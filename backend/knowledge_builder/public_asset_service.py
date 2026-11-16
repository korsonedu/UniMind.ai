"""Align reusable public learning assets with a tree's blocks and atom points."""
import http.client
import importlib
import re
from urllib.parse import urlsplit

from django.db import transaction
from rest_framework.exceptions import ValidationError

from .models import BlockResource, PublicAssetCatalog


CATALOG_FIELDS = (
    'title', 'source_kind', 'asset_track', 'pedagogical_role', 'region_scope',
    'description', 'topic_keywords', 'segments',
)


def _resolvers():
    name = f'{__package__}.public_asset_resolvers'
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name != name:
            raise
        return None


def get_region_preference(user=None, request=None, explicit_region=''):
    if not explicit_region and request is not None:
        explicit_region = getattr(request, 'query_params', {}).get('region', '')
    if explicit_region in ('cn', 'intl'):
        return explicit_region
    language = request.headers.get('Accept-Language', '') if request is not None else ''
    language = language or getattr(user, 'preferred_language', '')
    return 'intl' if language.casefold().startswith('en') else 'cn'


def _text(value):
    if isinstance(value, (list, tuple)):
        return ' '.join(_text(item) for item in value)
    if isinstance(value, dict):
        return ' '.join(_text(item) for item in value.values())
    return str(value or '')


def _normalized(value):
    return re.sub(r'[^\w\u4e00-\u9fff]+', '', _text(value)).casefold()


def _terms(value):
    value = _text(value).casefold()
    words = set(re.findall(r'[a-z0-9_]+', value))
    for phrase in re.findall(r'[\u4e00-\u9fff]+', value):
        words.add(phrase)
        words.update(phrase[index:index + 2] for index in range(len(phrase) - 1))
    return {word for word in words if len(word) > 1}


def _score(text, labels):
    normalized = _normalized(text)
    if not normalized:
        return 0
    score = 0
    for label in labels:
        label = _text(label)
        normalized_label = _normalized(label)
        if not normalized_label:
            continue
        if normalized_label in normalized:
            score += 8 + len(normalized_label)
        elif normalized in normalized_label:
            score += 4 + len(normalized)
        score += len(_terms(text) & _terms(label))
    return score


def asset_data_from_catalog(asset):
    resolver = _resolvers()
    locator = resolver.extract_locator_from_url(asset.url, asset.source_kind) if resolver else ''
    return {field: getattr(asset, field) for field in CATALOG_FIELDS} | {'url': asset.url, 'locator': locator}


def store_public_asset(build, asset_data, user=None):
    """Persist provider metadata once per subject and canonical URL."""
    for required in ('title', 'url'):
        if not asset_data.get(required):
            raise ValidationError(f'公开资产缺少 {required}。')
    if len(asset_data['url']) > 1000:
        raise ValidationError('挂载链接最多 1000 字。')
    defaults = {field: asset_data[field] for field in CATALOG_FIELDS if field in asset_data}
    defaults['title'] = defaults['title'][:200]
    if user is not None and getattr(user, 'is_authenticated', False):
        defaults['created_by'] = user
    asset, _ = PublicAssetCatalog.objects.update_or_create(
        subject=build.subject, url=asset_data['url'], defaults=defaults,
    )
    return asset


def ensure_subject_public_assets(subject, region_pref='cn'):
    resolver = _resolvers()
    if resolver is not None:
        for data in resolver.load_seed_public_assets(subject, region_pref):
            defaults = {field: data[field] for field in CATALOG_FIELDS if field in data}
            PublicAssetCatalog.objects.update_or_create(
                subject=data.get('subject') or subject, url=data['url'], defaults=defaults,
            )
    rows = PublicAssetCatalog.objects.all()
    rows = rows.filter(region_scope__in=('cn', 'global') if region_pref == 'cn' else ('intl', 'global'))
    return [row for row in rows if row.subject in ('', '*', 'general', '通用')
            or _score(subject, [row.subject, row.title, row.topic_keywords]) > 0]


def _blocks(build):
    blocks = list(build.blocks.order_by('layer', 'order', 'pk').prefetch_related('steps__step_atoms__atom'))
    details = []
    for block in blocks:
        steps = list(block.steps.all())
        assignments = [row for step in steps for row in step.step_atoms.all()]
        labels = [block.short_title, *[step.step_title for step in steps]]
        labels += [label for row in assignments for label in (row.atom.name, row.atom.key_elements)]
        details.append((block, steps, assignments, labels))
    return details


def _asset_text(data):
    parts = [_text(data.get(field)) for field in ('title', 'description', 'topic_keywords')]
    parts.extend(f"{segment.get('title', '')} {segment.get('summary', '')}" for segment in data.get('segments', []))
    return ' '.join(parts)


def _binding(details, text, target_atom_id=None):
    block, steps, assignments, _ = details
    if target_atom_id is not None:
        assignment = next((row for row in assignments if row.atom_id == target_atom_id), None)
        if assignment is None:
            raise ValidationError('原子点不属于当前知识块。')
        return assignment.step, assignment.atom
    ranked = [(_score(text, [row.atom.name, row.atom.key_elements]), row) for row in assignments]
    if ranked:
        score, assignment = max(ranked, key=lambda pair: pair[0])
        if score > 0:
            return assignment.step, assignment.atom
    ranked_steps = [(_score(text, [step.step_title]), step) for step in steps]
    if ranked_steps:
        score, step = max(ranked_steps, key=lambda pair: pair[0])
        if score > 0:
            return step, None
    return None, None


def _mount(build, details, data, user=None, public_asset=None, *, segment=None, target_atom_id=None):
    block = details[0]
    segment = segment or {}
    text = f"{segment.get('title', '')} {segment.get('summary', '')}" if segment else _asset_text(data)
    step, atom = _binding(details, text, target_atom_id)
    track = 'spine' if segment else data.get('asset_track', 'spotlight')
    locator = (segment.get('locator') or f"P{segment.get('index', 1)}") if segment else data.get('locator', '')
    title = f"{data['title']} · {segment['title']}" if segment else data['title']
    url = segment['url'] if segment else data['url']
    if not url or len(url) > 1000:
        raise ValidationError('公开资产需要最多 1000 字的可点击链接。')
    fields = dict(
        step=step, atom=atom, asset_track=track,
        pedagogical_role='series_episode' if segment else data.get('pedagogical_role') or
                         ('wiki_reference' if track == 'wiki' else 'concept_intuition'),
        title=title[:200], excerpt=segment.get('summary') or data.get('description', ''),
        region_scope=data.get('region_scope', 'global'),
    )
    creator = user if user is not None and getattr(user, 'is_authenticated', False) else None
    # Album episodes share /courses, so retain their course ID and locator in the identity.
    resource, _ = BlockResource.objects.update_or_create(
        build=build, block=block, public_asset=public_asset, created_by=creator,
        source_kind=data['source_kind'],
        url=url, locator=locator, course_id=segment.get('course_id') or data.get('course_id'),
        marketplace_listing_id=data.get('marketplace_listing_id'), defaults=fields,
    )
    return resource


def align_and_mount_spine_series(build, asset_data, user=None, public_asset=None):
    details = _blocks(build)
    if not details:
        raise ValidationError('当前知识树没有可挂载资源的知识块。')
    segments = sorted(asset_data.get('segments', []), key=lambda item: item.get('index', 1))
    anchors = {}
    for index, segment in enumerate(segments):
        text = f"{segment['title']} {segment.get('summary', '')}"
        scores = [_score(text, item[3]) for item in details]
        best = max(range(len(scores)), key=scores.__getitem__)
        if scores[best] > 0:
            anchors[index] = best
    positions = {}
    for index in range(len(segments)):
        if index in anchors:
            positions[index] = anchors[index]
            continue
        left = max((point for point in anchors if point < index), default=None)
        right = min((point for point in anchors if point > index), default=None)
        # Unmatched episodes follow the ordered blocks, interpolating between known titles.
        left_x, left_y = (left, anchors[left]) if left is not None else (0, 0)
        right_x, right_y = (right, anchors[right]) if right is not None else (max(0, len(segments) - 1), len(details) - 1)
        if right_x == left_x:
            position = left_y
        else:
            position = round(left_y + (right_y - left_y) * (index - left_x) / (right_x - left_x))
        positions[index] = max(0, min(len(details) - 1, position))
    with transaction.atomic():
        return [_mount(build, details[positions[index]], asset_data, user, public_asset, segment=segment)
                for index, segment in enumerate(segments)]


def mount_single_public_asset(build, asset_data, user=None, public_asset=None, target_block=None, target_atom_id=None):
    details = _blocks(build)
    if target_block is not None:
        details = [item for item in details if item[0].pk == target_block.pk]
    elif target_atom_id is not None:
        details = [item for item in details if any(row.atom_id == target_atom_id for row in item[2])]
    if not details:
        raise ValidationError('挂载目标不属于当前知识树，或知识树没有知识块。')
    best = max(details, key=lambda item: _score(_asset_text(asset_data), item[3]))
    return _mount(build, best, asset_data, user, public_asset, target_atom_id=target_atom_id)


def catalog_candidates_for_build(build, region_pref='cn', block=None):
    ensure_subject_public_assets(build.subject, region_pref)
    details = _blocks(build)
    labels = [build.subject] if block is None else []
    for current, _, _, current_labels in details:
        if block is None or current.pk == block.pk:
            labels.extend(current_labels)
    if block is None:
        labels.extend(build.atoms.values_list('name', flat=True))
    rows = PublicAssetCatalog.objects.all()
    rows = rows.filter(region_scope__in=('cn', 'global') if region_pref == 'cn' else ('intl', 'global'))
    ranked = [(max(_score(_asset_text(asset_data_from_catalog(row)), labels),
                   _score(row.subject, labels) if block is None else 0), row) for row in rows]
    return [row for score, row in sorted(ranked, key=lambda pair: (-pair[0], pair[1].pk)) if score > 0]


def marketplace_candidates(build):
    from quizzes.models import MarketplaceListing
    rows = MarketplaceListing.objects.filter(status='published', license_type='free')
    return [row for row in rows if _score(build.subject, [row.subject]) > 0]


def _marketplace_data(listing):
    return dict(title=listing.title[:200], url='/courses', source_kind='marketplace',
                asset_track='spotlight', description=listing.description, region_scope='global',
                topic_keywords=[listing.subject], marketplace_listing_id=listing.pk)


def album_candidates(build, user=None):
    from .block_study import _courses
    from courses.models import Album
    ids = _courses(user).exclude(album_obj_id=None).values_list('album_obj_id', flat=True)
    return [album for album in Album.objects.filter(pk__in=ids).order_by('pk')
            if _score(build.subject, [album.name, album.description]) > 0
            or any(_score(build.subject, [course.title, course.description, course.module.subject if course.module else '']) > 0
                   for course in _courses(user).filter(album_obj=album).select_related('module'))]


def wiki_candidates_for_block(block, region_pref='cn'):
    resolver = _resolvers()
    if resolver is None:
        return []
    query = block.short_title.strip()
    if not query:
        query = block.steps.values_list('step_atoms__atom__name', flat=True).exclude(
            step_atoms__atom__name=None).first() or ''
    candidates = resolver.search_wikipedia_concepts(
        query, lang='en' if region_pref == 'intl' else 'zh', limit=5)
    scopes = ('cn', 'global') if region_pref == 'cn' else ('intl', 'global')
    return [item for item in candidates if item.get('region_scope', 'global') in scopes]


def resolve_and_store_asset(build, url, payload=None, user=None, region_pref='cn'):
    from ai_assistant.services import learning_resources
    payload = payload or {}
    resolver = _resolvers()
    fetched = []

    def fetch(target):
        result = learning_resources.public_text(target)
        fetched.append(result)
        return result

    try:
        if resolver is None:
            host = (urlsplit(url).hostname or '').casefold()
            if any(host == domain or host.endswith('.' + domain) for domain in
                   ('bilibili.com', 'b23.tv', 'github.com', 'wikipedia.org', 'oi-wiki.org', 'youtube.com', 'youtu.be')):
                raise ValidationError('公开资产解析模块尚未安装，暂时无法导入此链接。')
            final_url, _ = fetch(url)
            data = dict(title=final_url[:200], url=final_url, source_kind='web',
                        asset_track='spotlight', region_scope='global', description='')
        else:
            data = dict(resolver.resolve_public_asset_url(
                url, preferred_lang='en' if region_pref == 'intl' else 'zh', html_fetcher=fetch))
        if data.get('source_kind') == 'web' and fetched:
            # Preserve existing general-page imports, including full body text and empty-page rejection.
            parser = learning_resources.PageText()
            parser.feed(fetched[-1][1])
            excerpt = '\n'.join(parser.text).strip()[:10000]
            if not excerpt:
                raise ValidationError('页面没有可读正文，请更换来源。')
            data.update(title=' '.join(parser.title)[:200] or data['title'], description=excerpt)
        for field in ('title', 'asset_track', 'pedagogical_role', 'locator'):
            if payload.get(field):
                data[field] = payload[field]
        if payload.get('outline_text'):
            if resolver is None:
                raise ValidationError('公开资产解析模块尚未安装，暂时无法解析课程目录。')
            data['segments'] = resolver.parse_custom_outline_segments(url, payload['outline_text'])
            if 'asset_track' not in payload:
                data['asset_track'] = 'spine'
    except (OSError, http.client.HTTPException, ValueError) as exc:
        raise ValidationError('公开资产读取或解析失败，请检查链接或稍后重试。') from exc
    asset = store_public_asset(build, data, user)
    return data, asset


def auto_mount_public_assets(build):
    region = get_region_preference(build.created_by)
    assets = catalog_candidates_for_build(build, region)
    spine = next((asset for asset in assets if asset.asset_track == 'spine' and asset.segments), None)
    with transaction.atomic():
        if spine is not None:
            align_and_mount_spine_series(build, asset_data_from_catalog(spine), build.created_by, spine)
        details = _blocks(build)
        for asset in assets:
            if asset.asset_track == 'spine':
                continue
            data = asset_data_from_catalog(asset)
            if any(_score(_asset_text(data), item[3]) > 0 for item in details):
                mount_single_public_asset(build, data, build.created_by, asset)
        for listing in marketplace_candidates(build):
            if details:
                mount_single_public_asset(build, _marketplace_data(listing), build.created_by)


@transaction.atomic
def import_tree_public_asset(user, build, payload, request=None):
    keys = [key for key in ('public_asset_id', 'marketplace_listing_id', 'album_id', 'url') if payload.get(key)]
    if len(keys) != 1:
        raise ValidationError('请指定一个公开资产、免费市场资源、课程专辑或 URL。')
    target_block = None
    if payload.get('target_block_id') is not None:
        target_block = build.blocks.filter(pk=payload['target_block_id']).first()
        if target_block is None:
            raise ValidationError('知识块不属于当前知识树。')
    target_atom_id = payload.get('target_atom_id')
    if target_atom_id is not None and not build.atoms.filter(pk=target_atom_id).exists():
        raise ValidationError('原子点不属于当前知识树。')
    asset = None
    source = keys[0]
    if source == 'public_asset_id':
        asset = PublicAssetCatalog.objects.filter(pk=payload[source]).first()
        if asset is None:
            raise ValidationError('公开资产不存在。')
        data = asset_data_from_catalog(asset)
    elif source == 'marketplace_listing_id':
        from quizzes.models import MarketplaceListing
        listing = MarketplaceListing.objects.filter(pk=payload[source], status='published', license_type='free').first()
        if listing is None:
            raise ValidationError('市场资源不存在、尚未发布或不是免费资源。')
        data = _marketplace_data(listing)
    elif source == 'album_id':
        from .block_study import _courses
        from courses.models import Album
        album = Album.objects.filter(pk=payload[source]).first()
        courses = list(_courses(user).filter(album_obj_id=payload[source]).order_by('sort_order', 'pk'))
        if album is None or not courses:
            raise ValidationError('课程专辑没有可见的已发布课程。')
        data = dict(title=album.name, description=album.description, source_kind='course',
                    asset_track='spine', region_scope='global', url='/courses', segments=[
                        dict(index=index, title=course.title, url='/courses', locator=f'course:{course.pk}',
                             course_id=course.pk, summary=course.description or '')
                        for index, course in enumerate(courses, 1)])
    else:
        data, asset = resolve_and_store_asset(build, payload['url'], payload, user,
                                             get_region_preference(user, request))
    for field in ('asset_track', 'pedagogical_role', 'locator'):
        if payload.get(field):
            data[field] = payload[field]
    if data.get('asset_track') == 'spine' and data.get('segments') and target_block is None and target_atom_id is None:
        resources = align_and_mount_spine_series(build, data, user, asset)
    else:
        resources = [mount_single_public_asset(build, data, user, asset, target_block, target_atom_id)]
    return dict(mounted_count=len(resources), asset_track=data.get('asset_track', 'spotlight'),
                public_asset=asset, resources=resources)
