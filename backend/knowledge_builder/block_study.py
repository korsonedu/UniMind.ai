"""Block resources and question generation for owned project tasks."""
import hashlib
import http.client
import logging
import re
from urllib.parse import quote, urlsplit
from uuid import uuid4
from xml.etree import ElementTree

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from ai_engine import config
from ai_service import AIService
from ai_assistant.models import LearningResource, LearningResourceVersion
from ai_assistant.services import learning_resources
from ai_assistant.services.learning_library import resource_data
from core.utils import get_content_institution_id
from quizzes.models import KnowledgePoint
from quizzes.services.question_generator import QuestionGenerator
from quizzes.services.question_normalizer import normalize_options, normalize_objective_answer
from quizzes.services.single_generate_pipeline import _check_latex_integrity, _check_objective_integrity
from .intake import _bank_question
from .models import BlockResource, BlockStepAtom
from .serializers import BlockResourceSerializer
from .source_parsers import clean_resource_excerpt

logger = logging.getLogger(__name__)
_DEFAULT_PUBLIC_TEXT = learning_resources.public_text


@transaction.atomic
def ensure_block_learning_project(user, block, project_id=None, atom_id=None):
    """Activate an owned graph learning path and reuse its companion conversation."""
    from django.contrib.auth import get_user_model
    from ai_assistant.models import (Bot, Conversation, ConversationProject,
                                     LearningKnowledgeVersion, ProjectLearning)
    from ai_assistant.services.learning_knowledge import knowledge_operation
    from ai_assistant.services.project_learning import change_learning

    # Project names have no uniqueness constraint. Serialize automatic creation for this user.
    get_user_model().objects.select_for_update().get(pk=user.pk)
    project = ConversationProject.objects.filter(pk=project_id, user=user).first() if project_id else None
    if project is None:
        version_ids = list(LearningKnowledgeVersion.objects.filter(
            knowledge_map__user=user, snapshot__builder__build_id=str(block.build_id)).values_list('pk', flat=True))
        project = ConversationProject.objects.filter(user=user).filter(
            Q(learning__plan__knowledge_path__version_id__in=version_ids)
            | Q(learning__pending_plan__plan__knowledge_path__version_id__in=version_ids)).first()
    if project is None:
        project = ConversationProject.objects.filter(user=user, name=block.build.subject[:60]).first()
    if project is None:
        project = ConversationProject.objects.create(
            user=user, name=block.build.subject[:60],
            instructions=f'围绕《{block.build.subject}》知识结构图谱进行分步学习、概念速通与难点检验。')

    state, _ = ProjectLearning.objects.get_or_create(project=project, defaults={'planning_enabled': True})
    state = ProjectLearning.objects.select_for_update().get(pk=state.pk)
    if not state.planning_enabled:
        state.planning_enabled = True
        state.save(update_fields=['planning_enabled', 'updated_at'])
    path = state.plan.get('knowledge_path') or {}
    version = LearningKnowledgeVersion.objects.filter(
        pk=path.get('version_id'), knowledge_map__user=user,
        snapshot__builder__build_id=str(block.build_id)).first()
    included = version and any(
        block.pk in node.get('builder_block_ids', []) for node in version.snapshot.get('nodes', []))
    if state.status != 'active' or not included:
        target_block_ids = list(block.build.blocks.values_list('pk', flat=True)[:26])
        if len(target_block_ids) > 25:
            target_block_ids = [block.pk]
        knowledge_operation(project, {
            'action': 'from_build', 'build_id': str(block.build_id),
            'block_ids': target_block_ids, 'revision': state.revision, 'depth': 'apply',
        })
        state.refresh_from_db()
        if state.pending_plan.get('plan'):
            change_learning(project, {'action': 'accept', 'revision': state.revision})
            state.refresh_from_db()

    bot = Bot.objects.filter(name='小宇', bot_type='planner', institution__isnull=True, is_active=True).order_by('id').first()
    if bot is None:
        bot = Bot.objects.filter(bot_type='planner').order_by('id').first()
    conversations = Conversation.objects.filter(user=user, project=project)
    conversation = conversations.filter(pk=state.last_conversation_id).first() if state.last_conversation_id else None
    if conversation is None:
        conversation = conversations.order_by('-updated_at').first()
    if conversation is None and bot:
        conversation = Conversation.objects.create(
            user=user, bot=bot, project=project, conversation_id=uuid4(),
            title=f'{block.build.subject[:40]} · 伴学')
    if conversation and state.last_conversation_id != conversation.pk:
        state.last_conversation = conversation
        state.save(update_fields=['last_conversation', 'updated_at'])
    return {
        'project_id': project.pk,
        'conversation_id': str(conversation.conversation_id) if conversation else None,
        'bot_id': bot.pk if bot else None,
        'project_name': project.name,
        'status': state.status,
        'block_id': block.pk,
        'atom_id': atom_id,
    }


def _assignments(block):
    return sorted(BlockStepAtom.objects.filter(step__block=block).select_related('atom', 'step'),
                  key=lambda row: (row.membership_type != 'core', row.step.step_index, row.position, row.pk))


def _courses(user):
    from types import SimpleNamespace
    from courses.access import visible_courses
    from courses.models import Course
    # Use the same workspace grants as the course page.
    try:
        return visible_courses(SimpleNamespace(user=user, query_params={})).select_related('knowledge_point').order_by('pk')
    except PermissionDenied:
        # Public catalog links remain usable when no curriculum partition is configured.
        return Course.objects.none()


def _normalized(text):
    return re.sub(r'\s+', '', text or '').casefold()


def _match(block, assignments, text):
    text = _normalized(text)
    matches = [(len(row.atom.name), row) for row in assignments if _normalized(row.atom.name) in text]
    if matches:
        return max(matches, key=lambda pair: pair[0])[1], True
    return None, _normalized(block.short_title) in text


def internal_resource_candidates(user, block, region_pref=None):
    from .public_asset_service import get_region_preference, public_asset_allowed
    region = region_pref or get_region_preference(user)
    assignments = _assignments(block)
    candidates = []
    for course in _courses(user):
        text = f'{course.title} {course.description or ""} {course.knowledge_point.name if course.knowledge_point else ""}'
        match, relevant = _match(block, assignments, text)
        if relevant:
            candidates.append({'source_kind': 'course', 'course_id': course.pk, 'title': course.title,
                               'url': '/courses', 'excerpt': course.description or '',
                               'step_id': match.step_id if match else None, 'atom_id': match.atom_id if match else None})
    if user and user.is_authenticated:
        for resource in LearningResource.objects.filter(user=user, is_archived=False):
            match, relevant = _match(block, assignments, f'{resource.title} {resource.topic} {resource.excerpt}')
            if relevant and public_asset_allowed({'url': resource.url}, region):
                candidates.append({'source_kind': 'library', 'library_resource_id': resource.pk,
                                   'title': resource.title, 'url': resource.url, 'excerpt': resource.excerpt,
                                   'step_id': match.step_id if match else None, 'atom_id': match.atom_id if match else None})
    return candidates


def visible_block_resources(user, block, request=None, explicit_region=''):
    # A curated/shared build must not expose another learner's private library snapshots.
    from .public_asset_service import filter_resources_for_region, get_region_preference

    resources = block.resources.filter(is_dismissed=False).filter(~Q(source_kind='library') | Q(created_by=user))
    if resources.filter(source_kind='course').exists():
        resources = resources.filter(~Q(source_kind='course') | Q(course_id__in=_courses(user).values('pk')))
    region = get_region_preference(user, request, explicit_region)
    return filter_resources_for_region(resources, region).order_by('id')


def auto_mount_internal_resources(build):
    for block in build.blocks.all():
        for candidate in internal_resource_candidates(build.created_by, block):
            fields = {key: value for key, value in candidate.items() if key != 'source_kind'}
            source = candidate['source_kind']
            lookup = {'course_id': fields['course_id']} if source == 'course' else {'library_resource_id': fields['library_resource_id']}
            if block.resources.filter(source_kind=source, **lookup).exists():
                continue
            if block.resources.filter(origin='auto', asset_track='spotlight', is_dismissed=False).count() >= 3:
                break
            BlockResource.objects.get_or_create(block=block, source_kind=source, **lookup,
                defaults={'build': build, 'created_by': build.created_by,
                          'origin': 'auto', 'match_method': f'internal_{source}',
                          **{key: value for key, value in fields.items() if key not in lookup}})


def search_block_web_resources(block, query='', region_pref='cn'):
    from .public_asset_service import public_asset_allowed
    query = query.strip() or f'{block.build.subject} {block.short_title}'
    if len(query) > 300:
        raise ValidationError('查询词最多 300 字，请缩小搜索范围。')
    if learning_resources.public_text is _DEFAULT_PUBLIC_TEXT and config._get_api_key():
        from .public_asset_discovery import search_public_web
        results = search_public_web(query, region_pref=region_pref, limit=5)
        if results:
            return [{key: item.get(key, '') for key in ('title', 'url', 'summary')} for item in results]
    try:
        _, xml = learning_resources.public_text('https://www.bing.com/search?format=rss&q=' + quote(query))
        root = ElementTree.fromstring(xml)
    except (OSError, http.client.HTTPException, ValueError, ElementTree.ParseError) as exc:
        raise ValidationError('公开资源搜索失败，请稍后重试。') from exc
    candidates = [{'title': row.findtext('title', '')[:200], 'url': row.findtext('link', ''),
                   'summary': row.findtext('description', '')[:600]} for row in root.findall('./channel/item')]
    return [item for item in candidates if item['url'].startswith('https://')
            and public_asset_allowed(item, region_pref)][:5]


def _save_library(user, block, title, url, excerpt):
    row, created = LearningResource.objects.select_for_update().get_or_create(
        user=user, url_hash=hashlib.sha256(url.encode()).hexdigest(),
        defaults={'url': url, 'title': title, 'excerpt': excerpt, 'read_at': timezone.now(),
                  'domain': urlsplit(url).hostname[:100], 'topic': block.short_title})
    if not created:
        LearningResourceVersion.objects.get_or_create(resource=row, revision=row.revision,
            defaults={'snapshot': resource_data(row)})
        row.revision += 1
        row.title, row.excerpt, row.read_at, row.is_archived = title, excerpt, timezone.now(), False
        row.save()
    LearningResourceVersion.objects.create(resource=row, revision=row.revision, snapshot=resource_data(row))
    return row


def attach_block_resource(user, block, payload, request=None):
    assignments = _assignments(block)
    step_id, atom_id = payload.get('step_id'), payload.get('atom_id')
    if step_id is not None and not block.steps.filter(pk=step_id).exists():
        raise ValidationError('步骤不属于当前知识块。')
    assignment = next((row for row in assignments if row.atom_id == atom_id), None)
    if atom_id is not None and (assignment is None or step_id is not None and assignment.step_id != step_id):
        raise ValidationError('原子点不属于当前知识块或指定步骤。')
    source_keys = [key for key in ('url', 'public_asset_id', 'marketplace_listing_id', 'course_id', 'library_resource_id')
                   if payload.get(key)]
    if len(source_keys) != 1:
        raise ValidationError('请指定一个网页 URL、公开资产、免费市场资源、站内课程或个人资料。')
    if source_keys[0] in ('url', 'public_asset_id', 'marketplace_listing_id'):
        from .public_asset_service import (get_region_preference, import_tree_public_asset,
                                           mount_single_public_asset, resolve_and_store_asset)

        if source_keys[0] == 'url':
            region_pref = get_region_preference(user, request)
            asset_data, public_asset = resolve_and_store_asset(
                block.build, payload['url'], payload, user, region_pref)
            with transaction.atomic():
                resource = mount_single_public_asset(
                    block.build, asset_data, user=user, public_asset=public_asset,
                    target_block=block, target_atom_id=atom_id)
                if payload.get('save_to_library'):
                    resource.library_resource_id = _save_library(
                        user, block, resource.title, resource.url, resource.excerpt).pk
                    resource.save(update_fields=('library_resource_id',))
        else:
            result = import_tree_public_asset(user, block.build, {
                **payload, 'target_block_id': block.pk, 'target_atom_id': atom_id,
            }, request=request)
            resource = result['resources'][0]
        if step_id is not None:
            if assignment is None:
                assignment, _ = _match(block, [row for row in assignments if row.step_id == step_id],
                                       f'{resource.title} {resource.excerpt}')
            resource.step_id = step_id
            resource.atom_id = assignment.atom_id if assignment else None
            resource.save(update_fields=('step', 'atom'))
        return resource
    if source_keys[0] == 'course_id':
        course = _courses(user).filter(pk=payload['course_id']).first()
        if course is None:
            raise ValidationError('课程不可见或尚未发布。')
        fields = dict(source_kind='course', title=course.title, url='/courses',
                      excerpt=course.description or '', course_id=course.pk)
    elif source_keys[0] == 'library_resource_id':
        resource = LearningResource.objects.filter(pk=payload['library_resource_id'], user=user, is_archived=False).first()
        if resource is None:
            raise ValidationError('个人资料不存在或已归档。')
        fields = dict(source_kind='library', title=resource.title, url=resource.url,
                      excerpt=resource.excerpt, library_resource_id=resource.pk)
    from .public_asset_service import get_region_preference, validate_public_asset_data
    validate_public_asset_data(fields, get_region_preference(user, request))
    if len(fields['url']) > 1000:
        raise ValidationError('挂载链接最多 1000 字。')
    if assignment is None:
        matching_assignments = [row for row in assignments if step_id is None or row.step_id == step_id]
        assignment, _ = _match(block, matching_assignments, f"{fields['title']} {fields['excerpt']}")
    if assignment:
        atom_id, step_id = assignment.atom_id, assignment.step_id
    fields.update({key: payload[key] for key in ('asset_track', 'pedagogical_role', 'locator') if key in payload})
    fields['excerpt'] = clean_resource_excerpt(fields.get('excerpt', ''), max_len=600)
    with transaction.atomic():
        return BlockResource.objects.create(build=block.build, block=block, created_by=user,
                                            atom_id=atom_id, step_id=step_id, **fields)


def auto_discover_block_resources(user, block, request=None, atom_id=None, max_mount=2):
    """Single-block budgeted fallback discovery so BlockResourceDrawer never triggers a full-tree scan."""
    from .public_asset_discovery import evaluate_candidate_quality, search_public_web
    from .public_asset_resolvers import detect_source_kind, extract_locator_from_url, infer_region_scope
    from .public_asset_service import get_region_preference, public_asset_allowed

    region = get_region_preference(user, request)
    assignments = _assignments(block)
    target_row = next((r for r in assignments if r.atom_id == atom_id), None) if atom_id else None
    focus_term = target_row.atom.name if target_row else block.short_title
    queries = [
        f'{block.build.subject} {focus_term} 精讲 site:bilibili.com/video',
        f'{block.build.subject} {focus_term} 讲义 定义',
    ]
    existing_urls = set(block.resources.filter(is_dismissed=False).values_list('url', flat=True))
    mounted = []
    labels = [focus_term, block.short_title, *(row.atom.name for row in assignments[:4])]

    for query in queries:
        if len(mounted) >= max_mount:
            break
        try:
            candidates = search_public_web(query, region_pref=region, limit=5)
        except Exception as exc:
            logger.warning('Single-block web discovery failed for query %r: %s', query, exc)
            continue
        for item in candidates:
            if len(mounted) >= max_mount:
                break
            url = (item.get('url') or '').strip()
            if not url.startswith('https://') or url in existing_urls:
                continue
            if not public_asset_allowed(item, region):
                continue
            score = evaluate_candidate_quality(item, block.build.subject, labels)
            if not score:
                continue
            kind = detect_source_kind(url)
            track = 'wiki' if kind == 'wikipedia' else 'spotlight'
            row_match = target_row
            if row_match is None:
                row_match, _ = _match(block, assignments, f"{item.get('title', '')} {item.get('summary', '')}")
            created = BlockResource.objects.create(
                build=block.build,
                block=block,
                step_id=row_match.step_id if row_match else None,
                atom_id=row_match.atom_id if row_match else None,
                source_kind=kind,
                asset_track=track,
                pedagogical_role='wiki_reference' if track == 'wiki' else 'concept_intuition',
                locator=extract_locator_from_url(url, kind),
                region_scope=infer_region_scope(url, kind),
                title=clean_resource_excerpt(item.get('title') or url, max_len=200),
                url=url[:1000],
                excerpt=clean_resource_excerpt(item.get('summary') or '', max_len=600),
                origin='auto',
                match_method='block_fallback_search',
                match_score=float(score),
                created_by=user,
            )
            existing_urls.add(url)
            mounted.append(created)
    return mounted


def _hash(stem):
    return hashlib.sha256(_normalized(stem).encode()).hexdigest()


def _knowledge_points(user, assignments):
    return {kp.name: kp for kp in KnowledgePoint.objects.filter(
        institution_id=get_content_institution_id(user), name__in=[row.atom.name for row in assignments]).order_by('-pk')}


def _clean_question(raw, q_type):
    if raw.get('q_type', q_type) != q_type:
        return None
    stem = str(raw.get('stem') or raw.get('question') or raw.get('text') or '').strip()
    if not stem:
        return None
    options = normalize_options(raw.get('options')) if q_type == 'objective' else {}
    answer = normalize_objective_answer(raw.get('correct_answer') or raw.get('answer'), options) if options else str(raw.get('correct_answer') or raw.get('answer') or '')
    grading_points = raw.get('grading_points') or ''
    if isinstance(grading_points, list):
        grading_points = '；'.join(str(point) for point in grading_points)
    rubric = raw.get('rubric') or []
    if q_type == 'subjective' and grading_points and not rubric:
        points = [point.strip() for point in re.split(r'[；;\n]', grading_points) if point.strip()]
        rubric = [{'point': point, 'score': 10 / len(points)} for point in points]
    item = dict(stem=stem, q_type=q_type, options=options, correct_answer=answer,
                explanation=str(raw.get('explanation') or raw.get('analysis') or ''),
                grading_points=grading_points, rubric=rubric,
                subjective_type=raw.get('subjective_type') or 'short', question_id=raw.get('question_id'))
    if q_type == 'objective':
        # The existing checker expects ABCD; two-choice judgement questions are valid too.
        actual = {key: value for key, value in options.items() if value}
        if len(actual) not in (2, 4) or answer not in actual or len(set(actual.values())) != len(actual):
            return None
        if _check_objective_integrity(item) and len(actual) != 2:
            return None
        item['options'] = actual
    elif item['subjective_type'] not in ('calculate', 'short') or not answer or not item['grading_points'] or not item['rubric']:
        return None
    if _check_latex_integrity(' '.join([stem, answer, *options.values(), item['explanation'], str(item['grading_points']), str(item['rubric'])])):
        return None
    return item


def _generate_question(row, block, q_type, seen, source_context=''):
    atom = row.atom
    if config._get_api_key():
        description = (f'所属学习块：{block.short_title}；掌握目标：{atom.goal_statement}；认知层级：{atom.cognitive_level}；'
                       f'核心要素：{"、".join(atom.key_elements)}；常见误区（请用作干扰项）：{"、".join(atom.common_misconceptions)}；'
                       f'本轮出题标识：{uuid4().hex}。请创作新的情境和题干。')
        if q_type == 'subjective':
            description += '请生成进阶简答或计算题，围绕核心机制或公式推导，必须包含 grading_points 和 rubric。'
        if source_context:
            description += f'\n当前项目实际保存的参考摘录（摘要不代表完整原文，不能虚构字幕或出处）：\n{source_context}'
        try:
            generated = QuestionGenerator(AIService)._request_bulk_generate_once(
                [{'id': atom.pk, 'code': atom.code, 'name': atom.name, 'description': description}],
                1, ['objective'] if q_type == 'objective' else ['subjective:short', 'subjective:calculate'], 'normal' if q_type == 'objective' else 'hard', '')
            for raw in generated:
                item = _clean_question(raw, q_type)
                if item and _hash(item['stem']) not in seen:
                    return item
        except Exception:
            logger.exception('Block task generation failed')
    raise ValidationError('暂时未能生成有效的新题，未创建检测或学习证据。请稍后重试。')


@transaction.atomic
def attach_project_resource(user, block, project_id, resource_id, request):
    from django.shortcuts import get_object_or_404
    from ai_assistant.models import ConversationProject, ProjectLearning
    from ai_assistant.services.learning_library import resource_operation
    project = get_object_or_404(ConversationProject, pk=project_id, user=user)
    resource = get_object_or_404(visible_block_resources(user, block, request=request), pk=resource_id)
    if resource.source_kind == 'library':
        return resource_operation(project, {'action': 'attach', 'resource_id': resource.library_resource_id})
    if resource.source_kind == 'course' and not _courses(user).filter(pk=resource.course_id).exists():
        raise ValidationError('当前空间无权使用这门课程。')
    state, _ = ProjectLearning.objects.get_or_create(project=project)
    url = f'/course/{resource.course_id}' if resource.source_kind == 'course' else resource.url
    existing = next((item for item in state.resources if item['url'] == url), None)
    if existing:
        return {'resource': existing, 'notice': '项目已保留这份资料，沿用原快照。'}
    # A mounted video or catalog entry only supplies metadata/excerpts, never its unseen transcript.
    source = dict(id=uuid4().hex, url=url, title=resource.title, excerpt=resource.excerpt,
        read_at=timezone.now().isoformat(), source_kind='block_resource_excerpt', not_web_read=True,
        content_version=hashlib.sha256(f'{resource.pk}:{resource.excerpt}'.encode()).hexdigest(),
        references=[{'build_id': str(block.build_id), 'block_id': block.pk, 'resource_id': resource.pk, 'locator': resource.locator}],
        notice='仅保存挂载条目的摘要或元数据，未读取视频字幕或核验完整原文。')
    return learning_resources.store_resource(project, source) | {'notice': source['notice']}
