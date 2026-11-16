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
