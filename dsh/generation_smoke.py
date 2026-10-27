"""Native SDK/internal generation and scoped teaching jobs, synthetic data only."""
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4

from smoke import ROOT, fixture_database, model_fixture


def backend_smoke():
    database = fixture_database()
    os.environ.update(DB_ENGINE='django.db.backends.sqlite3', DB_NAME=database)
    sys.path.insert(0, str(ROOT / 'backend'))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school_system.settings')
    import django
    django.setup()
    from django.core.management import call_command
    from ai_assistant.models import Bot, Conversation, AIChatMessage
    from ai_engine.service import AIEngine
    from backoffice.tasks import run_teaching_task
    from quizzes.models import ContentPipelineTask, KnowledgePoint, Question
    from quizzes.services.adversarial_pipeline import _reviewer_evaluate
    from users.models import User
    call_command('migrate', interactive=False, verbosity=0)
    admin = User.objects.create_superuser(username='generation-synthetic-admin')
    other = User.objects.create_superuser(username='generation-synthetic-admin-two')
    from django.conf import settings
    settings.UNIMIND_DIRECTUS_ADMIN_MAP = {str(uuid4()): admin.pk, str(uuid4()): other.pk}
    kp = KnowledgePoint.objects.create(name='合成久期', code='SYNTHETIC-DURATION', level='kp')
    task = ContentPipelineTask.objects.create(created_by=admin, title='合成出题',
        payload={'kind': 'quick', 'kp_ids': [kp.pk], 'count': 1})
    run_teaching_task(task.pk)
    task.refresh_from_db()
    assert task.status == 'review' and len(task.result['questions']) == 1, task.error_message
    assert not Question.objects.exists()
    review = _reviewer_evaluate(task.result['questions'][0], strict_scope=True)
    assert review['score'] == .8, review
    bot = Bot.objects.create(name='合成教研助手', bot_type='exam_generator')
    conversation = Conversation.objects.create(user=admin, bot=bot, conversation_id=uuid4())
    chat = ContentPipelineTask.objects.create(created_by=admin, title='合成教研', payload={
        'kind': 'chat', 'bot_id': bot.pk, 'conversation_id': str(conversation.conversation_id), 'message': '内部教研工具发现'})
    run_teaching_task(chat.pk)
    chat.refresh_from_db()
    assert chat.status == 'completed', chat.error_message
    assert chat.result['content'] == '合成内容已整理'
    assert AIChatMessage.objects.count() == 2 and not Question.objects.exists()
    response = AIEngine.call_ai([{'role': 'user', 'content': '内部辅助生成'}], operation='notes.understanding')
    assert response['choices'][0]['message']['content'] == '合成内容已整理'
    assert AIEngine.structured_output([], {'type': 'array', 'items': {'type': 'string'}}, tool_name='submit_result', operation='courses.generate_outline') == ['合成数组']
    print('RESULT ' + json.dumps({'author_draft': True, 'reviewer_research': True,
        'teaching_discovery': True, 'teaching_chat_saved': True, 'internal_text_and_array': True,
        'published_questions': Question.objects.count()}))


def main():
    if '--backend-fixture' in sys.argv:
        backend_smoke()
        return
    model, calls = model_fixture()

    def response(body):
        names = {tool['name'] for tool in body.get('tools', [])}
        results = [block for message in body['messages'] if isinstance(message['content'], list)
                   for block in message['content'] if block.get('type') == 'tool_result']
        if 'submit_questions' in names:
            return [('submit_questions', {'questions': [{'question': '合成久期题', 'q_type': 'subjective',
                'subjective_type': 'short', 'options': None, 'answer': '合成答案',
                'grading_points': ['合成要点'], 'difficulty_level': 'normal'}]})]
        if 'submit_review' in names:
            if not results:
                return [('lookup_knowledge_point_definition', {'code': 'SYNTHETIC-DURATION'})]
            return [('submit_review', {'score': .8, 'feedback': '合成评阅通过',
                'dimensions': dict(discrimination=.8, clarity=.8, coverage=.8)})]
        if 'find_teaching_tools' in names:
            if not results:
                return [('find_teaching_tools', {'group': '1'})]
            if len(results) == 1:
                assert 'list_articles' in names
                return [('list_articles', {})]
        if 'submit_result' in names:
            return [('submit_result', {'questions': ['合成数组']})]
        return [('submit_text', {'text': '合成内容已整理'})]

    model.tool_response = response
    try:
        with TemporaryDirectory(prefix='unimind-m0-smoke-') as state:
            environment = {**os.environ, 'ACCOUNT_ENABLED': 'false', 'ACCOUNT_RSA_KEY_PATH': '',
                'ACCOUNT_DEV_LOCAL_CACHE': 'true', 'DJANGO_ENV': 'development', 'DEBUG': 'true',
                'UNIMIND_CONTENT_INSTITUTION_ID': 'global', 'UNIMIND_DSH_TEACHING_ENABLED': 'true',
                'UNIMIND_DSH_GENERATION_ENABLED': 'true', 'UNIMIND_DSH_PYTHON': sys.executable,
                'UNIMIND_DSH_STATE_DIR': str(Path(state) / 'tasks'),
                'UNIMIND_M0_FIXTURE_DIR': state, 'UNIMIND_M0_FIXTURE_DB': str(Path(state) / 'db.sqlite3'),
                'UNIMIND_DSH_FIXTURE_URL': f'http://127.0.0.1:{model.server_port}/v1/messages'}
            python = sys.argv[sys.argv.index('--backend-python') + 1]
            result = subprocess.run([python, __file__, '--backend-fixture'], env=environment,
                capture_output=True, text=True, timeout=240)
            if result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
            assert len(calls) == 8, len(calls)
            assert max(len(body['tools']) for body in calls) <= 8
            assert all('render_visual' not in {tool['name'] for tool in body['tools']} for body in calls)
            assert calls[1]['thinking']['type'] == 'enabled' and calls[1]['output_config']['effort'] == 'high'
            print(next(line for line in result.stdout.splitlines() if line.startswith('RESULT ')))
            print(json.dumps({'native_requests': len(calls), 'max_visible_tools': max(len(body['tools']) for body in calls)}))
    finally:
        model.shutdown()
        model.server_close()


if __name__ == '__main__':
    main()
