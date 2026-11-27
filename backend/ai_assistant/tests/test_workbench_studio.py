import json
from datetime import timedelta
from unittest.mock import Mock

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from ai_assistant.models import ConversationProject, ProjectSource, ProjectSourceChunk, ProjectStudioArtifact
from ai_engine.service import AICallError, AIEngine
from notes.models import Note, Notebook
from users.learning import get_weekly_quota_config, usage_info
from users.login_sessions import LoginSession
from users.models import AIUsageReservation, Institution, User
from users.models_workspace import Workspace, WorkspaceMembership

pytestmark = pytest.mark.django_db
MARKERS = ('S1#C2', 'S2#C1', 'S3#C3')


def _url(project, artifact_id=None, suffix=''):
    path = reverse('project-studio-list', args=[project.pk])
    return f'{path}{artifact_id}/{suffix}' if artifact_id else path


def _source(project, kind, title, chunk_index, anchor, locator, content, **position):
    metadata = {'platform': 'bilibili', 'external_id': 'BV1Studio', 'part': 2} if kind == 'external_video' else {}
    source = ProjectSource.objects.create(
        project=project, user=project.user, source_type=kind, title=title, status='ready', metadata=metadata,
    )
    chunk = ProjectSourceChunk.objects.create(
        source=source, chunk_index=chunk_index, anchor_type=anchor, locator_label=locator, content=content, **position,
    )
    return source, chunk


@pytest.fixture
def studio(user):
    project = ConversationProject.objects.create(user=user, name='利率复习')
    sources = [
        _source(project, 'pdf', '课本', 2, 'page', 'P.6', '到期收益率是使债券现金流现值等于价格的折现率。', page_number=6),
        _source(project, 'pptx', '课件', 1, 'slide', 'Slide 5', '久期衡量现金流回收的平均时间。', slide_number=5),
        _source(project, 'external_video', '视频', 3, 'timestamp', '00:42', '固定利率债券价格与市场利率反向变动。',
                start_seconds=42, end_seconds=51),
    ]
    return project, sources


def _quiz(subjective=False):
    questions = [
        {'type': 'single_choice', 'prompt': f'题干 {i}', 'options': ['甲', '乙', '丙'], 'answer_index': i % 3,
         'explanation': f'原文支持选项 {i % 3}。', 'cite_key': MARKERS[i % 3]}
        for i in range(4)
    ]
    if subjective:
        questions[-1] = {
            'type': 'subjective', 'prompt': '解释固定利率债券价格与市场利率的关系。',
            'reference_answer': '市场利率上升，债券价格下跌。', 'explanation': '两者反向变动。',
            'rubric': [
                {'criterion': '指出利率方向', 'keywords': ['利率上升', '收益率上升']},
                {'criterion': '指出价格方向', 'keywords': ['价格下跌', '价格下降']},
            ],
            'cite_key': MARKERS[2],
        }
    return {'questions': questions}


@pytest.fixture
def model(monkeypatch):
    def generate(**kwargs):
        kind = kwargs['operation'].rsplit('.', 1)[-1]
        if kind == 'quiz':
            user_payload = json.loads(kwargs['messages'][-1]['content'])
            return _quiz(user_payload['include_subjective'])
        if kind == 'workbench_studio':
            return {'matched_points': [1, 2], 'feedback': '答对了利率和价格的方向。'}
        return {
            'study_guide': {
                'main_question': '怎样理解债券定价？ [S1#C2]',
                'source_outline': ['课本讲收益率 [S1#C2]', '课件讲久期 [S2#C1]', '视频讲价格变动 [S3#C3]'],
                'key_concepts': [{'concept': '久期', 'explanation': '平均回收时间 [S2#C1]'}],
                'confusing_points': ['先比较久期与收益率 [S2#C1] [S1#C2]'],
                'study_order': ['先学习收益率 [S1#C2]', '再看价格的变化 [S3#C3]'],
            },
            'briefing': {'content_markdown': '## 债券定价\n\n折现率 [S1#C2]、久期 [S2#C1]、价格变动 [S3#C3]。'},
            'faq': {'pairs': [{'question': f'核心问题 {i}', 'answer': f'关键回答 [{MARKERS[i % 3]}]'} for i in range(6)]},
            'flashcards': {'cards': [
                {'front': f'知识点 {i}', 'back': f'知识点解释 {i}', 'hint': '用定义回想', 'cite_key': MARKERS[i % 3]}
                for i in range(10)
            ]},
        }[kind]
    mock = Mock(side_effect=generate)
    monkeypatch.setattr(AIEngine, 'structured_output', mock)
    return mock


def _generate(client, project, kind, **options):
    response = client.post(_url(project), {'kind': kind, **options}, format='json')
    assert response.status_code == 201, response.data
    assert response.data['status'] == 'ready', response.data
    return response.data


@pytest.mark.parametrize('kind', ['study_guide', 'briefing', 'faq', 'flashcards', 'quiz'])
def test_generate_selected_sources_and_resolve_multimodal_citations(auth_client, studio, model, kind):
    project, sources = studio
    unselected, _ = _source(project, 'text', '未选', 0, 'section', '正文', '这段未选正文不应发给模型。')
    unselected.is_selected = False
    unselected.save()
    ProjectSource.objects.create(project=project, user=project.user, source_type='pdf', title='处理中', status='processing')

    artifact = _generate(auth_client, project, kind, custom_focus='重看债券定价')
    assert artifact['source_ids'] == [str(source.pk) for source, _ in sources]
    by_key = {row['cite_key']: row for row in artifact['citations']}
    assert set(by_key) == set(MARKERS)
    assert [by_key[key]['chunk_id'] for key in MARKERS] == [chunk.pk for _, chunk in sources]
    assert [by_key[key]['index'] for key in MARKERS] == [1, 2, 3]
    assert by_key[MARKERS[0]]['page_number'] == 6
    assert by_key[MARKERS[1]]['slide_number'] == 5
    assert by_key[MARKERS[2]]['start_seconds'] == 42
    assert by_key[MARKERS[2]]['companion_url'] == 'https://www.bilibili.com/video/BV1Studio?p=2&t=42'
    if kind in ('study_guide', 'briefing', 'faq'):
        assert all(f'[{key}]' in artifact['content_markdown'] for key in MARKERS)
    if kind == 'study_guide':
        assert '核心概念速查表' in artifact['content_markdown']
        assert artifact['structured_payload']['key_concepts'][0]['concept'] == '久期'
    if kind == 'faq':
        assert len(artifact['structured_payload']['pairs']) == 6
    if kind == 'flashcards':
        assert [card['id'] for card in artifact['structured_payload']['cards']] == [f'fc_{i}' for i in range(1, 11)]
        assert {card['mastery'] for card in artifact['structured_payload']['cards']} == {'unseen'}
    if kind == 'quiz':
        assert all('quote' not in row for row in by_key.values())
        assert len(artifact['structured_payload']['questions']) == 4
        assert all(set(question) == {'id', 'type', 'prompt', 'options', 'cite_key'}
                   for question in artifact['structured_payload']['questions'])

    context = json.loads(model.call_args.kwargs['messages'][-1]['content'])
    assert context['custom_focus'] == '重看债券定价'
    assert context['excerpts'] == {f'[{key}]': chunk.content for key, (_, chunk) in zip(MARKERS, sources)}
    assert auth_client.get(_url(project, artifact['id'])).data == artifact
    assert auth_client.get(_url(project)).data['artifacts'] == [artifact]
    assert usage_info(project.user)['used'] == 1


def test_explicit_selection_rejects_unready_and_foreign_sources(auth_client, studio, model):
    project, sources = studio
    source, chunk = sources[1]
    source.is_selected = False
    source.save()
    pending = ProjectSource.objects.create(project=project, user=project.user, source_type='pdf', title='未就绪')
    empty = ProjectSource.objects.create(project=project, user=project.user, source_type='text', title='空白', status='ready')
    other = ConversationProject.objects.create(user=project.user, name='另一个项目')
    other_source, _ = _source(other, 'text', '其他项目资料', 0, 'section', '正文', '其他项目内容')
    for ids in ([], ['invalid'], [str(pending.pk)], [str(other_source.pk)], [str(empty.pk)]):
        response = auth_client.post(_url(project), {'kind': 'briefing', 'source_ids': ids}, format='json')
        assert response.status_code == 400, response.data
    response = auth_client.post(_url(other), {'kind': 'briefing', 'source_ids': [str(source.pk)]}, format='json')
    assert response.status_code == 400
    assert not project.studio_artifacts.exists()
    model.assert_not_called()

    model.side_effect = None
    model.return_value = {'content_markdown': '久期 [S1#C1]。'}
    artifact = _generate(auth_client, project, 'briefing', source_ids=[str(source.pk)])
    assert artifact['source_ids'] == [str(source.pk)]
    assert artifact['citations'][0]['chunk_id'] == chunk.pk


def test_generation_requires_ready_selection_and_available_quota(auth_client, studio, model):
    project, _ = studio
    project.workbench_sources.update(is_selected=False)
    response = auth_client.post(_url(project), {'kind': 'briefing'}, format='json')
    assert response.status_code == 400 and 'source_ids' in response.data
    project.workbench_sources.update(is_selected=True)
    config = get_weekly_quota_config()
    config.experience_calls = 0
    config.save(update_fields=['experience_calls'])
    assert auth_client.post(_url(project), {'kind': 'briefing'}, format='json').status_code == 403
    assert not project.studio_artifacts.exists()
    assert not AIUsageReservation.objects.filter(user=project.user).exists()
    model.assert_not_called()


def test_large_selection_supplies_excerpts_from_each_source(auth_client, studio, model):
    project, sources = studio
    first, _ = sources[0]
    ProjectSourceChunk.objects.bulk_create([
        ProjectSourceChunk(source=first, chunk_index=index, anchor_type='page', locator_label=str(index),
                           content='一段很长的课本正文。' * 240 + ('基准收益率' if index == 9 else ''))
        for index in range(3, 17)
    ])
    _generate(auth_client, project, 'briefing', custom_focus='基准收益率')
    excerpts = json.loads(model.call_args.kwargs['messages'][-1]['content'])['excerpts']
    assert {'[S1#C2]', '[S1#C9]', '[S1#C16]', '[S2#C1]', '[S3#C3]'} <= excerpts.keys()
    assert '基准收益率' in excerpts['[S1#C9]']
    assert sum(map(len, excerpts.values())) <= 18_000


@pytest.mark.parametrize('invalid_output', [None, {'content_markdown': '原文 [S1#C2]、虚构引用 [S9#C1]。'}])
def test_failed_generation_is_persisted_and_releases_quota(auth_client, studio, model, invalid_output):
    project, _ = studio
    model.side_effect = None
    model.return_value = invalid_output
    response = auth_client.post(_url(project), {'kind': 'briefing'}, format='json')
    assert response.status_code == 201
    artifact = auth_client.get(_url(project, response.data['id'])).data
    assert artifact['status'] == 'failed' and artifact['error_message']
    assert artifact['citations'] == [] and artifact['content_markdown'] == ''
    assert AIUsageReservation.objects.get(user=project.user).status == 'released'
    assert usage_info(project.user)['used'] == 0


def test_deleting_a_generating_artifact_prevents_publication_and_charge(auth_client, studio, model):
    project, _ = studio

    def delete_during_generation(**kwargs):
        artifact = project.studio_artifacts.get(status='generating')
        assert auth_client.delete(_url(project, artifact.pk)).status_code == 204
        return {'content_markdown': '收益率 [S1#C2]。'}

    model.side_effect = delete_during_generation
    response = auth_client.post(_url(project), {'kind': 'briefing'}, format='json')
    assert response.status_code == 404
    assert not project.studio_artifacts.exists()
    assert AIUsageReservation.objects.get(user=project.user).status == 'released'
    assert usage_info(project.user)['used'] == 0


def test_flashcard_progress_title_and_delete(auth_client, studio, model):
    project, _ = studio
    artifact = _generate(auth_client, project, 'flashcards')
    url = _url(project, artifact['id'])
    for mastery in ({'fc_1': 'known'}, {'unknown': 'mastered'}, {'fc_1': 'learning', 'unknown': 'mastered'}):
        response = auth_client.patch(url, {'title': '无效更新', 'flashcard_mastery': mastery}, format='json')
        assert response.status_code == 400
    assert auth_client.get(url).data['title'] == artifact['title']
    response = auth_client.patch(
        url, {'title': '复习卡', 'flashcard_mastery': {'fc_1': 'mastered', 'fc_3': 'learning'}}, format='json',
    )
    assert response.status_code == 200
    record = auth_client.get(url).data
    assert record['title'] == '复习卡'
    assert [card['mastery'] for card in record['structured_payload']['cards']][:3] == ['mastered', 'unseen', 'learning']
    assert record['citations'] == artifact['citations']
    assert auth_client.delete(url).status_code == 204
    assert auth_client.get(url).status_code == 404


def test_objective_quiz_grades_answers_and_keeps_latest_attempt(auth_client, studio, model):
    project, sources = studio
    artifact = _generate(auth_client, project, 'quiz')
    assert json.loads(model.call_args.kwargs['messages'][-1]['content'])['include_subjective'] is False
    url = _url(project, artifact['id'], 'submit-quiz/')
    for answers in (
        [{'question_id': 'q_9', 'answer': 0}],
        [{'question_id': 'q_1', 'answer': 0}, {'question_id': 'q_1', 'answer': 1}],
        [{'question_id': 'q_1', 'answer': True}],
        [{'question_id': 'q_1', 'answer': 3}],
    ):
        assert auth_client.post(url, {'answers': answers}, format='json').status_code == 400
    response = auth_client.post(url, {
        'answers': [{'question_id': 'q_1', 'answer': 0}, {'question_id': 'q_2', 'answer': 0}],
    }, format='json')
    assert response.status_code == 200, response.data
    assert (response.data['score'], response.data['max_score']) == (1, 4)
    correct, wrong, skipped, _ = response.data['results']
    assert correct['is_correct'] is True and wrong['is_correct'] is False
    assert wrong['correct_answer'] == 1 and wrong['explanation']
    assert wrong['citation']['slide_number'] == 5 and wrong['citation']['quote'] == sources[1][1].content
    assert skipped['grading_method'] == 'unanswered'
    assert auth_client.get(_url(project, artifact['id'])).data['structured_payload']['latest_attempt'] == response.data
    retry = auth_client.post(url, {'answers': [{'question_id': 'q_2', 'answer': 1}]}, format='json')
    assert retry.data['results'][0]['grading_method'] == 'unanswered'
    assert auth_client.get(_url(project)).data['artifacts'][0]['structured_payload']['latest_attempt'] == retry.data
    model.assert_called_once()


@pytest.mark.parametrize('mode', ['ai', 'invalid', 'unavailable', 'quota'])
def test_subjective_quiz_rubric_and_deterministic_fallback(auth_client, studio, model, mode):
    project, _ = studio
    artifact = _generate(auth_client, project, 'quiz', include_subjective=True)
    question = artifact['structured_payload']['questions'][-1]
    assert question['type'] == 'subjective'
    assert 'rubric' not in question and 'reference_answer' not in question
    if mode == 'invalid':
        model.side_effect = None
        model.return_value = {'matched_points': [99], 'feedback': '不合法的序号'}
    if mode == 'unavailable':
        model.side_effect = AICallError('暂不可用')
    if mode == 'quota':
        config = get_weekly_quota_config()
        config.experience_calls = 1
        config.save(update_fields=['experience_calls'])
    url = _url(project, artifact['id'], 'submit-quiz/')
    response = auth_client.post(url, {
        'answers': [{'question_id': question['id'], 'answer': '从利率上升开始分析。'}],
    }, format='json')
    assert response.status_code == 200, response.data
    graded = response.data['results'][-1]
    assert graded['score'] == (1 if mode == 'ai' else 0.5)
    assert graded['grading_method'] == ('ai_rubric' if mode == 'ai' else 'keyword')
    assert graded['feedback'] and graded['citation']['start_seconds'] == 42
    assert usage_info(project.user)['used'] == (2 if mode == 'ai' else 1)
    assert not AIUsageReservation.objects.filter(user=project.user, status='pending').exists()
    assert model.call_count == (1 if mode == 'quota' else 2)


@pytest.mark.parametrize('kind', ['study_guide', 'briefing', 'faq', 'flashcards'])
def test_save_note_reuses_project_notebook_and_preserves_edits(auth_client, studio, model, kind):
    project, _ = studio
    notes_url = reverse('project-note-list', args=[project.pk])
    freeform = auth_client.post(notes_url, {'title': '课堂笔记', 'content': '  我的 Markdown  \n'}, format='json')
    assert freeform.status_code == 201, freeform.data
    assert freeform.data['content'] == '  我的 Markdown  \n'
    artifact = _generate(auth_client, project, kind)
    save_url = _url(project, artifact['id'], 'save-note/')
    response = auth_client.post(save_url)
    assert response.status_code == 201, response.data
    note = Note.objects.get(pk=response.data['id'])
    assert note.user == project.user and note.notebook.name == project.name
    assert note.notebook_id == freeform.data['notebook_id']
    assert response.data['title'] == artifact['title']
    assert '[S1#C2]' in note.content
    if kind == 'flashcards':
        assert '## 知识点 0' in note.content and '用定义回想' in note.content
    assert ProjectStudioArtifact.objects.get(pk=artifact['id']).linked_note == note
    assert auth_client.get(_url(project)).data['notes'] == auth_client.get(notes_url).data['notes']
    assert len(auth_client.get(notes_url).data['notes']) == 2

    regular_notes_url = f'/api/notes/items/{note.pk}/'
    edited = auth_client.patch(regular_notes_url, {'content': '修订后的笔记', 'version': 1}, format='json')
    assert edited.status_code == 200, edited.data
    second = auth_client.post(save_url)
    assert second.status_code == 200
    assert (second.data['id'], second.data['content']) == (note.pk, '修订后的笔记')
    assert Notebook.objects.filter(user=project.user, name=project.name).count() == 1

    same_name = ConversationProject.objects.create(user=project.user, name=project.name)
    other_notes = reverse('project-note-list', args=[same_name.pk])
    assert auth_client.get(other_notes).data['notes'] == []
    other_note = auth_client.post(other_notes, {'title': '另一项目的笔记'}, format='json')
    assert other_note.status_code == 201 and other_note.data['notebook_id'] != note.notebook_id
    assert auth_client.delete(_url(project, artifact['id'])).status_code == 204
    assert auth_client.get(regular_notes_url).data['content'] == '修订后的笔记'


def test_studio_endpoints_return_404_for_other_projects_users_and_spaces(auth_client, studio, model):
    project, _ = studio
    artifact = _generate(auth_client, project, 'quiz')
    notes_url = reverse('project-note-list', args=[project.pk])
    other_project = ConversationProject.objects.create(user=project.user, name='同一用户的另一个项目')
    for suffix in ('', 'save-note/', 'submit-quiz/'):
        path = _url(other_project, artifact['id'], suffix)
        response = auth_client.post(path) if suffix else auth_client.get(path)
        assert response.status_code == 404
    other = APIClient()
    other.force_authenticate(user=User.objects.create_user(username='other-owner'))

    institution = Institution.objects.create(name='课程空间', slug='studio-space')
    workspace = Workspace.objects.create(
        institution=institution, service_ends_on=timezone.localdate() + timedelta(days=10), max_students=3,
    )
    WorkspaceMembership.objects.create(workspace=workspace, user=project.user, role='admin')
    school = APIClient()
    school.cookies['auth_token'] = LoginSession.issue(project.user).key
    school.credentials(HTTP_X_UNIMIND_WORKSPACE=str(workspace.pk))
    detail = _url(project, artifact['id'])
    for client in (other, school):
        assert client.get(_url(project)).status_code == 404
        assert client.post(_url(project), {'kind': 'quiz'}, format='json').status_code == 404
        assert client.get(detail).status_code == 404
        assert client.patch(detail, {'title': '越权'}, format='json').status_code == 404
        assert client.delete(detail).status_code == 404
        assert client.post(detail + 'save-note/').status_code == 404
        assert client.post(detail + 'submit-quiz/').status_code == 404
        assert client.get(notes_url).status_code == 404
        assert client.post(notes_url, {'title': '越权'}, format='json').status_code == 404
    assert auth_client.get(detail).data['title'] == artifact['title']
    assert auth_client.get(notes_url).data['notes'] == []
    model.assert_called_once()
