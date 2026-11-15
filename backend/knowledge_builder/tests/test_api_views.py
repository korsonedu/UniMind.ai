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
