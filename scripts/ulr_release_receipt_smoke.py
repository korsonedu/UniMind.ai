"""Exercise permission changes on saved receipts through the packaged HTTP service."""

import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


def main():
    from os import environ

    import django

    environ.setdefault('DJANGO_SETTINGS_MODULE', 'school_system.settings')
    django.setup()

    from ai_assistant.models import AIChatMessage, Bot, Conversation
    from ai_assistant.services.ulr_config import standalone_ulr
    from ai_assistant.views import _reserve_chat_request
    from courses.models import Course, VideoTranscript
    from notes.models import ConversationNoteReference, Note
    from quizzes.models import PracticeSubmission, Question
    from users.learning import confirm_ai_call
    from users.login_sessions import LoginSession
    from users.models import CourseStudentStatus, User, WeeklyAIQuotaConfig, WeeklyAIUsage

    assert standalone_ulr()
    user = User.objects.create_user(username=f'receipt-smoke-{uuid4().hex}')
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    WeeklyAIQuotaConfig.objects.update_or_create(pk=1, defaults={'course_calls': 20})
    bot, _ = Bot.objects.get_or_create(is_xiaoyu=True, defaults={'name': '小宇', 'bot_type': 'planner'})
    conversation = Conversation.objects.create(user=user, bot=bot, conversation_id=uuid4(), title='合成回执')
    course = Course.objects.create(title='合成回执课程', is_published=True)
    transcript = VideoTranscript.objects.create(course=course, asr_status='completed')
    note = Note.objects.create(user=user, title='合成回执笔记')
    ConversationNoteReference.objects.create(user=user, bot=bot, conversation=conversation, note=note)
    question = Question.objects.create(text='合成回执练习题', options=['甲', '乙'], correct_answer='A')
    body = {'request_id': str(uuid4()), 'conversation_id': str(conversation.conversation_id),
            'bot_id': bot.pk, 'message': '继续原讲解。'}
    answer = AIChatMessage.objects.create(user=user, bot=bot, conversation_id=conversation.conversation_id,
        role='assistant', content='SYNTHETIC_RELEASE_RECEIPT', metadata={'engine': 'ulr', 'ulr_context_sources': {
            'courses': [course.pk], 'transcripts': [[course.pk, transcript.pk, transcript.revision]],
            'notes': [[note.pk, note.version]], 'question_answers': [question.pk],
        }})
    receipt = {'engine': 'ulr', 'done': True, 'message_id': answer.pk, 'full_content': answer.content}
    reservation = _reserve_chat_request(user, body, bot, conversation_id=conversation.conversation_id)
    confirm_ai_call(reservation, response=receipt)
    token = LoginSession.issue(user)
    headers = {'X-Forwarded-Proto': 'https', 'Authorization': f'Token {token.key}', 'Content-Type': 'application/json'}

    def fetch(path, data=None):
        return urlopen(Request(f'http://localhost:8000{path}', headers=headers, data=data), timeout=10)

    request_body = json.dumps(body, ensure_ascii=False).encode()
    status_path = f"/api/ai/chat-requests/{body['request_id']}/"
    with fetch(status_path) as response:
        assert json.load(response)['response'] == receipt

    def denied(detail, status):
        with fetch(status_path) as response:
            recovery = json.load(response)
        assert recovery['status'] == 'failed' and detail in recovery['response']['full_content']
        try:
            with fetch('/api/ai/chat/', request_body):
                raise AssertionError('Polling returned a revoked receipt')
        except HTTPError as error:
            failure = json.load(error)
            assert error.code == status and detail in str(failure)
        with fetch('/api/ai/chat/stream/', request_body) as response:
            events = [json.loads(line[6:]) for line in response if line.startswith(b'data: ')]
        assert events[-1]['is_error'] and detail in events[-1]['full_content']
        assert answer.content not in str((recovery, failure, events))

    Course.objects.filter(pk=course.pk).update(is_published=False)
    denied('引用课程已不可访问', 403)
    Course.objects.filter(pk=course.pk).update(is_published=True)
    Note.objects.filter(pk=note.pk).update(version=note.version + 1)
    denied('引用笔记已更新', 400)
    Note.objects.filter(pk=note.pk).update(version=note.version)
    PracticeSubmission.objects.create(user=user, session_id=uuid4(), answers_hash='',
        response={'ulr_practice': {'source': reservation.pk, 'question_ids': [question.pk]}})
    denied('原题已进入正式练习', 403)
    reservation.refresh_from_db()
    assert reservation.status == 'succeeded' and reservation.response == receipt
    assert WeeklyAIUsage.objects.get(user=user).ai_calls == 1
    print('Packaged XiaoYu receipt smoke passed for course, note and practice sources.')


if __name__ == '__main__':
    main()
