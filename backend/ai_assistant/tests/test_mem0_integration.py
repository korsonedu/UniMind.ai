"""
Integration tests for mem0 + pgvector.
Requires: PostgreSQL with pgvector extension, test database.
Run with: pytest ai_assistant/tests/test_mem0_integration.py -v -m integration
"""
import os
import pytest


# Skip if no real DB available or USE_MEM0 is not enabled
pytestmark = pytest.mark.skipif(
    os.getenv('USE_MEM0', 'false').lower() != 'true',
    reason="Integration tests require USE_MEM0=true"
)


@pytest.mark.integration
class TestMem0Integration:
    """These tests hit a real pgvector instance."""

    def test_add_and_search(self):
        """End-to-end: add a memory and search for it."""
        from ai_assistant.services.tenant_memory import TenantMemoryManager

        manager = TenantMemoryManager(institution_id=999)

        # Add a memory
        manager.add(user_id=1, message="学生三角函数公式记不住，但图形理解能力很强")

        # Search
        results = manager.search(user_id=1, query="这个学生数学怎么样")
        assert len(results) > 0
        assert any("三角函数" in r.get("memory", "") for r in results)

        # Cleanup
        manager.delete_all(user_id=1)

    def test_user_isolation(self):
        """Users within same institution cannot see each other's memories."""
        from ai_assistant.services.tenant_memory import TenantMemoryManager

        manager = TenantMemoryManager(institution_id=999)

        # User 1 adds memory
        manager.add(user_id=1, message="我喜欢用图解法学习")
        # User 2 adds memory
        manager.add(user_id=2, message="我喜欢背公式")

        # User 1 should only see their own
        results_1 = manager.get_all(user_id=1)
        results_2 = manager.get_all(user_id=2)

        assert all("图解" not in r.get("memory", "") for r in results_2)
        assert all("背公式" not in r.get("memory", "") for r in results_1)

        # Cleanup
        manager.delete_all(user_id=1)
        manager.delete_all(user_id=2)

    def test_institution_isolation(self):
        """Different institutions have separate memory collections."""
        from ai_assistant.services.tenant_memory import TenantMemoryManager

        manager_a = TenantMemoryManager(institution_id=888)
        manager_b = TenantMemoryManager(institution_id=889)

        # Institution 888 user adds memory
        manager_a.add(user_id=1, message="机构A的学生记忆")
        # Institution 889 user adds memory
        manager_b.add(user_id=1, message="机构B的学生记忆")

        # Institution 888 should not see 889's memories
        results_a = manager_a.get_all(user_id=1)
        results_b = manager_b.get_all(user_id=1)

        assert all("机构B" not in r.get("memory", "") for r in results_a)
        assert all("机构A" not in r.get("memory", "") for r in results_b)

        # Cleanup
        manager_a.delete_all(user_id=1)
        manager_b.delete_all(user_id=1)


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(not os.environ.get('ULR_SEMANTIC_SMOKE'), reason='isolated ULR pgvector smoke')
def test_ulr_semantic_withdrawal_on_pgvector(user, settings, monkeypatch, tmp_path, request):
    from datetime import timedelta
    from unittest.mock import patch
    from uuid import uuid4

    from django.db import connection
    from django.utils import timezone
    from rest_framework.test import APIClient

    from ai_assistant.services import tenant_memory
    from ai_assistant.services.ulr_profile import profile_for_user
    from users.login_sessions import LoginSession
    from users.models import Institution
    from users.models_workspace import Workspace, WorkspaceMembership
    from users.workspaces.identity import select_learner
    from .test_ulr_queue_smoke import PROFILE

    assert connection.vendor == 'postgresql' and connection.settings_dict['NAME'].startswith('test_')
    settings.UNIMIND_LEARNING_RUNTIME = 'ulr'
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    settings.CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}
    with connection.cursor() as cursor:
        cursor.execute('CREATE EXTENSION IF NOT EXISTS vector')
    original_config = tenant_memory._get_mem0_config

    def local_config(institution_id):
        config = original_config(institution_id)
        config['history_db_path'] = str(tmp_path / 'semantic-audit.sqlite3')
        return config

    monkeypatch.setattr(tenant_memory, '_get_mem0_config', local_config)
    institution = Institution.objects.create(name='合成语义记忆机构', slug='ulr-semantic-test')
    workspace = Workspace.objects.create(institution=institution, max_students=2,
                                         service_ends_on=timezone.localdate() + timedelta(days=2))
    WorkspaceMembership.objects.create(user=user, workspace=workspace)
    learner = select_learner(user, workspace.pk)
    client = APIClient()
    client.cookies['auth_token'] = LoginSession.issue(user).key
    client.credentials(HTTP_X_UNIMIND_WORKSPACE=str(workspace.pk))
    manager = tenant_memory.TenantMemoryManager(institution.pk)
    request.addfinalizer(manager.close)
    vector = [1.0] + [0.0] * (tenant_memory.EMBEDDING_DIMENSIONS - 1)

    def seed(owner, count):
        ids = [str(uuid4()) for _ in range(count)]
        manager.memory.vector_store.insert([vector] * count, ids=ids, payloads=[
            {'user_id': str(owner), 'data': f'SYNTHETIC_{owner}_{index}_END', 'created_at': timezone.now().isoformat()}
            for index in range(count)])
        return ids

    ids = seed(learner.pk, 105)
    foreign, = seed('foreign-learner', 1)
    seed('legacy-clear', 105)
    manager.memory.delete_all(user_id='legacy-clear')
    assert len(manager.memory.get_all(filters={'user_id': 'legacy-clear'})['results']) == 5
    listing = '/api/ai/memories/semantics/'
    response = client.get(listing, {'limit': 200})
    assert response.status_code == 200 and {row['id'] for row in response.data['memories']} == set(ids)
    initial = manager.get_all(learner.pk)
    marker = initial[0]['memory']
    early = initial[0]['id']
    late = next(key for key in ids if key not in {row['id'] for row in initial})
    assert client.delete(f'{listing}{foreign}/').status_code == 404
    with patch.object(tenant_memory.Memory, 'delete', side_effect=RuntimeError('Synthetic storage failure')):
        assert client.delete(f'{listing}{late}/').status_code == 500
    assert manager.memory.get(late)
    assert client.delete(f'{listing}{late}/').status_code == 200
    assert manager.memory.get(late) is None

    with patch('ai_assistant.services.ulr_profile.run_collector', return_value=PROFILE) as model:
        assert profile_for_user(learner.pk)[0] is not None
        assert marker in model.call_args.args[0]
        assert client.delete(f'{listing}{early}/').status_code == 200
        assert profile_for_user(learner.pk)[0] is not None
        assert marker not in model.call_args.args[0] and model.call_count == 2
        assert client.delete(f'{listing}clear/').status_code == 200
        assert profile_for_user(learner.pk) == (None, []) and model.call_count == 2
    with patch.object(manager.memory.embedding_model, 'embed', return_value=vector):
        assert manager.search(learner.pk, 'synthetic query') == []
    assert client.get(listing).data['memories'] == []
    assert manager.memory.get(foreign) is not None
