"""Generate source-grounded studio artifacts and grade their private quizzes."""

import json
import logging
import unicodedata

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from jsonschema import Draft202012Validator
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from ai_engine.service import AICallError, AIEngine
from users.learning import confirm_ai_call, release_ai_call, reserve_ai_call

from ai_assistant.models import ProjectStudioArtifact
from ai_assistant.services.dsh_runtime import DshUnavailable
from .project_learning_tools import obj
from .ulr_structured import InvalidStructuredOutput, StructuredOutputSchemaError, StructuredProviderFailure
from .workbench_grounding import CITATION_MARKER, WorkbenchGrounding, active_sources, extract_workbench_citations, workbench_prompt

logger = logging.getLogger(__name__)
Kind = ProjectStudioArtifact.Kind
Status = ProjectStudioArtifact.Status


def _string(max_length):
    return {'type': 'string', 'minLength': 1, 'maxLength': max_length, 'pattern': r'\S'}


def _array(items, minimum, maximum):
    return {'type': 'array', 'items': items, 'minItems': minimum, 'maxItems': maximum}


def _object(**properties):
    return obj(properties, properties)


_CITE_KEY = {'type': 'string', 'pattern': r'^S[1-9]\d*#C\d+$'}
_MARKED_ENTRY = {**_string(900), 'pattern': CITATION_MARKER.pattern}
_GUIDE = _object(
    main_question=_MARKED_ENTRY,
    source_outline=_array(_MARKED_ENTRY, 1, 60),
    key_concepts=_array(_object(concept=_string(80), explanation=_MARKED_ENTRY), 1, 20),
    confusing_points=_array(_MARKED_ENTRY, 0, 12),
    study_order=_array(_MARKED_ENTRY, 1, 12),
)
_CARD = _object(front=_string(500), back=_string(1000), hint=_string(350), cite_key=_CITE_KEY)
_QUESTION = {'prompt': _string(1000), 'explanation': _string(1000), 'cite_key': _CITE_KEY}
_RUBRIC_POINT = _object(criterion=_string(350), keywords=_array(_string(100), 1, 5))
_SCHEMAS = {
    Kind.STUDY_GUIDE: _GUIDE,
    Kind.BRIEFING: _object(content_markdown=_string(16000)),
    Kind.FAQ: _object(pairs=_array(_object(question=_string(300), answer=_MARKED_ENTRY), 6, 10)),
    Kind.FLASHCARDS: _object(cards=_array(_CARD, 10, 16)),
    Kind.QUIZ: _object(questions=_array({'oneOf': [
        _object(**_QUESTION, type={'const': 'single_choice'}, options={
            **_array(_string(350), 2, 5), 'uniqueItems': True,
        }, answer_index={'type': 'integer', 'minimum': 0, 'maximum': 4}),
        _object(**_QUESTION, type={'const': 'subjective'}, reference_answer=_string(1500),
                rubric=_array(_RUBRIC_POINT, 1, 5)),
    ]}, 4, 6)),
}
_VALIDATORS = {kind: Draft202012Validator(schema) for kind, schema in _SCHEMAS.items()}
_GRADING_SCHEMA = _object(
    matched_points={**_array({'type': 'integer', 'minimum': 1}, 0, 5), 'uniqueItems': True},
    feedback=_string(700),
)
_GRADING_VALIDATOR = Draft202012Validator(_GRADING_SCHEMA)


class StudioOutputError(ValueError):
    pass


_OUTPUT_ERRORS = (AICallError, DshUnavailable, StudioOutputError)


def _guide_markdown(guide):
    concepts = []
    for item in guide['key_concepts']:
        concept = item['concept'].replace('|', r'\|').replace('\n', ' ')
        explanation = item['explanation'].replace('|', r'\|').replace('\n', ' ')
        concepts.append(f'| {concept} | {explanation} |')
    return '\n'.join([
        '## 核心主线问题', '', guide['main_question'], '',
        '## 各份资料与章节脉络', '', *(f'- {line}' for line in guide['source_outline']), '',
        '## 核心概念速查表', '', '| 概念 | 解释 |', '| --- | --- |', *concepts, '',
        '## 易混对比点', '', *(f'- {line}' for line in guide['confusing_points']), '',
        '## 建议学习顺序', '', *(f'{i}. {line}' for i, line in enumerate(guide['study_order'], 1)),
    ])


def _flashcard_markdown(cards):
    return '\n\n'.join(
        f"## {card['front']}\n\n{card['back']} [{card['cite_key']}]\n\n提示：{card['hint']}" for card in cards
    )


def artifact_note_markdown(artifact):
    if artifact.kind == Kind.FLASHCARDS:
        return _flashcard_markdown(artifact.structured_payload['cards'])
    return artifact.content_markdown


def _validate_quiz(questions, include_subjective):
    subjective_count = sum(question['type'] == 'subjective' for question in questions)
    if subjective_count > 1 or (include_subjective is not None and subjective_count != include_subjective):
        raise StudioOutputError('Invalid number of subjective questions')
    for question in questions:
        if question['type'] == 'single_choice' and not 0 <= question['answer_index'] < len(question['options']):
            raise StudioOutputError('Answer index outside options')


def _generate(kind, grounding, excerpts, focus, include_subjective, *, citation_retry):
    context = {
        'custom_focus': focus,
        'sources': {grounding.aliases[source.pk]: source.title for source in grounding.sources.values()},
        'excerpts': {row['marker']: row['content'] for row in excerpts},
    }
    if kind == Kind.QUIZ:
        context['include_subjective'] = include_subjective
    instruction = workbench_prompt('studio_grounding.txt') + '\n\n' + workbench_prompt(f'studio_{kind}.txt')
    if citation_retry:
        instruction += '\n\n上一次有条目未通过原文引用格式校验。请逐条检查，原样复制 excerpts 中的引用锚点，保留半角方括号。'
    result = AIEngine.structured_output(
        messages=[
            {'role': 'system', 'content': instruction},
            {'role': 'user', 'content': json.dumps(context, ensure_ascii=False)},
        ],
        schema=_SCHEMAS[kind], tool_name='submit_studio_artifact',
        operation=f'assistant.chat.planner.studio.{kind}', max_tokens=6500,
        temperature=0.25, raise_on_error=True,
    )
    schema_error = next(_VALIDATORS[kind].iter_errors(result), None)
    if schema_error is not None:
        raise StructuredOutputSchemaError(schema_error)

    markdown, payload, keys = '', result, []
    if kind == Kind.STUDY_GUIDE:
        markdown = _guide_markdown(result)
    elif kind == Kind.BRIEFING:
        markdown, payload = result['content_markdown'], {}
    elif kind == Kind.FAQ:
        markdown = '\n\n'.join(f"## {item['question']}\n\n{item['answer']}" for item in result['pairs'])
    elif kind == Kind.FLASHCARDS:
        payload = {'cards': [
            {**card, 'id': f'fc_{i}', 'mastery': ProjectStudioArtifact.Mastery.UNSEEN}
            for i, card in enumerate(result['cards'], 1)
        ]}
        keys = [card['cite_key'] for card in payload['cards']]
    else:
        _validate_quiz(result['questions'], include_subjective)
        payload = {'questions': [{**question, 'id': f'q_{i}'} for i, question in enumerate(result['questions'], 1)]}
        keys = [question['cite_key'] for question in payload['questions']]

    # Resolve explicit anchors in cards/questions as well as inline Markdown markers.
    cited_content = markdown + '\n' + ''.join(f'[{key}]' for key in keys)
    cited_content += json.dumps(result, ensure_ascii=False)
    citations = extract_workbench_citations(cited_content, grounding.citation_registry)
    if not citations or set(CITATION_MARKER.findall(cited_content)) != {row['cite_key'] for row in citations}:
        raise StudioOutputError('Missing or unknown source citation')
    if not set(keys) <= grounding.citation_registry.keys():
        raise StudioOutputError('Unknown card or question citation')
    return {'content_markdown': markdown, 'structured_payload': payload, 'citations': citations}


def generate_studio_artifact(project, *, kind, source_ids=None, custom_focus='', include_subjective=None):
    sources = active_sources(project, source_ids, error_field='source_ids')
    if not sources:
        raise ValidationError({'source_ids': '请至少选择一份已就绪的资料。'})
    grounding = WorkbenchGrounding(project, sources)
    excerpts = grounding.studio_excerpts(custom_focus)
    if not custom_focus and include_subjective is None:
        include_subjective = False

    artifacts = project.studio_artifacts.filter(user_id=project.user_id)
    with transaction.atomic():
        reservation = reserve_ai_call(project.user)
        artifact = ProjectStudioArtifact.objects.create(
            project=project, user_id=project.user_id, kind=kind, title=Kind(kind).label,
            source_ids=[str(source.pk) for source in sources],
        )
    target = artifacts.filter(pk=artifact.pk, status=Status.GENERATING)
    completed = False
    error_message = '生成失败，请重新生成。'
    try:
        for attempt in range(2):
            try:
                output = _generate(kind, grounding, excerpts, custom_focus, include_subjective, citation_retry=bool(attempt))
            except (*_OUTPUT_ERRORS, InvalidStructuredOutput, StructuredProviderFailure) as exc:
                logger.warning('Studio generation failed for %s on attempt %d (%s)', artifact.pk, attempt + 1, type(exc).__name__)
                if (not attempt and kind == Kind.STUDY_GUIDE and isinstance(exc, StructuredOutputSchemaError)
                        and exc.pattern == CITATION_MARKER.pattern):
                    error_message = '资料导读的原文引用格式校验失败，自动重试一次后仍未生成。请点击「重新生成」。'
                    continue
            else:
                with transaction.atomic():
                    if not target.update(**output, status=Status.READY, updated_at=timezone.now()):
                        raise NotFound()
                    _confirm_reservation(reservation)
                completed = True
            break
    finally:
        if not completed:
            with transaction.atomic():
                target.update(status=Status.FAILED, error_message=error_message, updated_at=timezone.now())
                release_ai_call(reservation)
    return get_object_or_404(artifacts, pk=artifact.pk)


def _confirm_reservation(reservation):
    confirmed = confirm_ai_call(reservation)
    if confirmed.status != 'succeeded' or confirmed.attempt_id != reservation.attempt_id:
        raise DshUnavailable('AI 额度预留已失效，请重试。')


def _normalize(value):
    return ''.join(char for char in unicodedata.normalize('NFKC', value).casefold() if char.isalnum())


def _fallback_grade(question, answer):
    normalized = _normalize(answer)
    points = [point['criterion'] for point in question['rubric']
              if any(key and key in normalized for key in map(_normalize, point['keywords']))]
    feedback = f'按评分要点关键词匹配，命中 {len(points)}/{len(question["rubric"])} 项。'
    if points:
        feedback += ' 命中要点：' + '；'.join(points)
    return len(points), feedback, 'keyword'


def _grade_subjective(question, answer, citation):
    result = AIEngine.structured_output(
        messages=[
            {'role': 'system', 'content': workbench_prompt('studio_quiz_grade.txt')},
            {'role': 'user', 'content': json.dumps({
                'question': question['prompt'], 'reference_answer': question['reference_answer'],
                'rubric': question['rubric'], 'answer': answer, 'source_excerpt': citation['quote'],
            }, ensure_ascii=False)},
        ],
        schema=_GRADING_SCHEMA, tool_name='submit_studio_grade', operation='quizzes.grade.workbench_studio',
        temperature=0, max_tokens=1000, raise_on_error=True,
    )
    if (_GRADING_VALIDATOR.is_valid(result)
            and all(point <= len(question['rubric']) for point in result['matched_points'])):
        return len(result['matched_points']), result['feedback'], 'ai_rubric'
    raise StudioOutputError('Invalid rubric grade')


def _validate_answers(questions, answers):
    by_id = {question['id']: question for question in questions}
    for question_id, answer in answers.items():
        question = by_id.get(question_id)
        if question is None:
            raise ValidationError({'answers': f'题目 {question_id} 不属于本次自测。'})
        if question['type'] == 'single_choice':
            if type(answer) is not int or not 0 <= answer < len(question['options']):
                raise ValidationError({'answers': f'题目 {question_id} 的答案必须是有效的选项索引。'})
        elif not isinstance(answer, str) or not answer.strip() or len(answer) > 4000:
            raise ValidationError({'answers': f'题目 {question_id} 的答案必须是 1–4000 字的文本。'})


def grade_studio_quiz(artifact, answers):
    questions = artifact.structured_payload['questions']
    _validate_answers(questions, answers)
    citations = {row['cite_key']: row for row in artifact.citations}
    results, reservation, ai_graded, completed = [], None, False, False
    try:
        for question in questions:
            question_id, kind = question['id'], question['type']
            answer = answers.get(question_id)
            citation = citations[question['cite_key']]
            correct_answer = question['answer_index'] if kind == 'single_choice' else question['reference_answer']
            feedback = ''
            if answer is None:
                score, method = 0, 'unanswered'
            elif kind == 'single_choice':
                score, method = int(answer == correct_answer), 'answer_key'
            else:
                try:
                    reservation = reserve_ai_call(artifact.user)
                except PermissionDenied:
                    points, feedback, method = _fallback_grade(question, answer)
                else:
                    try:
                        points, feedback, method = _grade_subjective(question, answer, citation)
                    except _OUTPUT_ERRORS:
                        points, feedback, method = _fallback_grade(question, answer)
                    else:
                        ai_graded = True
                score = round(points / len(question['rubric']), 2)
            results.append({
                'question_id': question_id, 'answer': answer, 'correct_answer': correct_answer,
                'is_correct': score == 1, 'score': score, 'max_score': 1, 'grading_method': method,
                'explanation': question['explanation'], 'feedback': feedback, 'citation': citation,
            })

        attempt = {
            'score': round(sum(row['score'] for row in results), 2),
            'max_score': len(questions), 'results': results, 'submitted_at': timezone.now().isoformat(),
        }
        with transaction.atomic():
            target = ProjectStudioArtifact.objects.filter(pk=artifact.pk, project_id=artifact.project_id,
                                                          user_id=artifact.user_id, status=Status.READY)
            if not target.update(structured_payload={**artifact.structured_payload, 'latest_attempt': attempt},
                                 updated_at=timezone.now()):
                raise NotFound()
            if reservation is not None:
                if ai_graded:
                    _confirm_reservation(reservation)
                else:
                    release_ai_call(reservation)
        completed = True
        return attempt
    finally:
        if reservation is not None and not completed:
            release_ai_call(reservation)
