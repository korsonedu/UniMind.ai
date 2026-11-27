"""L4 View Layer — extended Learning Memory MCP tools (Memorix reviews, practice prep, note writes)."""

from uuid import uuid4

from django.core.cache import cache
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed, NotFound, ValidationError

from ai_assistant.models import LearningMemoryCheckpoint, LearningMemoryGrant
from ai_assistant.services.memory_system import MemorySystem
from ai_assistant.services.runtime.learning_memory_oauth import digest as _digest
from core.utils import get_content_institution
from notes.awareness import after_note_save
from notes.links import index_links
from notes.models import Note, Tag


DUE_REVIEWS_TOOL = {
    'name': 'get_due_reviews',
    'description': '查询当前学习空间在 Memorix 记忆调度下今日到期待复习的题目与优先度。',
    'inputSchema': {
        'type': 'object',
        'properties': {
            'limit': {'type': 'integer', 'minimum': 1, 'maximum': 50, 'default': 10, 'description': '返回的最大待复习题目数'},
        },
        'additionalProperties': False,
    },
    'annotations': {'readOnlyHint': True, 'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': False},
}

START_PRACTICE_TOOL = {
    'name': 'start_weak_point_practice',
    'description': '按薄弱知识点、学科或关键词抽取一组练习题并生成 UniMind 站内作答链接。不修改正式成绩或掌握度。',
    'inputSchema': {
        'type': 'object',
        'properties': {
            'topic': {'type': 'string', 'maxLength': 120, 'description': '可选，知识点或主题关键词；留空时自动优先薄弱知识点'},
            'subject': {'type': 'string', 'maxLength': 80, 'description': '可选，学科名称'},
            'difficulty': {'type': 'string', 'enum': ['easy', 'medium', 'hard'], 'description': '可选，题目难度'},
            'count': {'type': 'integer', 'minimum': 1, 'maximum': 10, 'default': 5, 'description': '抽取题量（1-10）'},
        },
        'additionalProperties': False,
    },
    'annotations': {'readOnlyHint': True, 'destructiveHint': False, 'idempotentHint': False, 'openWorldHint': False},
}

SAVE_NOTE_TOOL = {
    'name': 'save_learning_note',
    'description': '经学生确认后，在 UniMind 个人笔记中新建学习笔记，或向已有笔记末尾追加内容。需同时具备写权限和笔记权限。',
    'inputSchema': {
        'type': 'object',
        'properties': {
            'mode': {'type': 'string', 'enum': ['create', 'append'], 'default': 'create'},
            'title': {'type': 'string', 'maxLength': 200, 'description': '新建笔记时必填标题'},
            'content': {'type': 'string', 'minLength': 1, 'maxLength': 8000, 'description': '笔记正文或追加内容（Markdown）'},
            'note_id': {'type': 'integer', 'minimum': 1, 'description': 'mode=append 时必填目标笔记 ID'},
            'tags': {
                'type': 'array',
                'maxItems': 8,
                'items': {'type': 'string', 'minLength': 1, 'maxLength': 40},
                'description': '可选，标签列表',
            },
            'request_id': {'type': 'string', 'format': 'uuid', 'description': '幂等请求 ID'},
        },
        'required': ['content', 'request_id'],
        'additionalProperties': False,
    },
    'annotations': {'readOnlyHint': False, 'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': False},
}


class DueReviewsInput(serializers.Serializer):
    limit = serializers.IntegerField(min_value=1, max_value=50, default=10)


class StartPracticeInput(serializers.Serializer):
    topic = serializers.CharField(max_length=120, allow_blank=True, default='')
    subject = serializers.CharField(max_length=80, allow_blank=True, default='')
    difficulty = serializers.ChoiceField(choices=['easy', 'medium', 'hard'], required=False, allow_blank=True, default='')
    count = serializers.IntegerField(min_value=1, max_value=10, default=5)


class SaveNoteInput(serializers.Serializer):
    mode = serializers.ChoiceField(choices=['create', 'append'], default='create')
    title = serializers.CharField(max_length=200, allow_blank=True, default='')
    content = serializers.CharField(min_length=1, max_length=8000)
    note_id = serializers.IntegerField(min_value=1, required=False)
    tags = serializers.ListField(
        child=serializers.CharField(min_length=1, max_length=40),
        max_length=8,
        required=False,
        default=list,
    )
    request_id = serializers.UUIDField()

    def validate(self, attrs):
        if attrs['mode'] == 'create' and not attrs.get('title', '').strip():
            raise serializers.ValidationError({'title': '新建笔记时必须提供标题。'})
        if attrs['mode'] == 'append' and not attrs.get('note_id'):
            raise serializers.ValidationError({'note_id': '追加模式必须提供 note_id。'})
        return attrs


def run_due_reviews(user, *, limit=10):
    institution = get_content_institution(user)
    data = MemorySystem.query_due_reviews(user, limit=limit, institution=institution)
    return {
        'due_count': data.get('due_count', 0),
        'interval_policy': data.get('interval_policy', 'memorix'),
        'reviews': data.get('reviews', []),
        'href': '/tests/review',
    }


def run_start_practice(user, *, topic='', subject='', difficulty='', count=5):
    institution = get_content_institution(user)
    target_kp = topic.strip()
    weak_points_used = []
    if not target_kp and not subject.strip():
        weak = MemorySystem.query_weak_points(user, institution=institution).get('weak_points', [])
        if weak:
            weak_points_used = [item['kp_name'] for item in weak[:3] if item.get('kp_name')]
            target_kp = weak[0].get('kp_name') or ''

    result = MemorySystem.query_practice_questions(
        user=user,
        kp_name=target_kp,
        subject=subject.strip(),
        difficulty=difficulty.strip(),
        limit=count,
        institution=institution,
    )
    questions = result.get('questions', [])
    if not questions and target_kp and not topic.strip():
        result = MemorySystem.query_practice_questions(
            user=user,
            kp_name='',
            subject=subject.strip(),
            difficulty=difficulty.strip(),
            limit=count,
            institution=institution,
        )
        questions = result.get('questions', [])

    if not questions:
        return {
            'session_id': None,
            'total_questions': 0,
            'weak_points_used': weak_points_used,
            'questions': [],
            'message': '当前没有匹配的练习题。',
        }

    session_id = uuid4().hex
    cache.set(
        f'practice:session:{session_id}',
        {
            'user_id': user.id,
            'questions': questions,
            'created_at': timezone.now().isoformat(),
        },
        timeout=86400,
    )
    sanitized = [
        {
            'id': q['id'],
            'text': (q.get('text') or '')[:400],
            'q_type': q.get('q_type') or 'objective',
            'subjective_type': q.get('subjective_type') or '',
            'options': q.get('options') or [],
            'kp_name': q.get('kp_name') or '',
            'difficulty': q.get('difficulty') or '',
        }
        for q in questions
    ]
    return {
        'session_id': session_id,
        'total_questions': len(sanitized),
        'total_time_estimate': len(sanitized) * 90,
        'weak_points_used': weak_points_used,
        'questions': sanitized,
        'href': f'/tests/session?session_id={session_id}',
    }


def _attach_tags(user, note, tag_names):
    cleaned = list(dict.fromkeys(name.strip() for name in tag_names if name and name.strip()))
    if not cleaned:
        return
    tag_objs = [Tag.objects.get_or_create(user=user, name=name)[0] for name in cleaned]
    note.tags.add(*tag_objs)


def run_save_learning_note(user, grant, *, mode, title, content, request_id, note_id=None, tags=None):
    tags = tags or []
    payload_digest = _digest(f'{mode}|{note_id or ""}|{title.strip()}|{content}|{",".join(sorted(tags))}')
    request_key = _digest(f'memory-note:{grant.pk}:{request_id}')

    with transaction.atomic():
        valid = LearningMemoryGrant.objects.select_for_update().filter(
            pk=grant.pk,
            digest=grant.digest,
            expires_at__gt=timezone.now(),
            learner_id=user.pk,
            can_write=True,
            share_notes=True,
        ).first()
        if not valid:
            raise AuthenticationFailed('学习记忆笔记写入授权已撤销或到期。')

        existing = LearningMemoryCheckpoint.objects.select_for_update().filter(request_key=request_key).first()
        if existing:
            meta = existing.content or {}
            if meta.get('payload_digest') != payload_digest:
                raise ValidationError('Request ID already used for different note payload')
            saved_note = Note.objects.filter(pk=meta.get('note_id'), user=user).first()
            return {
                'source': f"note:{meta['note_id']}",
                'note_id': meta['note_id'],
                'title': saved_note.title if saved_note else meta.get('title', ''),
                'version': saved_note.version if saved_note else meta.get('version', 1),
                'mode': meta.get('mode', mode),
                'href': f"/notes/{meta['note_id']}",
            }

        if mode == 'create':
            note = Note.objects.create(user=user, title=title.strip()[:200], content=content)
            _attach_tags(user, note, tags)
        else:
            note = Note.objects.select_for_update().filter(pk=note_id, user=user, deleted_at__isnull=True).first()
            if not note:
                raise NotFound('目标笔记不存在或无权访问。')
            appended = f'{note.content.rstrip()}\n\n{content}' if note.content.strip() else content
            Note.objects.filter(pk=note.pk, user=user).update(
                content=appended,
                version=F('version') + 1,
                updated_at=timezone.now(),
            )
            note.refresh_from_db()
            _attach_tags(user, note, tags)

        index_links(note)
        after_note_save(note)

        LearningMemoryCheckpoint.objects.create(
            learner=user,
            request_key=request_key,
            content={
                'agent': grant.name,
                'kind': 'note_write',
                'mode': mode,
                'note_id': note.pk,
                'title': note.title,
                'version': note.version,
                'payload_digest': payload_digest,
                'text': f'通过外部 Agent {"新建" if mode == "create" else "补充"}笔记「{note.title or "未命名笔记"}」',
            },
        )
        return {
            'source': f'note:{note.pk}',
            'note_id': note.pk,
            'title': note.title,
            'version': note.version,
            'mode': mode,
            'href': f'/notes/{note.pk}',
        }
