"""Block resources and signed assessments using UniMind's quiz services."""
import hashlib
import http.client
import logging
import math
import random
import re
from urllib.parse import quote, urlsplit
from uuid import uuid4
from xml.etree import ElementTree

from django.core import signing
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from ai_engine import config
from ai_service import AIService
from ai_assistant.models import LearningResource, LearningResourceVersion
from ai_assistant.services import learning_resources
from ai_assistant.services.learning_library import resource_data
from core.utils import get_content_institution_id
from courses.access import has_full_course_access
from courses.models import Course
from quizzes.models import KnowledgePoint, Question, UserKnowledgeState
from quizzes.services.question_generator import QuestionGenerator
from quizzes.services.question_normalizer import normalize_options, normalize_objective_answer
from quizzes.services.single_generate_pipeline import _check_latex_integrity, _check_objective_integrity
from quizzes.ai_workflow import _grade_answer
from .intake import _bank_question
from .models import BlockResource, BlockStepAtom, UserBlockProgress
from .serializers import BlockResourceSerializer

logger = logging.getLogger(__name__)
SIGNING_SALT = 'knowledge-builder-block-quiz'


def _assignments(block):
    return sorted(BlockStepAtom.objects.filter(step__block=block).select_related('atom', 'step'),
                  key=lambda row: (row.membership_type != 'core', row.step.step_index, row.position, row.pk))


def _courses(user):
    scope = get_content_institution_id(required=False)
    scoped = Q(institution_id=scope)
    if scope is not None:
        scoped |= Q(institution__isnull=True, module__is_public=True, module__institution__isnull=True)
    rows = Course.objects.filter(scoped, is_published=True).select_related('knowledge_point')
    if not has_full_course_access(user):
        rows = rows.filter(module__is_public=True).filter(
            Q(module__institution_id=scope) | Q(institution__isnull=True, module__institution__isnull=True))
    return rows.order_by('pk')


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

    resources = block.resources.filter(~Q(source_kind='library') | Q(created_by=user))
    region = get_region_preference(user, request, explicit_region)
    return filter_resources_for_region(resources, region).order_by('id')


def auto_mount_internal_resources(build):
    for block in build.blocks.all():
        for candidate in internal_resource_candidates(build.created_by, block):
            fields = {key: value for key, value in candidate.items() if key != 'source_kind'}
            source = candidate['source_kind']
            lookup = {'course_id': fields['course_id']} if source == 'course' else {'library_resource_id': fields['library_resource_id']}
            BlockResource.objects.get_or_create(block=block, source_kind=source, **lookup,
                defaults={'build': build, 'created_by': build.created_by,
                          **{key: value for key, value in fields.items() if key not in lookup}})


def search_block_web_resources(block, query='', region_pref='cn'):
    from .public_asset_service import public_asset_allowed
    query = query.strip() or f'{block.build.subject} {block.short_title}'
    if len(query) > 300:
        raise ValidationError('查询词最多 300 字，请缩小搜索范围。')
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
    with transaction.atomic():
        return BlockResource.objects.create(build=block.build, block=block, created_by=user,
                                            atom_id=atom_id, step_id=step_id, **fields)


def _hash(stem):
    return hashlib.sha256(_normalized(stem).encode()).hexdigest()


def _knowledge_points(assignments):
    return {kp.name: kp for kp in KnowledgePoint.objects.filter(
        institution_id=get_content_institution_id(required=False), name__in=[row.atom.name for row in assignments]).order_by('-pk')}


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


def _offline_question(row, q_type, variant):
    atom = row.atom
    elements = [str(value).strip() for value in atom.key_elements if str(value).strip()]
    goal = atom.goal_statement.strip()
    if q_type == 'subjective':
        points = elements or [goal]
        rubric = [{'point': point, 'score': 10 / len(points)} for point in points]
        return dict(q_type=q_type, subjective_type='short',
            stem=f'围绕“{atom.name}”完成进阶挑战：{goal}。请说明适用条件、核心机制或公式推导，并举例解释结论。复测情境 {variant + 1}：分析条件改变后结论是否仍成立。',
            options={}, correct_answer='；'.join(points), grading_points='；'.join(points), rubric=rubric,
            explanation=f'应围绕掌握目标“{goal}”逐项说明，推理须连接条件与结论。', question_id=None)
    # Alternate the assessed element and truth judgement, rather than inventing subject facts.
    correct = elements[variant % len(elements)] if elements else goal
    mistakes = list(dict.fromkeys(str(value).strip() for value in atom.common_misconceptions if str(value).strip() and str(value).strip() != correct))
    if len(mistakes) >= 3:
        choices = [correct, *mistakes[:3]]
        random.Random(f'{atom.pk}:{variant}').shuffle(choices)
        options = dict(zip('ABCD', choices))
        answer = next(key for key, value in options.items() if value == correct)
        prompt = ('依据掌握目标，以下哪项表述正确？', '学习者需要纠正常见误区，以下哪项可作为正确依据？', '复核本知识点的核心要素时，应保留以下哪项表述？')[variant % 3]
        stem = f'“{atom.name}”应用情境 {variant + 1}：{prompt}'
    else:
        statement = mistakes[(variant // 2) % len(mistakes)] if mistakes and variant % 2 else correct
        options, answer = {'A': '正确', 'B': '错误'}, 'B' if statement in mistakes else 'A'
        stem = f'“{atom.name}”辨析 {variant + 1}：请判断下列表述是否正确：{statement}'
    return dict(q_type=q_type, subjective_type='', stem=stem, options=options, correct_answer=answer,
                explanation=f'掌握目标：{goal}。核心要素：{"；".join(elements)}。常见误区：{"；".join(mistakes)}。',
                grading_points='', rubric={}, question_id=None)


def _generate_question(row, block, q_type, seen):
    atom = row.atom
    if config._get_api_key():
        description = (f'所属学习块：{block.short_title}；掌握目标：{atom.goal_statement}；认知层级：{atom.cognitive_level}；'
                       f'核心要素：{"、".join(atom.key_elements)}；常见误区（请用作干扰项）：{"、".join(atom.common_misconceptions)}；'
                       f'本轮出题标识：{uuid4().hex}。请创作新的情境和题干。')
        if q_type == 'subjective':
            description += '请生成进阶简答或计算题，围绕核心机制或公式推导，必须包含 grading_points 和 rubric。'
        try:
            generated = QuestionGenerator(AIService)._request_bulk_generate_once(
                [{'id': atom.pk, 'code': atom.code, 'name': atom.name, 'description': description}],
                1, ['objective'] if q_type == 'objective' else ['subjective:short', 'subjective:calculate'], 'normal' if q_type == 'objective' else 'hard', '')
            for raw in generated:
                item = _clean_question(raw, q_type)
                if item and _hash(item['stem']) not in seen:
                    return item
        except Exception:
            # Explicit offline/API-failure contract: issue a targeted deterministic question.
            logger.exception('Block quiz AI generation failed; using atom-based questions')
    variant = 0
    while True:
        item = _offline_question(row, q_type, variant)
        if _hash(item['stem']) not in seen:
            return item
        variant += 1


def generate_block_quiz(user, block, mode='objective', retest=False):
    if mode not in ('objective', 'challenge'):
        raise ValidationError('请选择客观题快测或进阶挑战。')
    assignments = _assignments(block)
    if not assignments:
        raise ValidationError('当前知识块尚无原子点，无法生成检测。')
    progress, _ = UserBlockProgress.objects.get_or_create(user=user, block=block, defaults={'build': block.build})
    seen = set(progress.seen_question_hashes)
    weak = set(progress.weak_atom_ids) if retest else set()
    ordered = sorted(assignments, key=lambda row: (row.membership_type != 'core', row.atom_id not in weak))
    required = [row for row in ordered if row.membership_type == 'core' or row.atom_id in weak]
    target_count = max(3, len(required))
    selected = (required + [row for row in ordered if row not in required])[:max(4, target_count)]
    while len(selected) < target_count:
        selected.append(ordered[len(selected) % len(ordered)])
    kps = _knowledge_points(assignments)
    questions = []
    for row in selected:
        kp = kps.get(row.atom.name)
        item = None
        if kp and not retest:
            for question in Question.objects.filter(knowledge_point=kp, institution_id=kp.institution_id, q_type='objective').select_related('knowledge_point').order_by('pk'):
                bank = _bank_question(question)
                if bank:
                    bank['options'] = {o['key']: o['label'] for o in bank['options']}
                    item = _clean_question(bank, 'objective')
                    if item and _hash(item['stem']) not in seen:
                        break
                    item = None
        item = item or _generate_question(row, block, 'objective', seen)
        if not item['explanation']:
            item['explanation'] = f'掌握目标：{row.atom.goal_statement}。核心要素：{"；".join(row.atom.key_elements)}。'
        item.update(atom_id=row.atom_id, atom_code=row.atom.code, atom_name=row.atom.name,
                    membership_type=row.membership_type, kp_id=kp.pk if kp else None)
        questions.append(item)
        seen.add(_hash(item['stem']))
    if mode == 'challenge':
        row = ordered[0]
        item = _generate_question(row, block, 'subjective', seen)
        if not item['explanation']:
            item['explanation'] = f'评分要点：{item["grading_points"]}'
        kp = kps.get(row.atom.name)
        item.update(atom_id=row.atom_id, atom_code=row.atom.code, atom_name=row.atom.name,
                    membership_type=row.membership_type, kp_id=kp.pk if kp else None)
        questions.append(item)
        seen.add(_hash(item['stem']))
    manifest = [_hash(item['stem']) for item in questions]
    quiz_id = uuid4().hex
    public = []
    for index, item in enumerate(questions):
        item.update(id=f'{quiz_id}:{index}', block_id=block.pk, user_id=user.pk, quiz_id=quiz_id, manifest=manifest)
        signed = signing.dumps(item, salt=SIGNING_SALT, compress=True)
        public.append({key: value for key, value in item.items() if key in (
            'id', 'atom_id', 'atom_code', 'atom_name', 'membership_type', 'q_type', 'stem', 'options', 'subjective_type')})
        public[-1].update(signed_payload=signed, assessment_hint='说明适用条件、关键步骤及结论。' if item['q_type'] == 'subjective' else '')
    with transaction.atomic():
        progress = UserBlockProgress.objects.select_for_update().get(pk=progress.pk)
        progress.seen_question_hashes = sorted(set(progress.seen_question_hashes) | seen)
        if progress.status == 'UNSTARTED':
            progress.status = 'LEARNING'
        progress.save()
    return {'block_id': block.pk, 'mode': mode, 'questions': public}


def _grade_subjective(item, answer, atom):
    if config._get_api_key():
        try:
            question = Question(text=item['stem'], correct_answer=item['correct_answer'], q_type='subjective',
                                grading_points=item['grading_points'], rubric=item['rubric'], subjective_type=item['subjective_type'])
            grade = _grade_answer(question, answer)
            ratio = float(grade['normalized_score'])
            if not math.isfinite(ratio):
                raise ValueError('Invalid grading score')
            return max(0.0, min(1.0, ratio)), grade.get('feedback', '')
        except Exception:
            logger.exception('Block subjective grading failed; using keyword coverage')
    points = list(dict.fromkeys([str(value) for value in atom.key_elements if str(value).strip()]
                               + [part.strip() for part in re.split(r'[；;\n]', str(item['grading_points'])) if part.strip()]))
    normalized = _normalized(answer)
    covered = sum(_normalized(point) in normalized for point in points)
    coverage = covered / len(points) if points else 0.0
    # Require substantive text as well as the expected keywords; empty answers score zero.
    completeness = min(1.0, len(normalized) / max(1, sum(len(_normalized(point)) for point in points)))
    ratio = min(coverage, completeness)
    return ratio, f'关键词评分：覆盖 {covered}/{len(points)} 个要点。请结合适用条件说明推理过程。'


def submit_block_quiz(user, block, questions, answers):
    if not questions or not isinstance(questions, list) or not isinstance(answers, dict):
        raise ValidationError('请提交完整检测题目和答案。')
    assignments = {row.atom_id: row for row in _assignments(block)}
    items = []
    try:
        for question in questions:
            item = signing.loads(question['signed_payload'], salt=SIGNING_SALT)
            row = assignments.get(item['atom_id'])
            if item['block_id'] != block.pk or item['user_id'] != user.pk or not row or item['membership_type'] != row.membership_type:
                raise ValidationError('题目不属于当前用户或知识块，请重新出题。')
            items.append(item)
    except (signing.BadSignature, KeyError, TypeError, ValueError) as exc:
        raise ValidationError('题目签名无效，请重新出题。') from exc
    manifest = items[0]['manifest']
    if (len(set(item['id'] for item in items)) != len(items)
            or [_hash(item['stem']) for item in items] != manifest
            or any(item['quiz_id'] != items[0]['quiz_id'] or item['manifest'] != manifest for item in items)):
        raise ValidationError('请提交同一轮的全部题目，不可删题或重复提交单题。')
    results = []
    for item in items:
        answer = answers.get(item['id'], '')
        if not isinstance(answer, str) or len(answer) > 20000:
            raise ValidationError('答案必须是最多 20000 字的文本。')
        if item['q_type'] == 'objective':
            ratio = float(normalize_objective_answer(answer, item['options']) == item['correct_answer'])
            feedback = '回答正确。' if ratio else '请结合解析回看对应知识点。'
        else:
            ratio, feedback = _grade_subjective(item, answer, assignments[item['atom_id']].atom)
        results.append({key: item[key] for key in ('id', 'atom_id', 'atom_code', 'atom_name', 'membership_type', 'q_type', 'correct_answer', 'explanation')}
                       | {'user_answer': answer, 'passed': ratio >= .75, 'score_ratio': ratio, 'feedback': feedback})
    core_ids = {row.atom_id for row in assignments.values() if row.membership_type == 'core'}
    core_results = [result for result in results if result['membership_type'] == 'core']
    core_passed = (core_ids <= {result['atom_id'] for result in core_results} and all(result['passed'] for result in core_results)) if core_ids else all(result['passed'] for result in results)
    raw_accuracy = sum(result['score_ratio'] for result in results) / len(results)
    accuracy = round(raw_accuracy, 2)
    completed = core_passed and raw_accuracy >= .75
    failed = {result['atom_id'] for result in results if not result['passed']}
    mastered = {result['atom_id'] for result in results if result['passed']} - failed
    resources = list(visible_block_resources(user, block))
    recommended = [resource for resource in resources if resource.atom_id in failed or resource.atom_id is None]
    if failed and not recommended:
        recommended = resources
    with transaction.atomic():
        progress, _ = UserBlockProgress.objects.get_or_create(user=user, block=block, defaults={'build': block.build})
        progress = UserBlockProgress.objects.select_for_update().get(pk=progress.pk)
        progress.status = 'COMPLETED' if completed else 'NEEDS_REVIEW'
        progress.last_accuracy, progress.best_accuracy = accuracy, max(progress.best_accuracy, accuracy)
        progress.core_passed = core_passed
        progress.attempt_count += 1
        progress.mastered_atom_ids = sorted((set(progress.mastered_atom_ids) | mastered) - failed)
        progress.weak_atom_ids = sorted((set(progress.weak_atom_ids) - mastered) | failed)
        progress.completed_at = timezone.now() if completed else None
        kps = _knowledge_points(list(assignments.values()))
        if completed:
            for atom_id in mastered:
                kp = kps.get(assignments[atom_id].atom.name)
                if kp:
                    state, _ = UserKnowledgeState.objects.select_for_update().get_or_create(user=user, knowledge_point=kp)
                    state.mastery_score = max(state.mastery_score, .8)
                    state.save(update_fields=('mastery_score', 'updated_at'))
        result = dict(block_id=block.pk, status=progress.status, block_completed=completed, core_passed=core_passed,
            accuracy=accuracy, best_accuracy=progress.best_accuracy, attempt_count=progress.attempt_count,
            mastered_atom_ids=progress.mastered_atom_ids, weak_atom_ids=progress.weak_atom_ids,
            weak_atoms=[{'id': assignments[pk].atom_id, 'code': assignments[pk].atom.code, 'name': assignments[pk].atom.name}
                        for pk in progress.weak_atom_ids if pk in assignments], results=results,
            recommended_resources=BlockResourceSerializer(recommended, many=True).data,
            summary_message='当前知识块已完成！核心点全部通过，总得分率达到 75%。' if completed else
                f'本次总得分率 {accuracy:.0%}，核心点{"已全部通过" if core_passed else "尚未全部通过"}。请回看待强化点的资料，再针对薄弱点换题复测。')
        progress.last_quiz_result = result
        progress.save()
    return result
