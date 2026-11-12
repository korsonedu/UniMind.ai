"""Owned source snapshots and traceable teaching methods; no cross-user promotion."""
import hashlib
import json
from uuid import uuid4
from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from ai_assistant.models import (
    AIChatMessage, Conversation, ProjectLearning, ProjectLearningEvent, LearningResource,
    LearningStrategy, LearningStrategyUse, LearningStrategyReview, LearningResourceVersion,
)
from .project_learning import LearningConflict, assert_learning_turn
from .learning_resources import store_resource


class LibraryInput(serializers.Serializer):
    action = serializers.CharField(max_length=30)
    query = serializers.CharField(max_length=200, allow_blank=True, required=False)
    domain = serializers.CharField(max_length=100, allow_blank=True, required=False)
    topic = serializers.CharField(max_length=200, allow_blank=True, required=False)
    level = serializers.CharField(max_length=80, allow_blank=True, required=False)
    edition = serializers.CharField(max_length=80, allow_blank=True, required=False)
    source_id = serializers.CharField(max_length=60, required=False)
    resource_id = serializers.IntegerField(min_value=1, required=False)
    event_id = serializers.IntegerField(min_value=1, required=False)
    strategy_id = serializers.IntegerField(min_value=1, required=False)
    use_id = serializers.IntegerField(min_value=1, required=False)
    revision = serializers.IntegerField(min_value=1, required=False)
    reason = serializers.CharField(max_length=2000, required=False)
    judgement = serializers.ChoiceField(choices=['support', 'against', 'uncertain'], required=False)


def validate(data):
    serializer = LibraryInput(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def resource_data(row, *, compact=False):
    version = row.versions.order_by('-revision').first()
    origin = {key: version.snapshot[key] for key in ('source_kind', 'content_version', 'references', 'not_web_read') if version and key in version.snapshot}
    return origin | {key: getattr(row, key) for key in ('id', 'url', 'title', 'read_at', 'domain', 'topic', 'level', 'edition',
                                               'is_archived', 'revision')} | {'read_at': row.read_at.isoformat(), 'excerpt': row.excerpt[:500] if compact else row.excerpt}


def event_data(event):
    return {'id': event.pk, 'project_id': event.project_id, 'created_at': event.created_at,
            'observation': event.content.get('observation', ''), 'assistance': event.content.get('assistance', 'unknown'),
            'source': event.message.content[:2000] if event.message else None,
            'conversation_id': str(event.message.conversation_id) if event.message else None}


def strategy_data(row, *, compact=False):
    checks = LearningStrategyReview.objects.filter(use__strategy=row).select_related('evidence_event__message').order_by('-id')
    reviews = (list(checks.filter(judgement='against', evidence_event__message__isnull=False)[:2]) +
               list(checks.exclude(judgement='against').filter(evidence_event__message__isnull=False)[:1])) if compact else list(checks[:10])
    counts = {kind: getattr(row, f'{kind}_count', 0) for kind in ('support', 'against', 'uncertain')}
    source = event_data(row.source_event)
    if compact:
        source['source'] = source['source'][:500] if source['source'] else None
        source['observation'] = source['observation'][:500]
    background = row.source_event.content.get('context', {})
    if compact:
        background = {key: str(value)[:300] for key, value in background.items()}
    return {'id': row.pk, 'method': str(row.source_event.content.get('strategy', ''))[:1000 if compact else 2000],
            'domain': row.domain, 'topic': row.topic, 'context': background,
            'available': not row.is_retired and bool(row.source_event.message_id), 'is_retired': row.is_retired,
            'revision': row.revision, 'counts': counts, 'source': source,
            'reviews': [{'judgement': review.judgement, 'reason': review.reason[:600] if compact else review.reason,
                'evidence': _review_evidence(review.evidence_event, compact)} for review in reviews],
            'notice': '候选教学方法；后续观察不能证明普遍有效，也不代表正式成绩。'}


def _review_evidence(event, compact):
    data = event_data(event)
    if compact:
        data['source'] = data['source'][:500] if data['source'] else None
        data['observation'] = data['observation'][:500]
    return data


def strategy_rows(user):
    return LearningStrategy.objects.filter(user=user).select_related('source_event__message').annotate(**{
        f'{kind}_count': Count('uses__reviews', filter=Q(uses__reviews__judgement=kind, uses__reviews__evidence_event__message__isnull=False))
        for kind in ('support', 'against', 'uncertain')})


def library_data(user, query='', domain='', *, compact=False):
    resources = LearningResource.objects.filter(user=user)
    strategies = strategy_rows(user)
    if query:
        resources = resources.filter(Q(title__icontains=query) | Q(topic__icontains=query) | Q(domain__icontains=query) | Q(edition__icontains=query))
        strategies = strategies.filter(Q(source_event__content__strategy__icontains=query) | Q(topic__icontains=query) | Q(domain__icontains=query))
    if domain:
        resources = resources.filter(domain__icontains=domain)
        strategies = strategies.filter(domain__icontains=domain)
    if compact:
        resources = resources.filter(is_archived=False)
        strategies = strategies.filter(is_retired=False, source_event__message__isnull=False)
    return {'resources': [resource_data(row, compact=compact) | ({} if compact else {'versions': list(row.versions.order_by('-revision').values('revision', 'created_at')[:10])}) for row in resources.order_by('-updated_at')[:20 if not compact else 8]],
            'strategies': [strategy_data(row, compact=compact) for row in strategies.order_by('-id')[:20 if not compact else 3]]}


def _state(project, message):
    state, _ = ProjectLearning.objects.get_or_create(project=project)
    state = ProjectLearning.objects.select_for_update().get(pk=state.pk)
    if message:
        if not Conversation.objects.filter(user=project.user, conversation_id=message.conversation_id, project=project).exists():
            raise PermissionDenied('对话所属项目已变化。')
        assert_learning_turn(project, message)
    return state


def _revision(row, data):
    if data.get('revision') != row.revision:
        raise LearningConflict('资料或方法已变化，请重新读取后操作。')


def _keep_version(row):
    LearningResourceVersion.objects.get_or_create(resource=row, revision=row.revision,
        defaults={'snapshot': json.loads(json.dumps(resource_data(row), default=str))})


@transaction.atomic
def resource_operation(project, arguments, *, message=None):
    data = validate(arguments)
    if data['action'] == 'search':
        return {'resources': library_data(project.user, data.get('query', ''), data.get('domain', ''), compact=True)['resources']}
    state = _state(project, message)
    if data['action'] == 'save':
        source = next((item for item in state.resources if item['id'] == data.get('source_id')), None)
        if not source:
            raise ValidationError('只能保存当前项目实际读取的来源，请先读取原文。')
        values = {key: source[key] for key in ('url', 'title', 'excerpt', 'read_at')}
        values['read_at'] = serializers.DateTimeField().run_validation(values['read_at'])
        values.update({key: data[key] for key in ('domain', 'topic', 'level', 'edition') if key in data})
        row, created = LearningResource.objects.get_or_create(user=project.user, url_hash=hashlib.sha256(source['url'].encode()).hexdigest(), defaults=values)
        if not created and 'revision' in data:
            row = LearningResource.objects.select_for_update().get(pk=row.pk)
            _revision(row, data)
            if values['read_at'] < row.read_at:
                raise LearningConflict('项目保留的是较早来源，不能覆盖资料库的新版本。')
            _keep_version(row)
            for key, value in values.items():
                setattr(row, key, value)
            row.revision += 1
            row.save()
        _keep_version(row)
        return {'resource': resource_data(row), 'created': created}
    row = get_object_or_404(LearningResource.objects.select_for_update(), pk=data.get('resource_id'), user=project.user)
    if data['action'] == 'attach':
        if row.is_archived:
            raise ValidationError('这份资料已归档，请先恢复或选择其他来源。')
        existing = next((item for item in state.resources if item['url'] == row.url), None)
        if existing:
            return {'resource': existing, 'notice': '项目已有这份资料的快照，保留原引用；需要更新时请重新读取原文。'}
        source = {key: getattr(row, key) for key in ('url', 'title', 'excerpt', 'domain', 'topic', 'level', 'edition')}
        source.update({key: value for key, value in resource_data(row).items() if key in ('source_kind', 'content_version', 'references', 'not_web_read')})
        source.update(id=uuid4().hex, read_at=row.read_at.isoformat(), library_id=row.pk, library_revision=row.revision)
        return store_resource(project, source) | {'notice': '沿用此前读取的快照，未重新核验网页时效。'}
    if message or data['action'] not in ('update', 'archive', 'restore'):
        raise ValidationError('不支持的资料操作。')
    _revision(row, data)
    _keep_version(row)
    if data['action'] == 'update':
        for key in ('domain', 'topic', 'level', 'edition'):
            if key in data:
                setattr(row, key, data[key])
    else:
        row.is_archived = data['action'] == 'archive'
    row.revision += 1
    row.save()
    _keep_version(row)
    return {'resource': resource_data(row)}


@transaction.atomic
def strategy_operation(project, arguments, *, message=None):
    data = validate(arguments)
    action = data['action']
    if action == 'search':
        return {'strategies': library_data(project.user, data.get('query', ''), data.get('domain', ''), compact=True)['strategies']}
    _state(project, message)
    if action == 'save':
        event = get_object_or_404(ProjectLearningEvent.objects.select_related('message'), pk=data.get('event_id'),
                                 project=project, kind='progress', message__user=project.user, message__role='user')
        if not str(event.content.get('strategy', '')).strip():
            raise ValidationError('这条实际表现还没有记录教学方法。')
        row, created = LearningStrategy.objects.get_or_create(source_event=event,
            defaults={'user': project.user, 'domain': data.get('domain', ''), 'topic': data.get('topic', '')})
        return {'strategy_id': row.pk, 'created': created, 'notice': '已留下带来源的候选方法，仍需后续表现检验。'}
    if action == 'review':
        use = get_object_or_404(LearningStrategyUse.objects.select_related('strategy__source_event__message', 'message'),
                               pk=data.get('use_id'), project=project, strategy__user=project.user)
        event = get_object_or_404(ProjectLearningEvent.objects.select_related('message'), pk=data.get('event_id'), project=project,
                                 kind='progress', message__user=project.user, message__role='user')
        if not message or event.message_id != message.pk or event.message_id == use.message_id or event.message.timestamp <= use.message.timestamp:
            raise ValidationError('评估必须来自试用之后另一轮实际提问的表现。')
        reply = AIChatMessage.objects.filter(user=project.user, bot_id=use.message.bot_id, conversation_id=use.message.conversation_id,
            role='assistant', metadata__learning_turn__message_id=use.message_id, metadata__learning_turn__completed=True).first()
        completed_at = serializers.DateTimeField().run_validation(reply.metadata['learning_turn']['completed_at']) if reply else None
        if not completed_at or completed_at >= event.message.timestamp:
            raise ValidationError('还没有本次试用提问已完成的讲解记录，暂不能把这次回答归为方法后续结果。')
        if not use.strategy.source_event.message_id:
            raise ValidationError('原始依据已删除，不能继续评估这项方法。')
        judgement = data.get('judgement')
        if judgement not in ('support', 'against', 'uncertain') or not data.get('reason'):
            raise ValidationError('请给出观察方向和判断依据。')
        if judgement == 'support' and event.content.get('assistance') != 'independent':
            raise ValidationError('获得提示或尚不清楚帮助程度的表现只能记为待检验，不能当作独立支持。')
        review = LearningStrategyReview.objects.filter(use=use, evidence_event__message_id=event.message_id).first()
        created = review is None
        if created:
            review = LearningStrategyReview.objects.create(use=use, evidence_event=event, judgement=judgement, reason=data['reason'])
        if review.judgement != judgement or review.reason != data['reason']:
            raise LearningConflict('这条表现已有判断；请通过新的实际反馈补充或纠正，不覆盖原记录。')
        return {'review_id': review.pk, 'created': created, 'judgement': review.judgement,
                'notice': '这是有来源的后续观察，不证明教学方法普遍有效。'}
    row = get_object_or_404(LearningStrategy.objects.select_for_update().select_related('source_event'),
                           pk=data.get('strategy_id'), user=project.user)
    if action == 'apply':
        if not message or row.is_retired or not row.source_event.message_id or not data.get('reason'):
            raise ValidationError('请在实际项目对话中试用仍有原始依据的方法，并说明适用原因。')
        use, created = LearningStrategyUse.objects.get_or_create(strategy=row, message=message,
            defaults={'project': project, 'reason': data['reason']})
        return {'use_id': use.pk, 'created': created, 'method': row.source_event.content['strategy'],
                'notice': '只登记本轮试用意图；等后续另一轮实际表现再检查结果。'}
    if message or action not in ('retire', 'restore'):
        raise ValidationError('不支持的方法操作。')
    _revision(row, data)
    row.is_retired = action == 'retire'
    row.revision += 1
    row.save(update_fields=['is_retired', 'revision'])
    return {'strategy_id': row.pk, 'is_retired': row.is_retired, 'revision': row.revision}


def project_strategy_uses(project):
    uses = LearningStrategyUse.objects.filter(project=project, strategy__user=project.user,
        strategy__is_retired=False, strategy__source_event__message__isnull=False).select_related('strategy__source_event').annotate(
            reviewed=Exists(LearningStrategyReview.objects.filter(use_id=OuterRef('pk'))))
    return [{'id': use.pk, 'method': use.strategy.source_event.content['strategy'][:800], 'reason': use.reason[:400],
             'trigger_message_id': use.message_id, 'reviewed': use.reviewed, 'created_at': use.created_at}
            for use in uses.order_by('-id')[:5]]
