"""Two student-confirmed actions; model callbacks can only prepare signed drafts."""
import hashlib
import json
import time
from uuid import NAMESPACE_URL, uuid4, uuid5

from django.contrib.auth import get_user_model
from django.core import signing
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from ai_assistant.models import DshSubmission
from core.utils import get_content_institution_id
from quizzes.services.diagnostic_service import (
    DiagnosticAnswerInput, DIAGNOSTIC_TIME_LIMIT_SECONDS, generate_diagnostic_questions,
    grade_diagnostic_answers, initialize_memorix_from_diagnostic,
)
from users.feature_access import has_learning_feature
from users.models import AIUsageReservation
from .dsh_runtime import site_request_lock, quota_write_lock


SALT = 'unimind.dsh.student-confirmation.v1'
FEATURES = {'diagnostic': 'quiz.exam', 'faq': 'faq.system'}


class Conflict(APIException):
    status_code = 409
    default_detail = '该操作已提交其他内容，请刷新查看原结果。'


def check_feature(user, kind):
    if kind not in FEATURES or not has_learning_feature(user, FEATURES[kind]):
        raise PermissionDenied('当前账号无权执行此操作。')


def draft(user, kind, fields, source=None):
    check_feature(user, kind)
    identity = json.dumps([user.pk, kind, source, fields], sort_keys=True, ensure_ascii=False)
    request_id = str(uuid5(NAMESPACE_URL, identity) if source else uuid4())
    expires = int(time.time()) + (DIAGNOSTIC_TIME_LIMIT_SECONDS if kind == 'diagnostic' else 86400)
    claims = {**fields, 'user': user.pk, 'kind': kind, 'request_id': request_id,
              'scope': get_content_institution_id(), 'source': source, 'expires_at': expires}
    return {**fields, 'kind': kind, 'request_id': request_id, 'expires_at': expires,
            'token': signing.dumps(claims, salt=SALT, compress=True)}


def prepare_diagnostic(user, source=None):
    check_feature(user, 'diagnostic')
    user.refresh_from_db(fields=['has_completed_initial_assessment'])
    if user.has_completed_initial_assessment:
        return {'already_completed': True, 'message': '已完成首次诊断，请到诊断页按规则重新评估。',
                'visual': {'type': 'data_card', 'payload': {'title': '诊断已完成', 'items': [],
                    'cta': {'label': '查看诊断与重新评估', 'link': '/diagnostic'}}}}
    questions = generate_diagnostic_questions(get_content_institution_id())
    if not questions:
        return {'error': '暂无可用诊断题，请联系管理员补充题库。'}
    payload = draft(user, 'diagnostic', {'question_ids': [row['id'] for row in questions]}, source)
    payload.pop('question_ids')
    payload.update(questions=questions, time_limit_seconds=DIAGNOSTIC_TIME_LIMIT_SECONDS)
    return {'question_count': len(questions), 'message': '诊断题已准备，请学生在卡片内自行作答并确认提交。',
            'visual': {'type': 'diagnostic_quiz', 'payload': payload}}


def prepare_faq(user, arguments, source=None):
    text = serializers.CharField(max_length=4000).run_validation(arguments.get('question_text'))
    context = serializers.CharField(max_length=3000, allow_blank=True).run_validation(arguments.get('context_summary', ''))
    content = f'【背景】{context}\n\n【问题】{text}' if context else text
    payload = draft(user, 'faq', {'content': content}, source)
    return {'message': '人工答疑草稿已准备，尚未发布；请学生核对并确认。',
            'visual': {'type': 'faq_draft', 'payload': payload}}


def load_claims(user, token):
    try:
        claims = signing.loads(token, salt=SALT, max_age=86400)
    except (signing.BadSignature, TypeError, ValueError):
        raise ValidationError('草稿已失效，请让小宇重新准备。') from None
    if claims.get('user') != user.pk:
        raise PermissionDenied('该草稿不属于当前账号。')
    check_feature(user, claims.get('kind'))
    if claims.get('scope') != get_content_institution_id():
        raise Conflict('内容范围已变化，请重新准备。')
    return claims


def confirm(user, data):
    if data.get('confirmed') is not True:
        raise ValidationError('请先核对内容并明确确认提交。')
    claims = load_claims(user, data.get('token'))
    kind = claims['kind']
    if kind == 'faq':
        content = serializers.CharField(max_length=7500).run_validation(data.get('content', claims['content']))
        values = {'content': content}
    else:
        field = DiagnosticAnswerInput(data=data.get('answers'), many=True, allow_empty=False, max_length=10)
        field.is_valid(raise_exception=True)
        answers = field.validated_data
        ids = [row['question']['id'] for row in answers]
        if len(ids) != len(set(ids)) or set(ids) != set(claims['question_ids']):
            raise ValidationError('须提交本次诊断的全部题目，不能替换或重复题目。')
        values = {'answers': answers}
    fingerprint = hashlib.sha256(json.dumps([kind, values], sort_keys=True).encode()).hexdigest()
    with site_request_lock(user), quota_write_lock(), transaction.atomic():
        actor = get_user_model().objects.select_for_update().get(pk=user.pk)
        existing = DshSubmission.objects.filter(request_id=claims['request_id']).first()
        if existing:
            if existing.user_id != user.pk or existing.kind != kind or existing.fingerprint != fingerprint:
                raise Conflict()
            return existing.response
        if claims['expires_at'] < time.time():
            raise ValidationError('本次诊断或草稿已超时，请重新准备；未提交任何结果。')
        if claims.get('source'):
            source = AIUsageReservation.objects.filter(pk=claims['source'], user=user, status='succeeded').first()
            if not source or source.response.get('engine') != 'dsh' or source.response.get('deleted'):
                raise Conflict('原提问未完成或已删除，请重新准备草稿。')
        if kind == 'faq':
            from faq_system.models import Question
            question = Question.objects.create(user=user, content=content, institution_id=get_content_institution_id())
            result = {'kind': kind, 'ticket_id': question.pk, 'message': '已发布人工答疑问题。', 'link': '/qa'}
        else:
            if actor.has_completed_initial_assessment:
                raise Conflict('首次诊断已完成，请到诊断页重新评估。')
            results, scores = grade_diagnostic_answers(answers)
            initialize_memorix_from_diagnostic(actor, scores)
            actor.has_completed_initial_assessment = True
            actor.save(update_fields=['has_completed_initial_assessment'])
            result = {'kind': kind, 'total_score': sum(row['is_correct'] for row in results),
                      'total_questions': len(results), 'results': results}
        DshSubmission.objects.create(user=user, request_id=claims['request_id'], kind=kind,
                                     fingerprint=fingerprint, response=result)
        return result
