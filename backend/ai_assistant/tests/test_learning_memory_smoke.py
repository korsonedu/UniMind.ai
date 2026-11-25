from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from ai_assistant.models import (
    AIChatMessage, Bot, Conversation, ConversationProject, LearningKnowledgeMap, LearningKnowledgeVersion,
    LearningMemoryCheckpoint, ProjectLearning,
)
from ai_assistant.services.dsh_service import build_context, execute_tool
from ai_assistant.services.project_learning import turn_project_context
from courses.models import Course, CourseModule, VideoProgress
from notes.models import ConversationNoteReference, Note


@pytest.mark.django_db
def test_workspace_source_reads_keep_original_evidence_and_permissions(settings, user, auth_client, django_user_model):
    from courses.models import TranscriptSegment, VideoTranscript
    from quizzes.models import ExamQuestionResult, KnowledgePoint, Question, QuizExam, ReviewLog, UserQuestionStatus

    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    settings.UNIMIND_LEARNING_MEMORY_CONNECTORS = True
    user.is_member = True
    user.save(update_fields=['is_member'])
    point = KnowledgePoint.objects.create(name='现金流时点')
    question = Question.objects.create(knowledge_point=point, text='新版本题干', correct_answer='标准答案')
    exam = QuizExam.objects.create(user=user, status='partial', total_questions=2, graded_count=1, total_score=4, max_score=10)
    marked = ExamQuestionResult.objects.create(exam=exam, question=question, position=1, user_answer='今天的金额也折现。',
        score=4, max_score=10, feedback='把第 0 期当成第 1 期。', status='graded', error_type='timing',
        question_snapshot={'text': '旧版本题干', 'kp_name': point.name, 'label_source': 'model_rubric_grade'})
    pending = ExamQuestionResult.objects.create(exam=exam, position=2, user_answer='第二题原作答',
        score=0, max_score=10, feedback='内部批改状态', status='pending')
    wrong = UserQuestionStatus.objects.create(user=user, question=question, wrong_count=3, error_type='timing')
    review = ReviewLog.objects.create(user=user, knowledge_point=point, grade=2, elapsed_days=7, predicted_retrievability=.5)
    other = django_user_model.objects.create_user(username='another-source-owner')
    foreign = QuizExam.objects.create(user=other)
    course = Course.objects.create(title='现金流讲稿', is_published=True, courseware='handout.pdf',
        module=CourseModule.objects.create(name='开放课', is_public=True))
    VideoProgress.objects.create(user=user, course=course, last_position=52)
    transcript = VideoTranscript.objects.create(course=course, asr_status='completed', revision=3)
    TranscriptSegment.objects.bulk_create([TranscriptSegment(transcript=transcript, index=i,
        start_time=i * 10, end_time=(i + 1) * 10, text=f'现金流讲稿第 {i} 段') for i in range(9)])
    bot = Bot.objects.create(name='小宇')
    old = AIChatMessage.objects.create(user=user, bot=bot, conversation_id=uuid4(), role='assistant',
        content='先把第零期放在原点。' * 600 + '旧问答的结尾')
    private = AIChatMessage.objects.create(user=user, bot=bot, conversation_id=uuid4(), role='user',
        content='笔记引用私有段落', metadata={'notes_context_used': True})
    current = AIChatMessage.objects.create(user=user, bot=bot, conversation_id=uuid4(), role='user', content='接着上次学')
    issued = auth_client.post('/api/ai/learning-memory/grants/', {'name': '来源验收'}, format='json').data
    external = APIClient()

    def call(name, **arguments):
        response = external.post('/api/ai/learning-memory/mcp/', {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
            'params': {'name': name, 'arguments': arguments}}, format='json', HTTP_AUTHORIZATION=f"Bearer {issued['token']}")
        assert response.status_code == 200, response.content
        data = response.json()
        return data['result']['structuredContent'] if 'result' in data else data

    def read(source, **arguments):
        return call('read_learning_source', source=source, **arguments)

    sources = {row['source']: row['items'] for row in call('recall_learning')['practice_sources']}
    assert sources['practice'][0]['source'] == f'exam:{exam.pk}'
    assert sources['wrong_answers'][0]['wrong_count'] == 3
    assert sources['review_history'][0]['elapsed_days'] == 7
    exam_page = read(f'exam:{exam.pk}')
    assert exam_page['items'][0]['question_text'] == '旧版本题干'
    assert exam_page['items'][1]['score'] is None and not exam_page['items'][1]['feedback']
    assert read(f'answer:{marked.pk}')['answer']['user_answer'] == marked.user_answer
    assert read(f'answer:{pending.pk}')['answer']['is_correct'] is None
    assert read(f'wrong:{wrong.pk}')['error_type'] == 'timing'
    assert read(f'review:{review.pk}')['grade'] == 2
    assert 'error' in read(f'exam:{foreign.pk}')

    first = read(f'course:{course.pk}')
    assert first['revision'] == 3 and first['next_offset'] == 8
    assert first['href'] == f'http://testserver/course/{course.pk}?t=52' and first['materials'][0]['kind'] == 'courseware'
    assert read(f'course:{course.pk}', offset=8)['segments'][0]['index'] == 8
    assert read(f'conversation:{old.conversation_id}')['conversation'][0]['source'] == f'message:{old.pk}'
    offset = read(f'message:{old.pk}')['next_offset']
    assert read(f'message:{old.pk}', offset=offset)['conversation'][0]['text'].endswith('旧问答的结尾')
    assert 'error' in read(f'message:{private.pk}')
    claims = {'message_id': current.pk, 'conversation_id': str(current.conversation_id), 'bot_id': bot.pk}
    context = build_context(user, current.content, chat_context=claims)
    assert 'read_learning_source' in [item['function']['name'] for item in context['tools']]
    execute_tool(user, 'read_learning_source', {'source': f'course:{course.pk}'}, context['memory']['version'], chat_context=claims)
    AIChatMessage.objects.create(user=user, bot=bot, conversation_id=current.conversation_id, role='assistant', content='讲稿转述')
    course.is_published = False
    course.save(update_fields=['is_published'])
    assert 'error' in read(f'course:{course.pk}')
    assert 'error' in read(f'conversation:{current.conversation_id}')


@pytest.mark.django_db
def test_workspace_credentials_recall_across_projects_and_unlinked_records(settings, user, auth_client, django_user_model):
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    settings.UNIMIND_LEARNING_MEMORY_CONNECTORS = True
    first = ConversationProject.objects.create(user=user, name='复利')
    second = ConversationProject.objects.create(user=user, name='久期')
    other = django_user_model.objects.create_user(username='other-workspace-learner')
    foreign = ConversationProject.objects.create(user=other, name='私有项目')
    Note.objects.create(user=other, title='私有便笺', content='只属于另一个学习身份。')
    note = Note.objects.create(user=user, title='未关联笔记', content='现金流先画时间轴。')
    course = Course.objects.create(title='未关联课程', is_published=True,
        module=CourseModule.objects.create(name='公开课', is_public=True))
    VideoProgress.objects.create(user=user, course=course, last_position=52)
    bot = Bot.objects.create(name='小宇')
    message = AIChatMessage.objects.create(user=user, bot=bot, conversation_id=uuid4(), role='user', content='接着上次学')

    grants = '/api/ai/learning-memory/grants/'
    writer = auth_client.post(grants, {'name': 'Codex', 'can_write': True, 'share_notes': True}, format='json').data
    legacy = auth_client.post(f'/api/ai/projects/{first.pk}/learning-memory/grants/', {'name': '旧项目授权'}, format='json').data
    external = APIClient()

    def call(name, arguments, grant=writer):
        return external.post('/api/ai/learning-memory/mcp/', {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
            'params': {'name': name, 'arguments': arguments}}, format='json', HTTP_AUTHORIZATION=f"Bearer {grant['token']}")

    recall = call('recall_learning', {}).json()['result']['structuredContent']
    assert {row['id'] for row in recall['projects']} == {first.pk, second.pk}
    assert [(row['source'], row['position_seconds']) for row in recall['course_progress']] == [(f'course:{course.pk}', 52)]
    assert [row['source'] for row in recall['notes']] == [f'note:{note.pk}']
    assert call('recall_learning', {'project_id': second.pk}).json()['result']['structuredContent']['project']['id'] == second.pk
    assert 'error' in call('recall_learning', {'project_id': foreign.pk}).json()
    assert 'error' in call('recall_learning', {'project_id': second.pk}, legacy).json()

    args = {'text': '外部学到先画时间轴', 'request_id': str(uuid4())}
    result = call('record_learning_checkpoint', args).json()['result']['structuredContent']
    assert call('record_learning_checkpoint', args).json()['result']['structuredContent'] == result
    assert LearningMemoryCheckpoint.objects.filter(learner=user).count() == 1
    assert call('recall_learning', {}, legacy).json()['result']['structuredContent']['external_checkpoints'] == []
    claims = {'message_id': message.pk, 'conversation_id': str(message.conversation_id), 'bot_id': bot.pk}
    context = build_context(user, message.content, chat_context=claims)
    recovered = execute_tool(user, 'recall_learning', {}, context['memory']['version'], chat_context=claims)
    assert recovered['external_checkpoints'][0]['source'] == result['source']
    assert {row['id'] for row in auth_client.get(grants).data} == {writer['id'], legacy['id']}
    assert auth_client.delete(f"{grants}{writer['id']}/").status_code == 204
    assert call('recall_learning', {}).status_code == 401


@pytest.mark.django_db
def test_project_sources_and_cross_agent_checkpoint(settings, user, auth_client):
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    settings.UNIMIND_LEARNING_MEMORY_CONNECTORS = True
    project = ConversationProject.objects.create(user=user, name='复利')
    graph = LearningKnowledgeMap.objects.create(user=user, title='时间价值')
    version = LearningKnowledgeVersion.objects.create(knowledge_map=graph, revision=1,
        snapshot={'nodes': [{'id': 'discount', 'title': '折现', 'prerequisites': []}]})
    state = ProjectLearning.objects.create(project=project, plan={'goal': '会用折现', 'knowledge_path': {
        'version_id': version.pk, 'targets': ['discount'],
    }})
    bot = Bot.objects.create(name='小宇')
    old = Conversation.objects.create(user=user, bot=bot, project=project, conversation_id=uuid4())
    room = Conversation.objects.create(user=user, bot=bot, project=project, conversation_id=uuid4())
    module = CourseModule.objects.create(name='公开课', is_public=True)
    course = Course.objects.create(title='折现第一课', module=module, is_published=True)
    VideoProgress.objects.create(user=user, course=course, last_position=120)
    AIChatMessage.objects.create(user=user, bot=bot, conversation_id=old.conversation_id, role='user',
        content='为什么要折现？', metadata={'course_context': {'course_id': course.pk, 'video_seconds': 115, 'revision': 3}})
    current = AIChatMessage.objects.create(user=user, bot=bot, conversation_id=room.conversation_id,
        role='user', content='接着上次学')
    note = Note.objects.create(user=user, title='折现', content='折现要看现金流发生在哪一年。')
    unrelated = Note.objects.create(user=user, title='折现私人便笺', content='没有关联到这个项目。')
    ConversationNoteReference.objects.create(user=user, bot=bot, conversation=old, note=note)
    other_project = ConversationProject.objects.create(user=user, name='其他项目')
    other = Conversation.objects.create(user=user, bot=bot, project=other_project, conversation_id=uuid4())
    AIChatMessage.objects.create(user=user, bot=bot, conversation_id=other.conversation_id, role='user',
        content='折现 OTHER_PROJECT')

    knowledge_url = f'/api/ai/projects/{project.pk}/learning/knowledge/'
    assert auth_client.post(knowledge_url, {'action': 'remember_view', 'version_id': version.pk, 'node_id': 'discount'},
                            format='json').status_code == 204
    updated = LearningKnowledgeVersion.objects.create(knowledge_map=graph, revision=2, snapshot=version.snapshot)
    state.plan['knowledge_path']['version_id'] = updated.pk
    state.save(update_fields=['plan'])

    grants = f'/api/ai/projects/{project.pk}/learning-memory/grants/'
    writer = auth_client.post(grants, {'name': 'WorkBuddy', 'can_write': True}, format='json').data
    reader = auth_client.post(grants, {'name': 'Codex', 'share_notes': True}, format='json').data
    external = APIClient()
    endpoint = '/api/ai/learning-memory/mcp/'
    assert external.get(endpoint, HTTP_ACCEPT='text/event-stream',
                        HTTP_AUTHORIZATION=f"Bearer {reader['token']}").status_code == 405

    def rpc(credential, method, params=None):
        return external.post(endpoint, {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}},
                             format='json', HTTP_AUTHORIZATION=f"Bearer {credential['token']}")

    assert rpc(reader, 'initialize', {'protocolVersion': '2025-11-25'}).json()['result']['capabilities'] == {'tools': {}}
    assert [tool['name'] for tool in rpc(reader, 'tools/list').json()['result']['tools']] == ['recall_learning']
    params = {'name': 'record_learning_checkpoint', 'arguments': {'text': '折现练习已做，利率还有疑问', 'request_id': str(uuid4())}}
    assert 'error' in rpc(reader, 'tools/call', params).json()
    first = rpc(writer, 'tools/call', params).json()['result']['structuredContent']
    assert rpc(writer, 'tools/call', params).json()['result']['structuredContent'] == first
    assert project.learning_events.filter(kind='agent_checkpoint').count() == 1
    params = {'name': 'recall_learning', 'arguments': {'topic': '折现'}}
    result = rpc(reader, 'tools/call', params).json()['result']['structuredContent']
    assert result['project']['goal'] == '会用折现'
    assert result['knowledge']['nodes'][0]['id'] == 'discount'
    assert result['last_viewed_node']['version_id'] == updated.pk
    assert result['last_viewed_node']['original_version_id'] == version.pk
    assert not state.current_stage
    assert result['course_progress'][0]['position_seconds'] == 120
    assert rpc(writer, 'tools/call', params).json()['result']['structuredContent']['notes'] == []
    assert result['notes'][0]['source'] == f'note:{note.pk}'
    assert len(result['notes']) == 1 and unrelated.title not in str(result)
    assert len(result['conversation']) == 1
    assert result['conversation'][0]['course_segment']['video_seconds'] == 115
    assert result['external_checkpoints'][0]['agent'] == 'WorkBuddy'

    claims = {'message_id': current.pk, 'conversation_id': str(room.conversation_id), 'bot_id': bot.pk}
    context = build_context(user, current.content, chat_context=claims)
    assert context['routing']['initial_group'] == 'recall'
    dsh = execute_tool(user, 'recall_learning', {'topic': '折现'}, context['memory']['version'], chat_context=claims)
    assert dsh['external_checkpoints'][0]['source'] == first['source']
    assert dsh['notes'][0]['source'] == f'note:{note.pk}'
    AIChatMessage.objects.create(user=user, bot=bot, conversation_id=room.conversation_id,
        role='assistant', content='继续之前先回看这条笔记：' + note.content)
    without_note_permission = rpc(writer, 'tools/call', params).json()['result']['structuredContent']
    assert note.content not in str(without_note_permission)


    note.delete()
    course.is_published = False
    course.save(update_fields=['is_published'])
    revoked = rpc(reader, 'tools/call', params).json()['result']['structuredContent']
    assert revoked['notes'] == revoked['course_progress'] == revoked['conversation'] == []
    assert auth_client.delete(f"{grants}{reader['id']}/").status_code == 204
    assert rpc(reader, 'tools/list').status_code == 401

    # A retry after disabling SDTM must bypass the previous memory frame.
    current.refresh_from_db()
    current.metadata['learning_snapshot'].update(memory_frame_id=999999, context='expired SDTM frame')
    current.save(update_fields=['metadata'])
    settings.UNIMIND_SDTM_TASK_MEMORY_MODE = 'off'
    assert 'expired SDTM frame' not in turn_project_context(user, claims)
    settings.UNIMIND_LEARNING_MEMORY_CONNECTORS = False
    assert rpc(writer, 'tools/list').status_code == 404
    assert project.learning_events.filter(kind='agent_checkpoint').count() == 1



@pytest.mark.django_db
def test_linked_sources_follow_live_permissions_without_a_chat_mention(settings, user, auth_client, django_user_model):
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    settings.UNIMIND_LEARNING_MEMORY_CONNECTORS = True
    project = ConversationProject.objects.create(user=user, name='久期')
    bot = Bot.objects.create(name='小宇')
    room = Conversation.objects.create(user=user, bot=bot, project=project, conversation_id=uuid4())
    message = AIChatMessage.objects.create(user=user, bot=bot, conversation_id=room.conversation_id,
                                          role='user', content='接着上次学')
    claims = {'message_id': message.pk, 'conversation_id': str(room.conversation_id), 'bot_id': bot.pk}
    module = CourseModule.objects.create(name='公开课', is_public=True)
    watched = Course.objects.create(title='久期基础', module=module, is_published=True)
    unwatched = Course.objects.create(title='久期例题', module=module, is_published=True)
    hidden = Course.objects.create(title='未开放课程', module=module)
    VideoProgress.objects.create(user=user, course=watched, last_position=59)
    note = Note.objects.create(user=user, title='久期笔记', content='前面的草稿。' * 200 + '票息变动时如何调整久期？')
    stranger = django_user_model.objects.create_user(username='other-owner')
    private_note = Note.objects.create(user=stranger, title='他人的久期笔记')
    other_project = ConversationProject.objects.create(user=stranger, name='他人的项目')

    sources = f'/api/ai/projects/{project.pk}/learning-memory/sources/'
    available = auth_client.get(sources, {'kind': 'note', 'q': '久期'}).data
    assert available['available'] == [{'id': note.pk, 'title': note.title}]
    assert auth_client.get(f'/api/ai/projects/{other_project.pk}/learning-memory/sources/').status_code == 404
    assert auth_client.post(sources, {'kind': 'note', 'source_id': private_note.pk}, format='json').status_code == 404
    assert auth_client.post(sources, {'kind': 'course', 'source_id': hidden.pk}, format='json').status_code == 404

    def attach(kind, source_id):
        return auth_client.post(sources, {'kind': kind, 'source_id': source_id}, format='json')

    course_link = attach('course', watched.pk)
    assert course_link.status_code == 201
    assert attach('course', watched.pk).data == course_link.data
    assert attach('course', unwatched.pk).status_code == 201

    course_room = Conversation.objects.create(user=user, bot=bot, project=project, conversation_id=uuid4())
    question = AIChatMessage.objects.create(user=user, bot=bot, conversation_id=course_room.conversation_id,
                                          role='user', content='讲解久期例题')
    course_claims = {'message_id': question.pk, 'conversation_id': str(course_room.conversation_id), 'bot_id': bot.pk}
    course_context = build_context(user, question.content, chat_context=course_claims)
    execute_tool(user, 'recall_learning', {'topic': '久期例题'}, course_context['memory']['version'], chat_context=course_claims)
    quoted_course = AIChatMessage.objects.create(user=user, bot=bot, conversation_id=course_room.conversation_id,
                                                 role='assistant', content='久期例题中的复述内容')

    note_link = attach('note', note.pk)
    assert note_link.status_code == 201
    assert not room.note_references.exists()

    context = build_context(user, message.content, chat_context=claims)

    def dsh(topic=''):
        return execute_tool(user, 'recall_learning', {'topic': topic},
                            context['memory']['version'], chat_context=claims)

    original = dsh()
    assert [(row['title'], row['position_seconds'], row['finished']) for row in original['course_progress']] == [
        ('久期基础', 59, False), ('久期例题', None, None),
    ]
    match = dsh('票息')['notes'][0]
    assert match['source'] == f'note:{note.pk}' and '票息变动' in match['excerpt'] and match['excerpt_start'] > 0
    assert auth_client.delete(f"{sources}{note_link.data['id']}/").status_code == 204
    assert dsh()['notes'] == []
    watched.is_published = False
    watched.save(update_fields=['is_published'])
    assert [row['title'] for row in dsh()['course_progress']] == ['久期例题']
    source = next(row for row in auth_client.get(sources).data['attached'] if row['id'] == course_link.data['id'])
    assert source['title'] is None
    assert auth_client.delete(f"{sources}{course_link.data['id']}/").status_code == 204
    remaining_course = next(row for row in auth_client.get(sources).data['attached'] if row['title'] == unwatched.title)
    assert quoted_course.content in str(dsh()['conversation'])
    assert auth_client.delete(f"{sources}{remaining_course['id']}/").status_code == 204
    assert quoted_course.content not in str(dsh()['conversation'])
    assert Note.objects.filter(pk=note.pk).exists()
    assert VideoProgress.objects.filter(user=user, course=watched, last_position=59).exists()
