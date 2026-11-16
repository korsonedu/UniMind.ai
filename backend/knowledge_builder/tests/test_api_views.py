import json

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIClient

from knowledge_builder import models, serializers

pytestmark = pytest.mark.django_db


@pytest.fixture
def client(user):
    api = APIClient()
    api.force_authenticate(user=user)
    return api


def test_serializers_explicit_fields():
    for serializer in (
        serializers.CreateBuildSerializer, serializers.BuildSummarySerializer,
        serializers.RequirementIntakeSerializer, serializers.IntakeMessageSerializer,
        serializers.ModuleSerializer, serializers.AtomSerializer, serializers.AtomEdgeSerializer,
        serializers.StepAtomSerializer, serializers.StepSerializer, serializers.BlockSerializer,
        serializers.BlockEdgeSerializer, serializers.InterfaceSerializer,
        serializers.FullKnowledgeTreeSerializer,
        serializers.BlockResourceSerializer, serializers.UserBlockProgressSerializer,
        serializers.AttachBlockResourceSerializer, serializers.BlockQuizRequestSerializer,
        serializers.BlockResourceInputSerializer, serializers.BlockResourceUpdateSerializer,
        serializers.PublicAssetCatalogSerializer, serializers.TreePublicAssetImportSerializer,
    ):
        assert isinstance(serializer.Meta.fields, tuple)
        assert set(serializer().fields) == set(serializer.Meta.fields)


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
def test_create_and_status(client, user, monkeypatch):
    submissions = []
    monkeypatch.setattr('knowledge_builder.views.build_knowledge_tree.delay', submissions.append)
    response = client.post('/', {'subject': ' 微积分极限与连续性 '}, format='json')
    assert response.status_code == 202
    build = models.KnowledgeTreeBuild.objects.get(pk=response.data['id'])
    assert build.created_by == user
    assert build.subject == '微积分极限与连续性'
    assert submissions == [str(build.pk)]
    status = client.get(f'/{build.pk}/status/')
    assert status.status_code == 200
    assert status.data['status'] == 'PENDING'
    assert status.data['stats'] == {}


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
@pytest.mark.parametrize('payload', [{'subject': '  '}, {}, {'subject': '主题', 'archetype': 'invalid'}])
def test_reject_invalid_create(client, payload):
    assert client.post('/', payload, format='json').status_code == 400
    assert not models.KnowledgeTreeBuild.objects.exists()


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
def test_requires_authentication():
    assert APIClient().post('/', {'subject': '主题'}).status_code in (401, 403)


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
def test_owner_only(client):
    other = get_user_model().objects.create_user(username='other', email='other@example.com')
    build = models.KnowledgeTreeBuild.objects.create(subject='主题', created_by=other)
    assert client.get(f'/{build.pk}/').status_code == 404
    assert client.get(f'/{build.pk}/status/').status_code == 404


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
def test_list_and_shared_unowned_builds(client, user):
    other = get_user_model().objects.create_user(username='other2', email='other2@example.com')
    own_pending = models.KnowledgeTreeBuild.objects.create(subject='我的构建', created_by=user, status='PENDING')
    shared_done = models.KnowledgeTreeBuild.objects.create(subject='共享完成学科', created_by=None, status='COMPLETED')
    shared_failed = models.KnowledgeTreeBuild.objects.create(subject='共享失败记录', created_by=None, status='FAILED')
    other_done = models.KnowledgeTreeBuild.objects.create(subject='他人构建', created_by=other, status='COMPLETED')

    response = client.get('/')
    assert response.status_code == 200
    returned_ids = {row['id'] for row in response.data}
    assert returned_ids == {str(own_pending.pk), str(shared_done.pk)}
    assert str(shared_failed.pk) not in returned_ids
    assert str(other_done.pk) not in returned_ids

    assert client.get(f'/{shared_done.pk}/status/').status_code == 200
    assert client.get(f'/{shared_done.pk}/').status_code == 200


def test_mounted_root_urls(client, user):
    build = models.KnowledgeTreeBuild.objects.create(subject='挂载路由测试', created_by=None, status='COMPLETED')
    assert APIClient().get('/api/knowledge-builder/', HTTP_HOST='localhost').status_code in (401, 403)
    list_res = client.get('/api/knowledge-builder/', HTTP_HOST='localhost')
    assert list_res.status_code == 200
    assert any(item['id'] == str(build.pk) for item in list_res.data)
    detail_res = client.get(f'/api/knowledge-builder/{build.pk}/', HTTP_HOST='localhost')
    assert detail_res.status_code == 200
    assert detail_res.data['subject'] == '挂载路由测试'


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
def test_full_tree_json(client, user):
    build = models.KnowledgeTreeBuild.objects.create(subject='主题', created_by=user, status='COMPLETED')
    module = models.TreeModule.objects.create(build=build, code='M1', title='模块', path='模块')
    atoms = [models.TreeAtomPoint.objects.create(
        build=build, module=module, code=f'A{i}', name=f'能力{i}', goal_statement='解释概念',
        parent_path=module.path, goal_type='概念辨析', granularity_minutes=3,
        cognitive_level='理解', key_elements=['概念'],
    ) for i in range(2)]
    models.TreeAtomEdge.objects.create(build=build, from_atom=atoms[0], to_atom=atoms[1], edge_strength='strong', rationale='输出成为输入')
    blocks = [models.LearningBlock.objects.create(build=build, code=f'B{i}', short_title=f'学习块{i}', narrative_summary=atom.name) for i, atom in enumerate(atoms)]
    for block, atom in zip(blocks, atoms):
        step = models.BlockStep.objects.create(block=block, step_index=1, step_title='认识概念', step_role='核心概念')
        models.BlockStepAtom.objects.create(step=step, atom=atom, membership_type='core')
    edge = models.BlockEdge.objects.create(build=build, from_block=blocks[0], to_block=blocks[1], edge_kind='unidirectional')
    models.CrossBlockInterface.objects.create(build=build, block_edge=edge, from_atom=atoms[0], to_atom=atoms[1], interface_role='prerequisite_handoff', bridge_explanation='承接前置能力')
    response = client.get(f'/{build.pk}/')
    assert response.status_code == 200
    data = json.loads(response.content)
    assert len(data['modules']) == 1
    assert len(data['atoms']) == 2
    assert len(data['atom_edges']) == 1
    assert len(data['blocks']) == 2
    assert data['blocks'][0]['steps'][0]['step_atoms'][0]['membership_type'] == 'core'
    assert len(data['block_edges']) == len(data['interfaces']) == 1
    json.dumps(data, allow_nan=False)


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
def test_broker_failure_marks_failed(client, monkeypatch):
    def fail(build_id):
        raise ConnectionError('broker unavailable')
    monkeypatch.setattr('knowledge_builder.views.build_knowledge_tree.delay', fail)
    with pytest.raises(ConnectionError, match='broker unavailable'):
        client.post('/', {'subject': '主题'}, format='json')
    build = models.KnowledgeTreeBuild.objects.get()
    assert build.status == 'FAILED'
    assert 'broker unavailable' in build.error_message


@pytest.fixture
def intake_catalog(settings, monkeypatch):
    from quizzes.models import KnowledgeEdge, KnowledgePoint, Question
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    monkeypatch.setattr('knowledge_builder.intake.config._get_api_key', lambda: '')
    chapters, points, questions = [], [], []
    for i, name in enumerate(('货币银行学', '公司理财', '国际金融'), 1):
        chapter = KnowledgePoint.objects.create(subject='金融431', code=f'M{i}', name=name, level='ch')
        kp = KnowledgePoint.objects.create(subject='金融431', code=f'K{i}', name=f'{name}基础', parent=chapter)
        q = Question.objects.create(knowledge_point=kp, text=f'{name}基础选择题', options=['选项一', '选项二'], correct_answer='A', ai_answer='选项一符合定义。')
        chapters.append(chapter); points.append(kp); questions.append(q)
    KnowledgeEdge.objects.create(source=points[0], target=points[1], edge_type='prerequisite')
    return chapters, points, questions


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
@pytest.mark.parametrize('subject', ['金融431', '431金融学综合', '431'])
def test_intake_cards_catalog_and_cold_start(client, intake_catalog, subject):
    response = client.post('/intake/', {'subject': subject}, format='json')
    assert response.status_code == 200
    data = response.data
    assert data['catalog_match']['matched_subject'] == '金融431'
    assert data['catalog_match']['kp_count'] == 3
    # Existing KP signals also create the two directed parent/child edges per chapter.
    assert data['catalog_match']['edge_count'] == 7
    assert data['catalog_match']['existing_edges'] == [
        {'source': intake_catalog[1][0].name, 'target': intake_catalog[1][1].name, 'edge_type': 'prerequisite'},
    ]
    assert data['needs_diagnostic'] is True
    assert {c['dimension'] for c in data['cards']} == {'goal', 'scope', 'depth', 'prior_knowledge'}
    scope = next(c for c in data['cards'] if c['dimension'] == 'scope')
    assert {o['value'] for o in scope['options']} == {c.name for c in intake_catalog[0]}
    assert len(data['diagnostic_questions']) == 3
    assert all(q['source'] == 'question_bank' for q in data['diagnostic_questions'])
    assert len({q['kp_id'] for q in data['diagnostic_questions']}) == 3
    assert data['requirements_draft']['seed_modules'] == data['catalog_match']['existing_modules']
    assert data['requirements_draft']['seed_edges'] == data['catalog_match']['existing_edges']
    assert data['ready_to_build'] is False
    json.dumps(data, allow_nan=False)


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
def test_intake_seed_edges_prioritize_prerequisites_and_limit(client, intake_catalog):
    from quizzes.models import KnowledgeEdge, KnowledgePoint
    source = intake_catalog[1][0]
    extra_points = KnowledgePoint.objects.bulk_create([
        KnowledgePoint(subject='金融431', name=f'关联知识点{i}') for i in range(22)
    ])
    KnowledgeEdge.objects.bulk_create([
        KnowledgeEdge(source=source, target=point, edge_type='similar', weight=1.0) for point in extra_points
    ])
    prerequisite = KnowledgeEdge.objects.create(source=extra_points[-1], target=source, edge_type='prerequisite', weight=.5)
    KnowledgeEdge.objects.create(source=extra_points[-2], target=source, edge_type='prerequisite', is_active=False)
    # Even a mislabeled parent/child edge must not become a prior dependency.
    KnowledgeEdge.objects.create(source=intake_catalog[0][0], target=source, edge_type='prerequisite')
    KnowledgeEdge.objects.create(source=source, target=intake_catalog[0][0], edge_type='prerequisite')
    data = client.post('/intake/', {'subject': '431'}, format='json').data
    edges = data['catalog_match']['existing_edges']
    assert len(edges) == 20
    assert edges[:2] == [
        {'source': source.name, 'target': intake_catalog[1][1].name, 'edge_type': 'prerequisite'},
        {'source': prerequisite.source.name, 'target': source.name, 'edge_type': 'prerequisite'},
    ]
    assert all(edge['edge_type'] == 'similar' for edge in edges[2:])
    assert data['requirements_draft']['seed_edges'] == edges


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
def test_intake_chat_grades_and_updates_scoped_state(client, user, intake_catalog):
    from quizzes.models import UserKnowledgeState
    chapters, points, bank = intake_catalog
    UserKnowledgeState.objects.create(user=user, knowledge_point=points[0], mastery_score=.9)
    UserKnowledgeState.objects.create(user=user, knowledge_point=points[1], mastery_score=.6)
    initial = client.post('/intake/', {'subject': '431'}, format='json').data
    qs = initial['diagnostic_questions']
    response = client.post('/intake/', dict(subject='431', mode='chat',
        messages=[dict(role='user', content='目标是431应试，重点公司理财，需要逐步推导，学过货币银行学基础。')],
        self_report='学过货币银行学，CAPM不熟', diagnostic_questions=qs,
        diagnostic_answers={qs[0]['id']: 'A', str(bank[1].pk): 'B', qs[2]['id']: 'A'}), format='json')
    assert response.status_code == 200
    data = response.data
    baseline = data['requirements_draft']['baseline_summary']
    assert baseline['answered_count'] == 3
    assert baseline['correct_count'] == 2
    assert baseline['accuracy'] == .67
    assert baseline['known_topics'] == [points[0].name, points[2].name]
    assert baseline['gap_topics'] == [points[1].name]
    assert '不删前置节点' in baseline['entry_strategy']
    assert data['ready_to_build'] is True
    assert '公司理财' in data['requirements_draft']['scope_inclusions']
    assert UserKnowledgeState.objects.get(user=user, knowledge_point=points[0]).mastery_score == .9
    assert UserKnowledgeState.objects.get(user=user, knowledge_point=points[1]).mastery_score == .35
    assert UserKnowledgeState.objects.get(user=user, knowledge_point=points[2]).mastery_score == .75
    refreshed = client.post('/intake/', {'subject': '431'}, format='json').data['catalog_match']
    assert refreshed['needs_diagnostic'] is False
    assert refreshed['assessed_kp_count'] == 3
    assert refreshed['avg_mastery'] == .67
    assert points[1].name in refreshed['weak_topics']


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
def test_intake_card_custom_and_partial_test(client, intake_catalog):
    initial = client.post('/intake/', {'subject': '431'}, format='json').data
    q = initial['diagnostic_questions'][0]
    response = client.post('/intake/', dict(subject='431', card_answers={
        'goal': {'selected': ['431应试复习'], 'custom': '课程期末也要用'},
        'scope': {'selected': ['公司理财'], 'custom': '排除：国际金融专题'},
        'depth': '逐步推导与计算', 'prior_knowledge': '学过但不熟'},
        diagnostic_questions=initial['diagnostic_questions'], diagnostic_answers={q['id']: 'B'}), format='json')
    draft = response.data['requirements_draft']
    assert response.data['ready_to_build'] is True
    assert draft['scope_exclusions'] == ['国际金融专题']
    assert draft['baseline_summary']['answered_count'] == 1
    assert draft['baseline_summary']['correct_count'] == 0
    assert draft['baseline_summary']['accuracy'] == 0.0


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
def test_intake_unknown_subject_offline(client, settings, monkeypatch):
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    monkeypatch.setattr('knowledge_builder.intake.config._get_api_key', lambda: '')
    data = client.post('/intake/', dict(subject='古文字学', mode='chat', messages=[dict(role='user', content='我想系统学习古文字学')]), format='json').data
    assert data['catalog_match']['matched_subject'] is None
    assert data['needs_diagnostic'] is True
    assert len(data['diagnostic_questions']) == 3
    assert all(q['source'] == 'ai_probe' and q['kp_id'] is None for q in data['diagnostic_questions'])
    assert '章节' in data['assistant_reply']
    for q in data['diagnostic_questions']:
        assert q['correct_answer'] in {o['key'] for o in q['options']}
    json.dumps(data, allow_nan=False)


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
def test_intake_llm_failure_and_generated_questions(client, intake_catalog, monkeypatch):
    from quizzes.models import Question
    Question.objects.all().delete()
    monkeypatch.setattr('knowledge_builder.intake.config._get_api_key', lambda: 'test-key')
    def fail(*args):
        raise RuntimeError('offline')
    monkeypatch.setattr('knowledge_builder.intake.prompts.ask', fail)
    response = client.post('/intake/', {'subject': '431'}, format='json')
    assert response.status_code == 200
    assert len(response.data['cards']) == 4
    assert len(response.data['diagnostic_questions']) == 3
    from knowledge_builder.intake import _default_cards
    ai_questions = [dict(topic=f'公司理财{i}', stem=f'基础问题{i}', options={'A': '正确陈述', 'B': '错误陈述'}, correct_answer='A', explanation='定义如此。') for i in range(3)]
    monkeypatch.setattr('knowledge_builder.intake.prompts.ask', lambda *args: dict(cards=_default_cards('431', response.data['catalog_match']), diagnostic_questions=ai_questions))
    generated = client.post('/intake/', {'subject': '431'}, format='json').data
    assert generated['diagnostic_questions'][0]['stem'] == '基础问题0'
    assert all(q['kp_id'] is None for q in generated['diagnostic_questions'])
    answers = {q['id']: 'A' for q in generated['diagnostic_questions']}
    graded = client.post('/intake/', dict(subject='431', diagnostic_questions=generated['diagnostic_questions'], diagnostic_answers=answers), format='json').data
    assert graded['requirements_draft']['baseline_summary']['correct_count'] == 3


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
def test_intake_security_and_validation(client, user, intake_catalog, settings):
    from quizzes.models import UserKnowledgeState
    assert APIClient().post('/intake/', {'subject': '431'}, format='json').status_code in (401, 403)
    for payload in ({'subject': ' '}, {'subject': '431', 'mode': 'wrong'}, {'subject': '431', 'messages': [{'role': 'system', 'content': 'x'}]}):
        assert client.post('/intake/', payload, format='json').status_code == 400
    initial = client.post('/intake/', {'subject': '431'}, format='json').data
    questions = initial['diagnostic_questions']
    questions[0]['correct_answer'] = 'B'
    questions[0]['kp_id'] = intake_catalog[1][1].pk
    graded = client.post('/intake/', dict(subject='431', diagnostic_questions=questions, diagnostic_answers={questions[0]['id']: 'B'}), format='json')
    assert graded.data['requirements_draft']['baseline_summary']['correct_count'] == 0
    assert not UserKnowledgeState.objects.filter(user=user, knowledge_point=intake_catalog[1][1]).exists()
    questions[0]['signed_payload'] = 'forged'
    assert client.post('/intake/', dict(subject='431', diagnostic_questions=questions), format='json').status_code == 400
    assert client.post('/intake/', dict(subject='408', diagnostic_questions=initial['diagnostic_questions'][1:]), format='json').status_code == 400
    settings.UNIMIND_CONTENT_INSTITUTION_ID = None
    assert client.post('/intake/', {'subject': '431'}, format='json').status_code == 403


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
def test_intake_institution_isolation(client, user, intake_catalog, settings):
    from quizzes.models import KnowledgePoint, Question, UserKnowledgeState
    from users.models import Institution
    institution = Institution.objects.create(name='另一机构')
    hidden = KnowledgePoint.objects.create(subject='金融431', name='不可见知识点', institution=institution)
    Question.objects.create(institution=institution, knowledge_point=hidden, text='不可见题目', options=['一', '二'], correct_answer='A')
    # A global question linked to a foreign knowledge point must also be excluded.
    Question.objects.create(knowledge_point=hidden, text='错误跨范围关联', options=['一', '二'], correct_answer='A')
    UserKnowledgeState.objects.create(user=user, knowledge_point=hidden, mastery_score=.9)
    response = client.post('/intake/', {'subject': '431'}, format='json')
    assert response.data['catalog_match']['kp_count'] == 3
    assert response.data['catalog_match']['assessed_kp_count'] == 0
    assert all(q['kp_id'] != hidden.pk for q in response.data['diagnostic_questions'])
    settings.UNIMIND_CONTENT_INSTITUTION_ID = institution.pk
    own = client.post('/intake/', {'subject': '431'}, format='json').data
    assert own['catalog_match']['kp_count'] == 1
    assert own['catalog_match']['assessed_kp_count'] == 1
    assert sum(q['source'] == 'question_bank' for q in own['diagnostic_questions']) == 1


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
def test_intake_workspace_content_and_revoked_access(client, user, intake_catalog, settings):
    from django.utils import timezone
    from quizzes.models import KnowledgeEdge, KnowledgePoint, Question, UserKnowledgeState
    from users.models import Institution
    from users.models_workspace import Workspace, WorkspaceMembership

    institution = Institution.objects.create(name='机构知识构建')
    workspace = Workspace.objects.create(
        institution=institution, service_ends_on=timezone.localdate(), max_students=10,
    )
    membership = WorkspaceMembership.objects.create(user=user, workspace=workspace)
    points = []
    for index in range(3):
        point = KnowledgePoint.objects.create(
            institution=institution, subject='金融431', code=f'W{index}', name=f'机构知识点{index}',
        )
        Question.objects.create(
            institution=institution, knowledge_point=point, text=f'机构题目{index}',
            options=['正确', '错误'], correct_answer='A',
        )
        points.append(point)
    KnowledgeEdge.objects.create(
        institution=institution, source=points[0], target=points[1], edge_type='prerequisite',
    )
    # Workspace content must resolve independently of the platform content setting.
    settings.UNIMIND_CONTENT_INSTITUTION_ID = None
    initial = client.post('/intake/', {'subject': '431'}, format='json')
    assert initial.status_code == 200
    assert initial.data['catalog_match']['kp_count'] == 3
    assert initial.data['catalog_match']['existing_edges'] == [
        {'source': points[0].name, 'target': points[1].name, 'edge_type': 'prerequisite'},
    ]
    questions = initial.data['diagnostic_questions']
    assert {question['kp_id'] for question in questions} == {point.pk for point in points}
    payload = dict(subject='431', diagnostic_questions=questions,
                   diagnostic_answers={question['id']: 'A' for question in questions})
    graded = client.post('/intake/', payload, format='json')
    assert graded.status_code == 200
    assert graded.data['requirements_draft']['baseline_summary']['correct_count'] == 3
    assert UserKnowledgeState.objects.filter(user=user, knowledge_point__in=points).count() == 3
    assert not UserKnowledgeState.objects.filter(user=user, knowledge_point__in=intake_catalog[1]).exists()

    membership.is_active = False
    membership.save(update_fields=['is_active'])
    unavailable = client.post('/intake/', {'subject': '431'}, format='json')
    assert unavailable.status_code == 200
    assert unavailable.data['catalog_match']['matched_subject'] is None
    assert all(question['source'] == 'ai_probe' for question in unavailable.data['diagnostic_questions'])
    assert client.post('/intake/', payload, format='json').status_code == 400


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
def test_create_requirements_persist_and_return(client, monkeypatch):
    monkeypatch.setattr('knowledge_builder.views.build_knowledge_tree.delay', lambda *_: None)
    requirements = dict(learning_goal='431应试', scope_inclusions=['公司理财'], baseline_summary={'accuracy': .75}, suggested_entry_topics=['CAPM'])
    response = client.post('/', {'subject': '金融431', 'requirements': requirements}, format='json')
    assert response.status_code == 202
    build = models.KnowledgeTreeBuild.objects.get(pk=response.data['id'])
    assert build.requirements == requirements
    for path in (f'/{build.pk}/status/', f'/{build.pk}/'):
        assert client.get(path).data['requirements'] == requirements
    for value in ([], 'invalid', {'accuracy': float('nan')}, {'accuracy': float('inf')}):
        serializer = serializers.CreateBuildSerializer(data={'subject': '主题', 'requirements': value})
        assert not serializer.is_valid()


def test_requirements_in_all_six_pipeline_stages(monkeypatch):
    from knowledge_builder.tests.test_pipeline_e2e import SemanticFixture
    from knowledge_builder.pipeline import create_build, run_build, base_context
    from ai_engine import config
    from ai_engine.ai_service import AIService
    fixture = SemanticFixture()
    requirements = dict(learning_goal='期末复习', scope_inclusions=['极限'], scope_exclusions=['级数'], depth_preference='逐步推导', learner_background='基础薄弱', baseline_summary={'accuracy': .5}, suggested_entry_topics=['极限'], seed_modules=[], seed_edges=[{'source': '极限', 'target': '连续性', 'edge_type': 'prerequisite'}])
    seen = set()
    def ai(**kwargs):
        system, prompt = kwargs['system_prompt'], kwargs['user_prompt']
        shared = json.loads(system[system.index('\n{') + 1:]) if '\n{' in system else {}
        payload = {**shared, **json.loads(prompt[prompt.index('\n{') + 1:])}
        assert payload['requirements'] == requirements
        seen.add(kwargs['tool_name'])
        return fixture.ai(**kwargs)
    monkeypatch.setattr(config, 'EMBEDDING_BASE_URL', 'http://127.0.0.1:8012/v1')
    monkeypatch.setattr(config, 'EMBEDDING_DIMENSIONS', 24)
    monkeypatch.setattr(AIService, 'structured_output', ai)
    monkeypatch.setattr('knowledge_builder.embedding_client.httpx.post', fixture.http)
    build = create_build('微积分极限与连续性', requirements=requirements)
    stages = []
    result = run_build(build.pk, progress=stages.append)
    assert result.status == 'COMPLETED'
    assert len(stages) == 6
    assert {'archetype_classify', 'outline_decompose', 'atom_generate', 'edge_classify', 'block_naming', 'interblock_review', 'intrablock_steps', 'interface_bind'} <= seen
    assert result.requirements == requirements
    assert base_context(create_build('默认主题')) == {'subject': '默认主题'}


@pytest.mark.parametrize('content,answer', [
    ({'stem': '题干', 'options': {'A': '选一', 'B': '选二'}}, 'A'),
    ({'question': '题干', 'choices': ['选一', '选二']}, 'B'),
    ({'title': '题干', 'options': [{'key': 'A', 'text': '选一'}, {'key': 'B', 'label': '选二'}]}, 'A'),
    ({'stem': '判断题'}, '正确'),
])
def test_bank_question_import_formats(intake_catalog, content, answer):
    from knowledge_builder.intake import _bank_question
    q = intake_catalog[2][0]
    q.text = json.dumps(content, ensure_ascii=False)
    q.options = None
    q.correct_answer = answer
    normalized = _bank_question(q)
    assert normalized['stem'] in ('题干', '判断题')
    assert normalized['correct_answer'] in {o['key'] for o in normalized['options']}
    assert len(normalized['options']) == 2


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
def test_intake_chat_revises_cards_and_asks_missing_dimension(client, intake_catalog):
    data = client.post('/intake/', dict(subject='431', mode='chat', card_answers={
        'goal': '431应试复习', 'scope': ['国际金融'], 'depth': '概念与框架', 'prior_knowledge': '从零开始'},
        messages=[{'role': 'user', 'content': '这次目标改为课程期末，重点公司理财，需要逐步推导，基础不熟。'}]), format='json').data
    draft = data['requirements_draft']
    assert data['ready_to_build'] is True
    assert draft['learning_goal'] == '这次目标改为课程期末'
    assert draft['scope_inclusions'] == ['公司理财']
    assert draft['depth_preference'] == '需要逐步推导'
    assert draft['learner_background'] == '基础不熟'


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
def test_intake_case_insensitive_and_408_alias(client, intake_catalog):
    from quizzes.models import KnowledgePoint
    KnowledgePoint.objects.create(subject='计算机408', name='数据结构', level='ch')
    KnowledgePoint.objects.create(subject='Python', name='基本语法', level='ch')
    assert client.post('/intake/', {'subject': '408'}, format='json').data['catalog_match']['matched_subject'] == '计算机408'
    assert client.post('/intake/', {'subject': 'python入门'}, format='json').data['catalog_match']['matched_subject'] == 'Python'


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
def test_intake_offline_multiturn_follows_its_questions(client, intake_catalog):
    messages = []
    for answer in ('准备课程期末', '完整学科', '综合应用', '学过但不熟'):
        messages.append({'role': 'user', 'content': answer})
        response = client.post('/intake/', dict(subject='431', mode='chat', messages=messages), format='json')
        assert response.status_code == 200
        messages.append({'role': 'assistant', 'content': response.data['assistant_reply']})
    assert response.data['ready_to_build'] is True
    draft = response.data['requirements_draft']
    assert draft['learning_goal'] == '准备课程期末'
    assert draft['scope_inclusions'] == ['完整学科']
    assert draft['depth_preference'] == '综合应用'
    assert draft['learner_background'] == '学过但不熟'


@pytest.fixture
def study_block(user, monkeypatch):
    monkeypatch.setattr('knowledge_builder.block_study.config._get_api_key', lambda: '')
    build = models.KnowledgeTreeBuild.objects.create(subject='公司理财', created_by=user, status='COMPLETED')
    module = models.TreeModule.objects.create(build=build, code='M1', title='价值', path='价值')
    block = models.LearningBlock.objects.create(build=build, code='B1', short_title='现金流折现', narrative_summary='分析价值')
    step = models.BlockStep.objects.create(block=block, step_index=1, step_title='折现', step_role='机制')
    for index, name in enumerate(('现金流', '折现率', '终值', '风险')):
        atom = models.TreeAtomPoint.objects.create(build=build, module=module, code=f'A{index}', name=name,
            goal_statement=f'解释{name}如何影响估值', cognitive_level='理解', goal_type='机制', granularity_minutes=4,
            key_elements=[f'{name}的定义', f'{name}的适用条件'],
            common_misconceptions=[f'{name}始终固定', f'{name}不受条件影响', f'忽略{name}也能估值'])
        models.BlockStepAtom.objects.create(step=step, atom=atom, membership_type='core' if index < 2 else 'extension', position=index)
    return block


def _quiz_answers(questions):
    from django.core import signing
    from knowledge_builder.block_study import SIGNING_SALT
    return {question['id']: signing.loads(question['signed_payload'], salt=SIGNING_SALT)['correct_answer'] for question in questions}


@override_settings(ROOT_URLCONF='knowledge_builder.urls', UNIMIND_CONTENT_INSTITUTION_ID=None)
def test_block_auto_mount_internal_and_optional_scope(study_block, user):
    from django.utils import timezone
    from ai_assistant.models import LearningResource
    from courses.models import Course, CourseModule
    from knowledge_builder.block_study import auto_mount_internal_resources
    from core.utils import get_content_institution_id
    from rest_framework.exceptions import PermissionDenied
    public = CourseModule.objects.create(name='公开', is_public=True)
    course = Course.objects.create(title='现金流讲解', is_published=True, module=public)
    Course.objects.create(title='现金流未发布', is_published=False, module=public)
    Course.objects.create(title='现金流受限', is_published=True)
    library = LearningResource.objects.create(user=user, title='折现率笔记', url='https://example.org/note',
        url_hash='note', excerpt='折现率的定义', read_at=timezone.now())
    LearningResource.objects.create(user=user, title='现金流归档', url='https://example.org/archive',
        url_hash='archive', excerpt='现金流', read_at=timezone.now(), is_archived=True)
    auto_mount_internal_resources(study_block.build)
    auto_mount_internal_resources(study_block.build)
    resources = study_block.resources.all()
    assert resources.count() == 2
    assert resources.get(source_kind='course').course_id == course.pk
    assert resources.get(source_kind='library').library_resource_id == library.pk
    assert all(resource.atom_id and resource.step_id for resource in resources)
    assert get_content_institution_id(required=False) is None
    with pytest.raises(PermissionDenied):
        get_content_institution_id()


@override_settings(ROOT_URLCONF='knowledge_builder.urls', UNIMIND_CONTENT_INSTITUTION_ID='global')
def test_block_resource_search_attach_library_delete(client, study_block, user, monkeypatch):
    monkeypatch.setattr('knowledge_builder.public_asset_resolvers.search_wikipedia_concepts', lambda *args, **kwargs: [])
    from ai_assistant.models import LearningResource
    calls = []
    def public_text(url):
        calls.append(url)
        if 'format=rss' in url:
            return url, '<rss><channel><item><title>现金流教程</title><link>https://example.org/lesson</link><description>讲解</description></item><item><link>http://example.org/insecure</link></item></channel></rss>'
        return url, '<html><head><title>现金流教程</title><script>secret</script></head><body>现金流的定义与适用条件</body></html>'
    monkeypatch.setattr('ai_assistant.services.learning_resources.public_text', public_text)
    path = f'/{study_block.build_id}/blocks/{study_block.pk}/resources/'
    assert client.get(path).status_code == 200
    assert not calls
    search = client.get(path, {'query': '现金流'}).data
    assert len(search['web_candidates']) == 1
    response = client.post(path, {'url': 'https://example.org/lesson', 'save_to_library': True}, format='json')
    assert response.status_code == 201
    resource = models.BlockResource.objects.get(pk=response.data['id'])
    assert resource.atom.name == '现金流'
    assert '现金流的定义' in resource.excerpt and 'secret' not in resource.excerpt
    library = LearningResource.objects.get(pk=resource.library_resource_id)
    assert library.user_id == user.pk and library.versions.count() == 1
    response = client.post(path, {'url': 'https://example.org/lesson', 'save_to_library': True}, format='json')
    assert response.status_code == 201
    library.refresh_from_db()
    assert library.revision == 2 and library.versions.count() == 2
    assert client.get(path).data['resources'][0]['id'] == resource.pk
    assert client.delete(path, {'resource_id': resource.pk}, format='json').status_code == 204
    assert LearningResource.objects.filter(pk=library.pk).exists()
    assert client.post(path, {'url': 'http://example.org'}, format='json').status_code == 400
    other = models.KnowledgeTreeBuild.objects.create(subject='other')
    other_block = models.LearningBlock.objects.create(build=other, code='other', short_title='other')
    other_step = models.BlockStep.objects.create(block=other_block, step_index=1)
    assert client.post(path, {'url': 'https://example.org', 'step_id': other_step.pk}, format='json').status_code == 400


@override_settings(ROOT_URLCONF='knowledge_builder.urls', UNIMIND_CONTENT_INSTITUTION_ID='global')
def test_block_resource_visibility(client, study_block, user, monkeypatch):
    monkeypatch.setattr('knowledge_builder.public_asset_resolvers.search_wikipedia_concepts', lambda *args, **kwargs: [])
    from django.utils import timezone
    from ai_assistant.models import LearningResource
    from courses.models import Course, CourseModule
    from users.models import Institution
    other = get_user_model().objects.create_user(username='resource_other')
    foreign = LearningResource.objects.create(user=other, title='现金流私有笔记', url='https://example.org/private',
        url_hash='private', excerpt='私密笔记', read_at=timezone.now())
    public = CourseModule.objects.create(name='public', is_public=True)
    course = Course.objects.create(title='现金流课程', is_published=True, module=public)
    inst = Institution.objects.create(name='其他机构')
    restricted = Course.objects.create(title='现金流课程', is_published=True, institution=inst, module=public)
    path = f'/{study_block.build_id}/blocks/{study_block.pk}/resources/'
    assert client.post(path, {'course_id': restricted.pk}, format='json').status_code == 400
    assert client.post(path, {'library_resource_id': foreign.pk}, format='json').status_code == 400
    assert client.post(path, {'course_id': course.pk}, format='json').status_code == 201
    assert client.get(f'/{study_block.build_id}/blocks/999999/resources/').status_code == 404
    own = client.post(path, {'url': 'javascript:alert(1)'}, format='json')
    assert own.status_code == 400
    private = models.BlockResource.objects.create(build=study_block.build, block=study_block, source_kind='library',
        title=foreign.title, url=foreign.url, excerpt=foreign.excerpt, library_resource_id=foreign.pk, created_by=other)
    assert private.pk not in {row['id'] for row in client.get(path).data['resources']}
    assert private.pk not in {row['id'] for row in client.get(f'/{study_block.build_id}/').data['blocks'][0]['resources']}
    client.force_authenticate(user=other)
    assert client.get(path).status_code == 404


@override_settings(ROOT_URLCONF='knowledge_builder.urls', UNIMIND_CONTENT_INSTITUTION_ID='global')
@pytest.mark.parametrize('mode,count', [('objective', 4), ('challenge', 5)])
def test_block_quiz_modes_and_offline_grading(client, study_block, mode, count):
    path = f'/{study_block.build_id}/blocks/{study_block.pk}/quiz/'
    response = client.post(path, {'mode': mode}, format='json')
    assert response.status_code == 200
    questions = response.data['questions']
    assert len(questions) == count
    assert not any('correct_answer' in question or 'explanation' in question for question in questions)
    assert all(question['signed_payload'] for question in questions)
    if mode == 'challenge':
        assert questions[-1]['q_type'] == 'subjective'
        from django.core import signing
        from knowledge_builder.block_study import SIGNING_SALT
        item = signing.loads(questions[-1]['signed_payload'], salt=SIGNING_SALT)
        assert item['grading_points'] and item['rubric']
    result = client.post(path, {'action': 'submit', 'questions': questions, 'answers': _quiz_answers(questions)}, format='json')
    assert result.status_code == 200
    assert result.data['block_completed'] and result.data['accuracy'] == 1
    assert result.data['core_passed'] and result.data['status'] == 'COMPLETED'
    detail = client.get(f'/{study_block.build_id}/').data
    assert detail['block_progress'][0]['status'] == 'COMPLETED'
    assert serializers.FullKnowledgeTreeSerializer(study_block.build).data['block_progress'] == []


@override_settings(ROOT_URLCONF='knowledge_builder.urls', UNIMIND_CONTENT_INSTITUTION_ID='global')
def test_block_quiz_review_retest_completion_and_mastery(client, study_block, user):
    from quizzes.models import KnowledgePoint, Question, UserKnowledgeState
    from users.models import Institution
    kp = KnowledgePoint.objects.create(name='现金流')
    Question.objects.create(knowledge_point=kp, text='银行题：现金流如何计算？', options=['正确概念', '常见误区', '其他误区', '明显误区'], correct_answer='A')
    foreign = Institution.objects.create(name='隔离机构')
    foreign_kp = KnowledgePoint.objects.create(name='折现率', institution=foreign)
    Question.objects.create(knowledge_point=foreign_kp, institution=foreign, text='不得抽取此题', options=['甲', '乙', '丙', '丁'], correct_answer='A')
    path = f'/{study_block.build_id}/blocks/{study_block.pk}/quiz/'
    questions = client.post(path, {}, format='json').data['questions']
    assert questions[0]['stem'] == '银行题：现金流如何计算？'
    assert all(question['stem'] != '不得抽取此题' for question in questions)
    answers = _quiz_answers(questions)
    weak_atom_id = questions[0]['atom_id']
    answers[questions[0]['id']] = 'B'
    resource = models.BlockResource.objects.create(build=study_block.build, block=study_block, atom_id=weak_atom_id, title='回看现金流', url='https://example.org/review')
    data = client.post(path, {'action': 'submit', 'questions': questions, 'answers': answers}, format='json').data
    assert data['accuracy'] == .75 and not data['core_passed']
    assert data['status'] == 'NEEDS_REVIEW' and data['weak_atom_ids'] == [weak_atom_id]
    assert data['recommended_resources'][0]['id'] == resource.pk
    assert not UserKnowledgeState.objects.filter(user=user).exists()
    retest = client.post(path, {'retest': True}, format='json').data['questions']
    assert {question['stem'] for question in questions}.isdisjoint(question['stem'] for question in retest)
    assert retest[0]['atom_id'] == weak_atom_id
    data = client.post(path, {'action': 'submit', 'questions': retest, 'answers': _quiz_answers(retest)}, format='json').data
    assert data['status'] == 'COMPLETED' and data['weak_atom_ids'] == [] and data['attempt_count'] == 2
    assert UserKnowledgeState.objects.get(user=user, knowledge_point=kp).mastery_score == .8
    assert not UserKnowledgeState.objects.filter(knowledge_point=foreign_kp).exists()


@override_settings(ROOT_URLCONF='knowledge_builder.urls', UNIMIND_CONTENT_INSTITUTION_ID='global')
def test_block_quiz_low_accuracy_with_core_correct(client, study_block):
    path = f'/{study_block.build_id}/blocks/{study_block.pk}/quiz/'
    questions = client.post(path, {}, format='json').data['questions']
    answers = _quiz_answers(questions)
    for question in questions:
        if question['membership_type'] == 'extension':
            answers[question['id']] = 'not-a-choice'
    data = client.post(path, {'action': 'submit', 'questions': questions, 'answers': answers}, format='json').data
    assert data['core_passed'] and data['accuracy'] == .5 and data['status'] == 'NEEDS_REVIEW'
    assert set(data['weak_atom_ids']) == {question['atom_id'] for question in questions if question['membership_type'] == 'extension'}


@override_settings(ROOT_URLCONF='knowledge_builder.urls', UNIMIND_CONTENT_INSTITUTION_ID='global')
def test_block_quiz_rejects_tampering_omissions_and_wrong_block(client, study_block, user):
    path = f'/{study_block.build_id}/blocks/{study_block.pk}/quiz/'
    questions = client.post(path, {}, format='json').data['questions']
    answers = _quiz_answers(questions)
    def submit(items, target=path):
        return client.post(target, {'action': 'submit', 'questions': items, 'answers': answers}, format='json')
    assert submit(questions[:1]).status_code == 400
    assert submit([questions[0]] * len(questions)).status_code == 400
    assert submit([{**questions[0], 'signed_payload': 'tampered'}, *questions[1:]]).status_code == 400
    other_block = models.LearningBlock.objects.create(build=study_block.build, code='B2', short_title='其他')
    assert submit(questions, f'/{study_block.build_id}/blocks/{other_block.pk}/quiz/').status_code == 400
    other = get_user_model().objects.create_user(username='quiz_other')
    study_block.build.created_by = None
    study_block.build.save()
    client.force_authenticate(user=other)
    assert submit(questions).status_code == 400
    assert client.post(path, {'mode': 'invalid'}, format='json').status_code == 400
    assert client.post(path, {'retest': 'invalid'}, format='json').status_code == 400
    assert models.UserBlockProgress.objects.get(user=user, block=study_block).attempt_count == 0


@override_settings(ROOT_URLCONF='knowledge_builder.urls', UNIMIND_CONTENT_INSTITUTION_ID='global')
def test_block_ai_generation_and_grading_reuse(client, study_block, monkeypatch):
    from django.core import signing
    from knowledge_builder.block_study import SIGNING_SALT
    from quizzes.services.question_generator import QuestionGenerator
    from quizzes.services.ai_task_service import QuizAITaskService
    monkeypatch.setattr('knowledge_builder.block_study.config._get_api_key', lambda: 'test-key')
    calls = []
    def generate(self, kps_data, count, types, difficulty, ratio):
        calls.append(kps_data)
        if types == ['objective']:
            return [{'q_type': 'objective', 'question': f'{kps_data[0]["name"]}的全新选择题', 'options': ['A.正确', 'B.误区一', 'C.误区二', 'D.误区三'], 'answer': 'A'}]
        return [{'q_type': 'subjective', 'subjective_type': 'calculate', 'question': '请推导现值公式', 'answer': '现值定义；适用条件', 'grading_points': ['现值定义', '适用条件']}]
    monkeypatch.setattr(QuestionGenerator, '_request_bulk_generate_once', generate)
    grading_calls = []
    def grade(cls, ai, **kwargs):
        grading_calls.append(kwargs)
        return {'score': 7.5, 'feedback': '推导完整，达到要求', 'memorix_rating': 4}
    monkeypatch.setattr(QuizAITaskService, 'grade_question', classmethod(grade))
    path = f'/{study_block.build_id}/blocks/{study_block.pk}/quiz/'
    questions = client.post(path, {'mode': 'challenge'}, format='json').data['questions']
    assert all('常见误区' in call[0]['description'] for call in calls)
    signed = signing.loads(questions[-1]['signed_payload'], salt=SIGNING_SALT)
    assert signed['rubric'] and signed['subjective_type'] == 'calculate'
    data = client.post(path, {'action': 'submit', 'questions': questions, 'answers': _quiz_answers(questions)}, format='json').data
    assert len(grading_calls) == 1 and grading_calls[0]['rubric']
    assert data['results'][-1]['score_ratio'] == .75 and data['block_completed']
    def fail(*args, **kwargs):
        raise RuntimeError('API unavailable')
    monkeypatch.setattr(QuestionGenerator, '_request_bulk_generate_once', fail)
    monkeypatch.setattr(QuizAITaskService, 'grade_question', fail)
    fallback = client.post(path, {'mode': 'challenge', 'retest': True}, format='json').data['questions']
    data = client.post(path, {'action': 'submit', 'questions': fallback, 'answers': _quiz_answers(fallback)}, format='json').data
    assert data['block_completed'] and data['results'][-1]['score_ratio'] == 1


@override_settings(UNIMIND_CONTENT_INSTITUTION_ID=None)
def test_run_build_mounts_resources_after_publication(user, monkeypatch):
    monkeypatch.setattr('knowledge_builder.public_asset_resolvers.load_seed_public_assets', lambda *args, **kwargs: [])
    from django.utils import timezone
    from courses.models import Course, CourseModule
    from ai_assistant.models import LearningResource
    from ai_engine.ai_service import AIService
    from knowledge_builder.tests.test_pipeline_e2e import SemanticFixture
    from knowledge_builder.pipeline import create_build, run_build
    fixture = SemanticFixture()
    monkeypatch.setattr(AIService, 'structured_output', fixture.ai)
    monkeypatch.setattr('knowledge_builder.embedding_client.httpx.post', fixture.http)
    public = CourseModule.objects.create(name='公开极限课', is_public=True)
    Course.objects.create(title='极限能力1课程', is_published=True, module=public)
    LearningResource.objects.create(user=user, title='连续性能力1资料', url='https://example.org/continuity',
        url_hash='continuity', excerpt='连续性能力1的讲解', read_at=timezone.now())
    build = run_build(create_build('微积分', created_by=user).pk)
    assert build.status == 'COMPLETED'
    assert set(build.block_resources.values_list('source_kind', flat=True)) == {'course', 'library'}
    def failed_mount(build):
        models.BlockResource.objects.create(build=build, block=build.blocks.first(), title='待回滚', url='https://example.org')
        raise RuntimeError('matching unavailable')
    monkeypatch.setattr('knowledge_builder.block_study.auto_mount_internal_resources', failed_mount)
    build = run_build(create_build('微积分', created_by=user).pk)
    assert build.status == 'COMPLETED' and build.blocks.exists()
    assert not build.block_resources.exists()


@override_settings(ROOT_URLCONF='knowledge_builder.urls', UNIMIND_CONTENT_INSTITUTION_ID='global')
def test_block_all_core_coverage_and_no_core_rule(client, study_block):
    step = study_block.steps.first()
    for index in range(4, 7):
        atom = models.TreeAtomPoint.objects.create(build=study_block.build, module=study_block.build.modules.first(),
            code=f'A{index}', name=f'核心点{index}', goal_statement=f'解释核心点{index}', cognitive_level='理解', goal_type='概念', granularity_minutes=4)
        models.BlockStepAtom.objects.create(step=step, atom=atom, membership_type='core', position=index)
    path = f'/{study_block.build_id}/blocks/{study_block.pk}/quiz/'
    questions = client.post(path, {}, format='json').data['questions']
    core_ids = set(models.BlockStepAtom.objects.filter(step__block=study_block, membership_type='core').values_list('atom_id', flat=True))
    assert core_ids <= {question['atom_id'] for question in questions}
    result = client.post(path, {'action': 'submit', 'questions': questions, 'answers': _quiz_answers(questions)}, format='json').data
    assert result['block_completed']
    models.BlockStepAtom.objects.filter(step__block=study_block).update(membership_type='extension')
    questions = client.post(path, {}, format='json').data['questions']
    answers = _quiz_answers(questions)
    answers[questions[0]['id']] = 'invalid'
    result = client.post(path, {'action': 'submit', 'questions': questions, 'answers': answers}, format='json').data
    assert result['accuracy'] == .75 and not result['block_completed'] and not result['core_passed']


@override_settings(ROOT_URLCONF='knowledge_builder.urls', UNIMIND_CONTENT_INSTITUTION_ID='global')
def test_challenge_threshold_and_ai_format_validation(client, study_block, monkeypatch):
    from quizzes.services.question_generator import QuestionGenerator
    from quizzes.services.ai_task_service import QuizAITaskService
    monkeypatch.setattr('knowledge_builder.block_study.config._get_api_key', lambda: 'test-key')
    # A malformed LaTeX answer must be replaced through the explicit offline path.
    def malformed(*args):
        return [{'q_type': 'objective', 'question': '断裂公式 $x', 'options': ['甲', '乙', '丙', '丁'], 'answer': 'A'}]
    monkeypatch.setattr(QuestionGenerator, '_request_bulk_generate_once', malformed)
    path = f'/{study_block.build_id}/blocks/{study_block.pk}/quiz/'
    questions = client.post(path, {'mode': 'challenge'}, format='json').data['questions']
    assert all('断裂公式' not in question['stem'] for question in questions)
    def grade(cls, ai, **kwargs):
        return {'score': 7.49, 'feedback': '尚需补充推理', 'memorix_rating': 3}
    monkeypatch.setattr(QuizAITaskService, 'grade_question', classmethod(grade))
    data = client.post(path, {'action': 'submit', 'questions': questions, 'answers': _quiz_answers(questions)}, format='json').data
    assert data['accuracy'] >= .75 and not data['core_passed'] and not data['block_completed']
    assert data['weak_atom_ids'] == [questions[-1]['atom_id']]
