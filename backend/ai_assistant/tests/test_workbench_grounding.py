"""Exercise source grounding through the HTTP and model tool boundaries."""
import asyncio
import json
from datetime import timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from django.utils import timezone

from ai_assistant.models import (
    AIChatMessage, Bot, Conversation, ConversationProject, ProjectLearning, ProjectSource, ProjectSourceChunk,
)
from ai_assistant.services.project_learning_tools import PROJECT_LEARNING_NAMES
from ai_assistant.services.runtime.workbench_grounding import (
    RETRIEVAL_LIMIT, WORKBENCH_TOOL_NAMES, WorkbenchGrounding, active_sources, extract_workbench_citations,
)
from ai_engine.service import AIEngine
from courses.models import Course, TranscriptSegment, VideoTranscript
from users.models import AIUsageReservation, Institution, User, WeeklyAIQuotaConfig
from users.models_workspace import Workspace, WorkspaceLearner, WorkspaceMembership

pytestmark = pytest.mark.django_db(transaction=True)


def add_source(project, title, source_type=ProjectSource.Type.TEXT, **kwargs):
    return ProjectSource.objects.create(
        project=project, user=project.user, title=title, source_type=source_type,
        status=kwargs.pop('status', ProjectSource.Status.READY), **kwargs,
    )


def add_chunk(source, index, content, *, anchor='section', label='章节', **kwargs):
    return ProjectSourceChunk.objects.create(
        source=source, chunk_index=index, content=content, anchor_type=anchor, locator_label=label, **kwargs,
    )


@pytest.fixture
def project(user):
    return ConversationProject.objects.create(user=user, name='货币银行学')


@pytest.fixture
def materials(project):
    pdf = add_source(project, '金融教材.pdf', 'pdf', summary='货币乘数与存款派生', unit_count=8)
    pdf_chunk = add_chunk(pdf, 0, '原始存款经过多轮派生存款扩张。', anchor='page', label='P.7', page_number=7)
    slides = add_source(project, '银行学第3章.pptx', 'pptx', unit_count=4)
    slide_chunk = add_chunk(
        slides, 0, '法定准备金率越高，简单货币乘数越小。', anchor='slide', label='Slide 4',
        slide_number=4, heading='存款创造机制',
    )
    course = Course.objects.create(title='准备金演示', author=project.user, is_workbench_companion=True)
    video = add_source(project, '准备金演示.mp4', 'uploaded_media', companion_course=course)
    add_chunk(video, 0, '本节介绍银行资产负债表。', anchor='timestamp', label='00:00', start_seconds=0, end_seconds=50)
    video_chunk = add_chunk(
        video, 1, '以准备金为例演示每一轮可贷金额。', anchor='timestamp', label='02:03',
        start_seconds=123.75, end_seconds=147.25,
    )
    return pdf_chunk, slide_chunk, video_chunk


@pytest.fixture
def bot(settings, monkeypatch):
    settings.UNIMIND_DSH_XIAOYU_ENABLED = False
    WeeklyAIQuotaConfig.objects.update_or_create(pk=1, defaults={'experience_calls': 20, 'course_calls': 20})
    for target in (
        'ai_assistant.services.title_generator.sync_generate_title',
        'ai_assistant.tasks.generate_conversation_title.delay',
        'ai_assistant.services.trajectory_recorder.record_trajectory',
        'ai_assistant.services.memory_service.extract_memories_async',
        'ai_assistant.services.memory_service.extract_memories_with_mem0',
    ):
        monkeypatch.setattr(target, Mock(return_value=None))
    monkeypatch.setattr('ai_assistant.services.memory_service.build_memory_context', Mock(return_value=('', '')))
    # Simulate an intent router that removes every model tool.
    monkeypatch.setattr('ai_engine.tool_router.route_tools', Mock(return_value=[]))
    return Bot.objects.create(name='工作台小宇', bot_type='planner', is_xiaoyu=True)


def chat_payload(bot, project, **extra):
    return {'bot_id': bot.pk, 'project_id': project.pk, 'message': '请综合资料解释存款创造。',
            'conversation_id': str(uuid4()), 'request_id': str(uuid4()), **extra}


async def stream_events(response):
    return [json.loads(frame[6:]) async for frame in response.streaming_content if frame.startswith(b'data: ')]


def finish_chat(client, payload, monkeypatch, answer, *, stream=False):
    def model_answer(**kwargs):
        content = answer(**kwargs)
        if stream:
            kwargs['on_message'](content)
            return {'content': content, 'finish_reason': 'completed'}
        return {'choices': [{'message': {'content': content}, 'finish_reason': 'stop'}]}

    if stream:
        monkeypatch.setattr(AIEngine, 'call_ai_with_streaming_tools', model_answer)
    else:
        monkeypatch.setattr(AIEngine, 'call_ai_with_tools', model_answer)
        monkeypatch.setattr('ai_assistant.utils._THREAD_POOL.submit', lambda fn, *a, **kw: fn(*a, **kw))
    url = '/api/ai/chat/stream/' if stream else '/api/ai/chat/'
    response = client.post(url, payload, format='json')
    assert response.status_code == 200, getattr(response, 'data', None)
    if stream:
        events = asyncio.run(stream_events(response))
        return next((event for event in events if event.get('done')), events)
    assert response.data == {'status': 'pending'}
    return client.get(f"/api/ai/chat-requests/{payload['request_id']}/").data['response']


@pytest.mark.parametrize('stream', [False, True])
def test_cross_source_citations_in_history_and_done(
    auth_client, bot, project, materials, stream, settings, monkeypatch,
):
    # Workbench SSE also runs when the ordinary chat route uses the DSH runtime.
    settings.UNIMIND_DSH_XIAOYU_ENABLED = stream
    payload = chat_payload(bot, project)
    pdf, slide, video = materials
    content = '教材和视频解释了派生存款与金额变化[S1#C0, S3#C1]。课件给出准备金率关系[S2#C0]。[S1#C0，S9#C0]'

    def answer(messages, tools, tool_executor, **kwargs):
        assert '只用本轮选中的资料' in messages[0]['content']
        grounding = messages[-2]['content']
        for chunk, marker in zip(materials, ('S1#C0', 'S2#C0', 'S3#C1')):
            assert f'[{marker}] ({chunk.source.title} · {chunk.locator_label})' in grounding
            assert chunk.content in grounding
        assert '[S3#C0]' in grounding
        assert {item['function']['name'] for item in tools} == WORKBENCH_TOOL_NAMES
        assert tool_executor._allowed_tool_names == WORKBENCH_TOOL_NAMES
        return content

    done = finish_chat(auth_client, payload, monkeypatch, answer, stream=stream)
    assert done['full_content'] == content
    citations = done['metadata']['workbench_citations']
    assert [(row['cite_key'], row['index'], row['chunk_id']) for row in citations] == [
        ('S1#C0', 1, pdf.pk), ('S3#C1', 2, video.pk), ('S2#C0', 3, slide.pk),
    ]
    assert citations[0] == {
        'cite_key': 'S1#C0', 'index': 1, 'source_id': str(pdf.source_id),
        'source_title': pdf.source.title, 'source_type': 'pdf', 'chunk_id': pdf.pk, 'chunk_index': 0,
        'anchor_type': 'page', 'locator_label': 'P.7', 'heading': '', 'quote': pdf.content,
        'page_number': 7, 'slide_number': None, 'start_seconds': None, 'end_seconds': None, 'companion_url': None,
    }
    assert (citations[1]['start_seconds'], citations[1]['end_seconds'], citations[1]['companion_url']) == (
        123.75, 147.25, f'/course/{video.source.companion_course_id}?project={project.pk}&t=123',
    )
    assert (citations[2]['anchor_type'], citations[2]['slide_number'], citations[2]['heading']) == (
        'slide', 4, '存款创造机制',
    )
    assert AIChatMessage.objects.get(pk=done['message_id']).metadata['workbench_citations'] == citations
    history = auth_client.get('/api/ai/history/', {'conversation_id': payload['conversation_id']}).data
    assert next(row for row in history if row['role'] == 'assistant')['metadata']['workbench_citations'] == citations
    assert ProjectLearning.objects.get(project=project).planning_enabled is False


@pytest.mark.parametrize('selection', ['default', 'explicit', 'empty'])
def test_chat_uses_only_this_turns_selection(auth_client, bot, project, materials, selection, monkeypatch):
    pdf, slide, video = materials
    ProjectSource.objects.filter(pk=slide.source_id).update(is_selected=False)
    conversation = Conversation.objects.create(user=project.user, bot=bot, project=project, conversation_id=uuid4())
    AIChatMessage.objects.create(
        user=project.user, bot=bot, role='assistant', conversation_id=conversation.conversation_id,
        content='上一次对话的引用[S9#C0]。',
    )
    payload = chat_payload(bot, project, conversation_id=str(conversation.conversation_id))
    expected = [pdf, video] if selection == 'default' else []
    if selection == 'explicit':
        # A request can explicitly choose a ready source that is deselected in the project defaults.
        expected = [slide]
    if selection != 'default':
        payload['workbench_source_ids'] = [str(chunk.source_id) for chunk in expected]

    def answer(messages, tool_executor, **kwargs):
        context = '\n'.join(row['content'] for row in messages)
        assert '[S9#C0]' not in context
        for chunk in materials:
            assert (chunk.content in context) == (chunk in expected)
            result = json.loads(tool_executor('search_workbench_sources', {
                'query': chunk.content, 'source_id': str(chunk.source_id),
            }))
            if chunk in expected:
                assert chunk.pk in [match['citation']['chunk_id'] for match in result['chunks']]
            else:
                assert 'error' in result
        hits = json.loads(tool_executor('search_workbench_sources', {'query': '准备金率 原始存款'}))['chunks']
        assert {row['citation']['source_id'] for row in hits} <= {str(chunk.source_id) for chunk in expected}
        return '已按本轮资料回答。'

    assert finish_chat(auth_client, payload, monkeypatch, answer)['metadata']['workbench_citations'] == []


@pytest.mark.parametrize('path', ['/api/ai/chat/', '/api/ai/chat/stream/'])
def test_source_ids_validate_project_ownership_readiness_and_shape(auth_client, bot, project, materials, path):
    sibling = ConversationProject.objects.create(user=project.user, name='其他项目')
    wrong_project = add_source(sibling, '其他项目资料')
    pending = add_source(project, '解析中', status='processing')
    foreign_user = User.objects.create_user(username='foreign-source-owner')
    foreign_project = ConversationProject.objects.create(user=foreign_user, name='私有项目')
    foreign = add_source(foreign_project, '私有来源')
    for raw in ([str(wrong_project.pk)], [str(foreign.pk)], [str(pending.pk)], [str(uuid4())],
                None, str(materials[0].source_id), [1], ['invalid']):
        payload = chat_payload(bot, project, workbench_source_ids=raw)
        response = auth_client.post(path, payload, format='json')
        assert response.status_code == 400 and 'workbench_source_ids' in response.data
        assert not Conversation.objects.filter(conversation_id=payload['conversation_id']).exists()
        assert not AIChatMessage.objects.filter(conversation_id=payload['conversation_id']).exists()
    assert not AIUsageReservation.objects.filter(status='pending').exists()


def test_explicit_source_selection_is_part_of_request_identity(auth_client, bot, project, materials, monkeypatch):
    payload = chat_payload(bot, project, workbench_source_ids=[str(materials[0].source_id)])
    done = finish_chat(auth_client, payload, monkeypatch, lambda **kwargs: '教材说明[S1#C0]。')
    duplicate = auth_client.post('/api/ai/chat/', payload, format='json')
    assert duplicate.data['message_id'] == done['message_id']
    for selection in ([], [str(materials[1].source_id)]):
        conflict = auth_client.post('/api/ai/chat/', {**payload, 'workbench_source_ids': selection}, format='json')
        assert conflict.status_code == 400 and 'request_id' in conflict.data
    assert AIChatMessage.objects.filter(conversation_id=payload['conversation_id']).count() == 2


@pytest.mark.parametrize('stream', [False, True])
def test_ulr_grounding_preserves_selection_tools_and_receipt(
    auth_client, bot, project, materials, settings, tmp_path, monkeypatch, stream,
):
    settings.UNIMIND_LEARNING_RUNTIME = 'ulr'
    settings.UNIMIND_DSH_STATE_DIR = str(tmp_path)
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    monkeypatch.setattr('ai_assistant.services.dsh_xiaoyu.schedule_conversation_title', Mock())
    selected, excluded, video = materials
    companion = video.source.companion_course
    companion.video_file = 'workbench_sources/companion.mp4'
    companion.save(update_fields=['video_file'])
    video.source.file = companion.video_file.name
    video.source.save(update_fields=['file'])
    transcript = VideoTranscript.objects.create(course=companion, asr_status='completed')
    TranscriptSegment.objects.create(transcript=transcript, index=0, start_time=120, end_time=150, text='私有伴学讲稿')
    payload = chat_payload(bot, project, workbench_source_ids=[str(selected.source_id)],
                           course_context={'course_id': companion.pk, 'video_seconds': 125})

    def answer(messages, tools, **kwargs):
        assert selected.content in messages[0]['content']
        assert excluded.content not in messages[0]['content']
        assert '私有伴学讲稿' in messages[0]['content']
        assert WORKBENCH_TOOL_NAMES <= {tool['function']['name'] for tool in tools}
        if messages[-1]['role'] != 'tool':
            return {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [{
                'id': 'read-source', 'type': 'function', 'function': {
                    'name': 'read_workbench_source_chunks', 'arguments': json.dumps({'source_id': 'S1'}),
                },
            }]}}]}
        assert json.loads(messages[-1]['content'])['chunks'][0]['content'] == selected.content
        return {'choices': [{'finish_reason': 'stop', 'message': {'content': '原始存款产生派生存款[S1#C0]。'}}]}

    model = Mock(side_effect=answer)
    monkeypatch.setattr(AIEngine, 'call_provider', model)
    recovery_url = f"/api/ai/chat-requests/{payload['request_id']}/"
    if stream:
        response = auth_client.post('/api/ai/chat/stream/', payload, format='json')
        assert response.status_code == 200
        done = asyncio.run(stream_events(response))[-1]
    else:
        monkeypatch.setattr('ai_assistant.utils._THREAD_POOL.submit', lambda fn: fn())
        response = auth_client.post('/api/ai/chat/', payload, format='json')
        assert response.data['status'] == 'pending'
        done = auth_client.get(recovery_url).data['response']

    assert done['engine'] == 'ulr'
    assert done['metadata']['course_context']['video_seconds'] == 125
    citation, = done['metadata']['workbench_citations']
    assert citation['chunk_id'] == selected.pk
    assert auth_client.get(recovery_url).data['response'] == done
    altered = {**payload, 'workbench_source_ids': [str(excluded.source_id)]}
    assert auth_client.post('/api/ai/chat/', altered, format='json').status_code == 400
    selected.source.delete()
    assert auth_client.get(recovery_url).data['status'] == 'failed'
    assert model.call_count == 2


def test_large_corpus_search_and_tool_only_citation(auth_client, bot, project, monkeypatch):
    monkeypatch.delenv('AI_EMBEDDING_BASE_URL', raising=False)
    embedding = Mock(side_effect=AssertionError('unconfigured embedding'))
    monkeypatch.setattr('ai_engine.tool_router._call_embedding_api', embedding)
    book = add_source(project, '资料集.pdf', 'pdf', unit_count=25)
    for index in range(25):
        add_chunk(book, index, 'liquidity reserve ' * 65, anchor='page', label=f'P.{index + 1}', page_number=index + 1)
    distant = add_chunk(book, 25, '货币乘数由准备金率决定。', anchor='page', label='P.26', page_number=26)
    add_chunk(book, 26, '债券的reinvestment risk影响投资回报。', anchor='page', label='P.27', page_number=27)
    private = add_source(ConversationProject.objects.create(user=project.user, name='其他项目'), '边界资料')
    add_chunk(private, 0, '货币乘数与准备金率的另一种解释。')
    payload = chat_payload(bot, project, message='liquidity reserve')

    def answer(messages, tool_executor, **kwargs):
        injected = messages[-2]['content']
        assert injected.count('] (资料集.pdf · P.') == RETRIEVAL_LIMIT
        assert '货币乘数' not in injected
        assert distant.pk not in {c['chunk_id'] for c in tool_executor.workbench_grounding.citation_registry.values()}
        chinese = json.loads(tool_executor('search_workbench_sources', {'query': '货币乘数 准备金率'}))
        assert chinese['chunks'][0]['citation']['chunk_id'] == distant.pk
        english = json.loads(tool_executor('search_workbench_sources', {'query': 'REINVESTMENT risk', 'source_id': 'S1'}))
        assert english['chunks'][0]['marker'] == '[S1#C26]'
        contiguous = json.loads(tool_executor('read_workbench_source_chunks', {
            'source_id': str(book.pk), 'start_chunk': 25, 'limit': 1,
        }))
        assert contiguous['next_chunk'] == 26 and contiguous['chunks'][0]['marker'] == '[S1#C25]'
        page = json.loads(tool_executor('read_workbench_source_chunks', {
            'source_id': 'S1', 'locator': {'unit': 'page', 'start': 27, 'end': 27},
        }))
        assert [row['marker'] for row in page['chunks']] == ['[S1#C26]']
        assert 'error' in json.loads(tool_executor('search_workbench_sources', {
            'query': '货币乘数', 'source_id': str(private.pk),
        }))
        assert 'error' in json.loads(tool_executor('read_workbench_source_chunks', {'source_id': str(private.pk)}))
        return '准备金率影响货币乘数[S1#C25]。'

    done = finish_chat(auth_client, payload, monkeypatch, answer)
    assert [row['chunk_id'] for row in done['metadata']['workbench_citations']] == [distant.pk]
    embedding.assert_not_called()


def test_configured_embeddings_add_semantic_matches(project, monkeypatch):
    monkeypatch.setenv('AI_EMBEDDING_BASE_URL', 'http://127.0.0.1:1234/v1')
    related = add_chunk(add_source(project, '视频讲义'), 0, '资产流动性折价')
    add_chunk(add_source(project, '其他资料'), 0, '国际收支平衡表')
    embedding = Mock(return_value=[[1, 0], [1, 0], [0, 1]])
    monkeypatch.setattr('ai_engine.tool_router._call_embedding_api', embedding)
    turn = WorkbenchGrounding(project, active_sources(project))
    hits = turn.search_workbench_sources('marketability')['chunks']
    assert [row['citation']['chunk_id'] for row in hits] == [related.pk]
    assert embedding.call_args.kwargs['timeout'] == 1.0


@pytest.mark.parametrize(('platform', 'expected'), [
    ('bilibili', 'https://www.bilibili.com/video/BVtest3?p=3&t=120'),
    ('youtube', 'https://www.youtube.com/watch?v=BVtest3&t=120s'),
    ('other', 'https://video.example/lecture'),
])
def test_external_video_citation_links_and_timestamp_read(project, platform, expected):
    video = add_source(project, '外部视频', 'external_video', source_url='https://video.example/lecture',
                       metadata={'platform': platform, 'external_id': 'BVtest3', 'part': 3})
    add_chunk(video, 0, '导言', anchor='timestamp', start_seconds=0, end_seconds=10)
    add_chunk(video, 1, '案例分析', anchor='timestamp', start_seconds=120.9, end_seconds=135.2)
    turn = WorkbenchGrounding(project, active_sources(project))
    results = turn.read_workbench_source_chunks(
        'S1', locator={'unit': 'timestamp', 'start': 130, 'end': 140},
    )
    assert [row['marker'] for row in results['chunks']] == ['[S1#C1]']
    citation, = extract_workbench_citations('案例见这里[S1#C1]。[S1#C0]', turn.citation_registry)
    assert citation['companion_url'] == expected


@pytest.mark.parametrize('planning_enabled', [False, True])
def test_institution_chat_preserves_its_planning_mode(api_client, user, bot, planning_enabled, monkeypatch):
    institution = Institution.objects.create(name='机构', slug='workbench-isolation')
    workspace = Workspace.objects.create(
        institution=institution, service_ends_on=timezone.localdate() + timedelta(days=7), max_students=5,
    )
    WorkspaceMembership.objects.create(workspace=workspace, user=user)
    learner = User.objects.create_user(username='workbench-learner', institution=institution)
    WorkspaceLearner.objects.create(account=user, workspace=workspace, user=learner)
    api_client.force_authenticate(learner)
    project = ConversationProject.objects.create(user=learner, name='机构课业')
    ProjectLearning.objects.create(project=project, planning_enabled=planning_enabled)
    source = add_source(project, '机构来源')
    add_chunk(source, 0, 'INSTITUTION_SOURCE_TEXT')

    def answer(messages, tools, tool_executor, **kwargs):
        assert 'INSTITUTION_SOURCE_TEXT' not in '\n'.join(row['content'] for row in messages)
        assert tool_executor.workbench_grounding is None
        assert {tool['function']['name'] for tool in tools} == (PROJECT_LEARNING_NAMES if planning_enabled else set())
        assert 'error' in json.loads(tool_executor('read_workbench_source_chunks', {'source_id': str(source.pk)}))
        return '机构空间回答。'

    payload = chat_payload(bot, project, workbench_source_ids=[str(source.pk)])
    done = finish_chat(api_client, payload, monkeypatch, answer, stream=planning_enabled)
    assert 'workbench_citations' not in done['metadata']
    url = f'/api/ai/projects/{project.pk}/workbench-overview/'
    assert api_client.get(url).status_code == 403
    assert api_client.post(url).status_code == 403


def test_overview_fast_get_model_post_and_selection_invalidation(auth_client, project, materials, monkeypatch):
    url = f'/api/ai/projects/{project.pk}/workbench-overview/'
    output = {'overview': '三份资料共同解释了存款创造。', 'suggested_questions': [
        '教材和课件对准备金率的解释如何对应？', '视频中的例子体现了什么关系？', '尝试推导简单货币乘数。',
    ]}
    model = Mock(return_value=output)
    monkeypatch.setattr(AIEngine, 'structured_output', model)
    first = auth_client.get(url).data
    assert '货币乘数与存款派生' in first['overview']
    assert len(first['suggested_questions']) == 4
    assert all(chunk.source.title in first['overview'] for chunk in materials)
    model.assert_not_called()

    response = auth_client.post(url)
    assert response.status_code == 200
    assert response.data == {**output, 'source_signature': first['source_signature']}
    model.assert_called_once()
    prompt = model.call_args.kwargs['messages'][-1]['content']
    assert all(chunk.content in prompt for chunk in materials)
    project.refresh_from_db()
    assert project.workbench_overview == response.data
    assert auth_client.get(url).data == auth_client.post(url).data == response.data
    model.assert_called_once()

    slide = materials[1]
    assert auth_client.patch(f'/api/ai/projects/{project.pk}/sources/{slide.source_id}/',
                             {'is_selected': False}, format='json').status_code == 200
    next_overview = auth_client.get(url).data
    assert next_overview['source_signature'] != first['source_signature']
    assert slide.source.title not in next_overview['overview']
    assert auth_client.post(url).data['source_signature'] == next_overview['source_signature']
    assert model.call_count == 2 and slide.content not in model.call_args.kwargs['messages'][-1]['content']

    # Updating a source that stays selected also invalidates its synthesis.
    pdf = materials[0]
    assert auth_client.patch(f'/api/ai/projects/{project.pk}/sources/{pdf.source_id}/',
                             {'title': '新版金融教材.pdf'}, format='json').status_code == 200
    renamed = auth_client.get(url).data
    assert renamed['source_signature'] != next_overview['source_signature']
    assert '新版金融教材.pdf' in renamed['overview']


def test_overview_scope_empty_and_failed_synthesis(auth_client, project, monkeypatch):
    other = User.objects.create_user(username='overview-other')
    foreign_project = ConversationProject.objects.create(user=other, name='私有项目')
    foreign_url = f'/api/ai/projects/{foreign_project.pk}/workbench-overview/'
    model = Mock(return_value={'overview': '无效结果', 'suggested_questions': []})
    monkeypatch.setattr(AIEngine, 'structured_output', model)
    assert auth_client.get(foreign_url).status_code == auth_client.post(foreign_url).status_code == 404

    url = f'/api/ai/projects/{project.pk}/workbench-overview/'
    add_source(project, '仍待处理', status='pending')
    empty = auth_client.get(url).data
    assert empty['overview'] == '' and empty['suggested_questions'] == []
    assert auth_client.post(url).data == empty
    model.assert_not_called()

    add_chunk(add_source(project, '正文'), 0, '已经就绪的文本')
    assert auth_client.post(url).status_code == 502
    project.refresh_from_db()
    assert not project.workbench_overview
    assert '已经就绪的文本' in auth_client.get(url).data['overview']


def test_overview_rejects_synthesis_if_selection_changes_during_generation(auth_client, project, monkeypatch):
    source = add_source(project, '会被取消选择的正文', summary='正文摘要')
    url = f'/api/ai/projects/{project.pk}/workbench-overview/'

    def generate(**kwargs):
        source.is_selected = False
        source.save(update_fields=['is_selected', 'updated_at'])
        return {'overview': '上一版选择的综合概览', 'suggested_questions': ['问题一？', '问题二？', '问题三？']}

    monkeypatch.setattr(AIEngine, 'structured_output', generate)
    assert auth_client.post(url).status_code == 409
    project.refresh_from_db()
    assert project.workbench_overview == {}
    assert auth_client.get(url).data['overview'] == ''
