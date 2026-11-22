"""Align reusable public learning assets with a tree's blocks and atom points."""
import http.client
import importlib
import re
from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import ValidationError

from .models import BlockResource, PublicAssetCatalog


CATALOG_FIELDS = (
    'title', 'source_kind', 'asset_track', 'pedagogical_role', 'region_scope',
    'description', 'topic_keywords', 'segments',
)


def compute_atom_difficulty(atom):
    """Compute the shared difficulty tier directly from an atom's learning goals."""
    goal_type = (getattr(atom, 'goal_type', '') or '').strip()
    cognitive_level = (getattr(atom, 'cognitive_level', '') or '').strip()
    granularity_minutes = int(getattr(atom, 'granularity_minutes', 4) or 4)
    if (goal_type in ('实操计算', '综合应用')
            or cognitive_level in ('评价', '创造')
            or (granularity_minutes >= 6 and cognitive_level == '分析' and goal_type != '概念辨析')):
        return 'L3', '硬核攻坚'
    if cognitive_level in ('记忆', '理解') and goal_type in ('概念辨析', '概念', ''):
        return 'L1', '基础速通'
    return 'L2', '机制辨析'


def _requires_difficult_atom(data):
    return data.get('respect_difficulty') and (data.get('source_kind') in ('bilibili', 'youtube')
        or (data.get('asset_track') in ('spine', 'spotlight')
            and data.get('source_kind') not in ('course', 'library')))


def _difficulty_filtered_details(details, data):
    """Restrict discovery videos to the harder concepts that they can teach."""
    if not _requires_difficult_atom(data):
        return details
    result = []
    for block, steps, assignments, _ in details:
        assignments = [row for row in assignments if compute_atom_difficulty(row.atom)[0] != 'L1']
        if assignments:
            labels = [label for row in assignments for label in (row.atom.name, row.atom.key_elements)]
            # The specific-term matcher prioritizes its first professional label.
            # Include every eligible concept there so later hard atoms retain coverage.
            labels.insert(0, ' '.join(_text(label) for label in labels))
            result.append((block, steps, assignments, labels))
    return result


def _resolvers():
    name = f'{__package__}.public_asset_resolvers'
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name != name:
            raise
        return None


def get_region_preference(user=None, request=None, explicit_region=''):
    if explicit_region in ('cn', 'intl'):
        return explicit_region
    if getattr(settings, 'UNIMIND_PUBLIC_ASSET_EDITION', 'cn') != 'intl':
        return 'cn'
    requested = getattr(request, 'query_params', {}).get('region', '') if request is not None else ''
    return requested if requested in ('cn', 'intl') else 'intl'


def public_asset_allowed(data, region_pref='cn'):
    from .public_asset_resolvers import is_asset_url_allowed
    return (not (region_pref == 'cn' and data.get('region_scope') == 'intl')
            and is_asset_url_allowed(data.get('url', ''), region_pref)
            and all(is_asset_url_allowed(segment.get('url', ''), region_pref)
                    for segment in data.get('segments', [])))


def validate_public_asset_data(data, region_pref='cn'):
    if public_asset_allowed(data, region_pref):
        return
    from .public_asset_resolvers import is_asset_url_allowed
    urls = [data.get('url', ''), *(segment.get('url', '') for segment in data.get('segments', []))]
    if any(not is_asset_url_allowed(url, 'intl') for url in urls):
        raise ValidationError('禁止使用百度百科，请使用专业开源 Wiki 或开源讲义仓库。')
    raise ValidationError('当前为国内版环境，已屏蔽境外不可直连站点（如 Wikipedia / YouTube），请使用 B 站、专业开源 Wiki（如 OI-Wiki / Hello-Algo）、开源讲义仓库或站内课程链接。')


def filter_resources_for_region(resources, region_pref='cn'):
    excluded = [row.pk for row in resources
                if not public_asset_allowed({'url': row.url, 'region_scope': row.region_scope}, region_pref)]
    return resources.exclude(pk__in=excluded)


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
    return [row for row in rows if public_asset_allowed(asset_data_from_catalog(row), region_pref)
            and (row.subject in ('', '*', 'general', '通用')
                 or _score(subject, [row.subject, row.title, row.topic_keywords]) > 0)]


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
    eligible = _difficulty_filtered_details([details], data)
    if not eligible:
        return None
    details = eligible[0]
    if (_requires_difficult_atom(data) and target_atom_id is not None
            and not any(row.atom_id == target_atom_id for row in details[2])):
        return None
    block = details[0]
    segment = segment or {}
    text = f"{segment.get('title', '')} {segment.get('summary', '')}" if segment else _asset_text(data)
    if _requires_difficult_atom(data):
        from .public_asset_discovery import _specific_score
        assignments = [row for row in details[2]
                       if target_atom_id is None or row.atom_id == target_atom_id]
        matched = [row for row in assignments if _specific_score(text, [row.atom.name, row.atom.key_elements]) > 0]
        if not matched:
            return None
        target_atom_id = max(matched, key=lambda row: (
            _specific_score(text, [row.atom.name, row.atom.key_elements]),
            _score(text, [row.atom.name, row.atom.key_elements]))).atom_id
    step, atom = _binding(details, text, target_atom_id)
    if _requires_difficult_atom(data) and atom is None:
        return None
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
        origin=data.get('origin', 'manual'),
        match_method=data.get('match_method', 'manual'),
        match_score=data.get('match_score', 0.0),
    )
    creator = user if user is not None and getattr(user, 'is_authenticated', False) else None
    # Album episodes share /courses, so retain their course ID and locator in the identity.
    identity = dict(build=build, block=block, public_asset=public_asset,
                    source_kind=data['source_kind'], url=url, locator=locator,
                    course_id=segment.get('course_id') or data.get('course_id'),
                    marketplace_listing_id=data.get('marketplace_listing_id'))
    if data.get('origin') == 'auto':
        # Automatic reruns must never resurrect dismissed or globally rejected alignments.
        existing = BlockResource.objects.filter(**identity).first()
        if existing is not None:
            if (_requires_difficult_atom(data)
                    and (existing.atom is None or compute_atom_difficulty(existing.atom)[0] == 'L1')):
                return None
            return existing
        if public_asset is not None:
            from .models import ConceptAssetIndex
            if ConceptAssetIndex.objects.filter(public_asset=public_asset,
                    segment_locator=locator, is_disabled=True).exists():
                return None
        resource, _ = BlockResource.objects.get_or_create(**identity,
                defaults={**fields, 'created_by': creator})
    else:
        resource, _ = BlockResource.objects.update_or_create(**identity,
                created_by=creator, defaults=fields)
    return resource


def align_and_mount_spine_series(build, asset_data, user=None, public_asset=None):
    details = _difficulty_filtered_details(_blocks(build), asset_data)
    if not details:
        if _requires_difficult_atom(asset_data):
            return []
        raise ValidationError('当前知识树没有可挂载资源的知识块。')
    segments = sorted(asset_data.get('segments', []), key=lambda item: item.get('index', 1))
    anchors = {}
    for index, segment in enumerate(segments):
        text = f"{segment['title']} {segment.get('summary', '')}"
        scores = [_score(text, item[3]) for item in details]
        best = max(range(len(scores)), key=scores.__getitem__)
        explicit = next((i for i, detail in enumerate(details)
                         if detail[0].pk == segment.get('target_block_id')), None)
        if explicit is not None:
            anchors[index] = explicit
        elif scores[best] > 0:
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
        type(build).objects.select_for_update().get(pk=build.pk)
        if asset_data.get('origin') == 'auto' and build.block_resources.filter(
                asset_track='spine', is_dismissed=False).exclude(public_asset=public_asset).exists():
            return []
        resources = [_mount(build, details[positions[index]], asset_data, user, public_asset, segment=segment,
                            target_atom_id=segment.get('target_atom_id'))
                     for index, segment in enumerate(segments)
                     if not asset_data.get('strict_alignment') or index in anchors]
        return [resource for resource in resources if resource is not None and not resource.is_dismissed]


def mount_single_public_asset(build, asset_data, user=None, public_asset=None, target_block=None, target_atom_id=None):
    details = _difficulty_filtered_details(_blocks(build), asset_data)
    if target_block is not None:
        details = [item for item in details if item[0].pk == target_block.pk]
    elif target_atom_id is not None:
        details = [item for item in details if any(row.atom_id == target_atom_id for row in item[2])]
    if not details:
        if _requires_difficult_atom(asset_data):
            return None
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
                   _score(row.subject, labels) if block is None else 0), row) for row in rows
              if public_asset_allowed(asset_data_from_catalog(row), region_pref)]
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
        query, lang='en' if region_pref == 'intl' else 'zh', limit=5, region_pref=region_pref)
    scopes = ('cn', 'global') if region_pref == 'cn' else ('intl', 'global')
    return [item for item in candidates if item.get('region_scope', 'global') in scopes
            and public_asset_allowed(item, region_pref)]


def resolve_and_store_asset(build, url, payload=None, user=None, region_pref='cn'):
    from ai_assistant.services import learning_resources
    payload = payload or {}
    if getattr(settings, 'UNIMIND_PUBLIC_ASSET_EDITION', 'cn') != 'intl':
        region_pref = 'cn'
    validate_public_asset_data({'url': url}, region_pref)
    resolver = _resolvers()
    fetched = []

    def fetch(target):
        validate_public_asset_data({'url': target}, region_pref)
        result = learning_resources.public_text(target)
        validate_public_asset_data({'url': result[0]}, region_pref)
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
    validate_public_asset_data(data, region_pref)
    asset = store_public_asset(build, data, user)
    return data, asset


def auto_mount_public_assets(build, *, respect_difficulty=False):
    region = get_region_preference(build.created_by)
    # Indexed assets must be reused through their verified concept alignment, not
    # broad catalog token overlap; this also preserves disabled feedback tombstones.
    assets = [asset for asset in catalog_candidates_for_build(build, region)
              if not asset.concept_alignments.exists()]
    from .public_asset_discovery import evaluate_candidate_quality, PART_MARKETING, _other_subject_part
    details = _blocks(build)
    assets = [asset for asset in assets if any(evaluate_candidate_quality(
        asset_data_from_catalog(asset), build.subject,
        [build.subject] if asset.asset_track == 'spine' else detail[3]) for detail in details)]
    existing_spine = build.block_resources.filter(asset_track='spine', is_dismissed=False).first()
    spine = next((asset for asset in assets if asset.asset_track == 'spine' and asset.segments
                  and (existing_spine is None or existing_spine.public_asset_id == asset.pk)), None)
    def automatic_data(asset):
        data = {**asset_data_from_catalog(asset), 'origin': 'auto', 'match_method': 'seed_catalog',
                'respect_difficulty': respect_difficulty}
        data['segments'] = [segment for segment in data.get('segments', [])
            if not PART_MARKETING.search(segment.get('title', ''))
            and not (0 < float(segment.get('duration', 0) or 0) < 90)
            and not (_other_subject_part(segment.get('title', ''))
                     and any(term in build.subject for term in ('\u79c1\u52df', '\u80a1\u6743')))]
        return data
    with transaction.atomic():
        if spine is not None:
            align_and_mount_spine_series(build, automatic_data(spine), build.created_by, spine)
        details = _blocks(build)
        for asset in assets:
            if asset.asset_track == 'spine':
                continue
            data = automatic_data(asset)
            eligible = _difficulty_filtered_details(details, data)
            ranked = sorted(eligible, key=lambda item: _score(_asset_text(data), item[3]), reverse=True)
            if ranked and _score(_asset_text(data), ranked[0][3]) > 0:
                limit = 2 if asset.asset_track == 'wiki' else 3
                if ranked[0][0].resources.filter(origin='auto', asset_track=asset.asset_track, is_dismissed=False).count() < limit:
                    mount_single_public_asset(build, data, build.created_by, asset, target_block=ranked[0][0])
        for listing in marketplace_candidates(build):
            data = {**_marketplace_data(listing), 'origin': 'auto', 'match_method': 'seed_catalog',
                    'respect_difficulty': respect_difficulty}
            eligible = _difficulty_filtered_details(details, data)
            ranked = sorted(eligible, key=lambda item: _score(_asset_text(data), item[3]), reverse=True)
            if ranked and _score(_asset_text(data), ranked[0][3]) > 0:
                if ranked[0][0].resources.filter(origin='auto', asset_track='spotlight', is_dismissed=False).count() < 3:
                    mount_single_public_asset(build, data, build.created_by, target_block=ranked[0][0])


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
    validate_public_asset_data(data, get_region_preference(user, request))
    for field in ('asset_track', 'pedagogical_role', 'locator'):
        if payload.get(field):
            data[field] = payload[field]
    if data.get('asset_track') == 'spine' and data.get('segments') and target_block is None and target_atom_id is None:
        resources = align_and_mount_spine_series(build, data, user, asset)
    else:
        resources = [mount_single_public_asset(build, data, user, asset, target_block, target_atom_id)]
    return dict(mounted_count=len(resources), asset_track=data.get('asset_track', 'spotlight'),
                public_asset=asset, resources=resources)
