"""Six-stage integration using real kernels, graph algorithms and ORM writes."""
import copy
import json
from collections import Counter
from pathlib import Path
from runpy import run_path

import httpx
import pytest
from django.test import override_settings

from ai_engine import config
from ai_engine.ai_service import AIService
from ai_engine.service import AICallError, AIEngine
from knowledge_builder.exceptions import (AIResponseError, EmbeddingError,
                                          InvariantViolationError, PipelineRepairExhaustedError)
from knowledge_builder.models import BlockStepAtom, KnowledgeTreeBuild
from knowledge_builder.pipeline import create_build, run_build
from knowledge_builder.serializers import FullKnowledgeTreeSerializer
from knowledge_builder.tasks import build_knowledge_tree

pytestmark = pytest.mark.django_db


class SemanticFixture:
    """Provide schema-conforming semantic answers to the actual prompt payload."""

    def __init__(self, diagnostic=False, cyclic=False, invalid_atoms=False):
        self.diagnostic = diagnostic
        self.cyclic = cyclic
        self.invalid_atoms = invalid_atoms
        self.calls = Counter()
        self.profile = 'taskflow_diagnostic_tree' if diagnostic else 'formula_derivation_chain'
        self.titles = ('症状识别', '鉴别诊断') if diagnostic else ('极限', '连续性')

    def modules(self):
        result = []
        for index, title in enumerate(self.titles, 1):
            result.extend([
                dict(code=f'M{index}', parent_code='', title=title, path=title, depth=1, order=index),
                dict(code=f'M{index}.1', parent_code=f'M{index}', title=title + '方法',
                     path=f'{title} > {title}方法', depth=2, order=1),
            ])
        return result

    def atoms(self, module):
        group = int(module['code'][1])
        return [dict(code=f'A{(group - 1) * 3 + offset}', module_code=module['code'],
                     name=f'{self.titles[group - 1]}能力{offset}', goal_statement=f'解释{self.titles[group - 1]}的步骤{offset}',
                     parent_path=module['path'], goal_type='机制分析' if self.diagnostic else '公式推导',
                     granularity_minutes=8 if self.invalid_atoms else 4, cognitive_level='理解',
                     key_elements=[f'{self.titles[group - 1]}要素{offset}'], prerequisites_hint=[],
                     common_misconceptions=[], branch_condition='若出现危险征象则升级检查' if self.diagnostic else '', order=offset)
                for offset in range(1, 4)]

    @staticmethod
    def edge(source, target, kind):
        return dict(from_atom=source, to_atom=target, edge_strength=kind,
                    relation_label='计算输入' if kind == 'strong' else '',
                    rationale='前一步输出供后续调用' if kind == 'strong' else '无需依赖', confidence=.9)

    def ai(self, **kwargs):
        assert kwargs['raise_on_error'] is True
        name = kwargs['tool_name']
        self.calls[name] += 1
        sys_text = kwargs.get('system_prompt') or ''
        sys_payload = json.loads(sys_text[sys_text.index('\n{') + 1:]) if '\n{' in sys_text else {}
        content = kwargs['user_prompt']
        payload = {**sys_payload, **json.loads(content[content.index('\n{') + 1:])}
        if name == 'archetype_classify':
            return {'archetype': self.profile}
        if name == 'outline_decompose':
            return {'modules': self.modules()}
        if name == 'atom_generate':
            return {'atoms': self.atoms(payload['module'])}
        if name == 'atom_repair':
            return {'atoms': payload['current']}
        if name == 'edge_classify':
            edges = []
            for left, right in payload['pairs']:
                source, target = left['code'], right['code']
                i, j = int(source[1:]), int(target[1:])
                kind = 'strong' if j == i + 1 else 'none'
                if self.cyclic and (i, j) == (1, 3):
                    source, target, kind = target, source, 'strong'
                edges.append(self.edge(source, target, kind))
            return {'edges': edges}
        if name == 'edge_cycle_resolve':
            return {'edges': [{key: value for key, value in edge.items() if key != 'similarity'}
                              for edge in payload['current']]}
        if name == 'block_naming':
            return {'blocks': [dict(code=block['code'], short_title=f'学习{block["atoms"][0]["name"]}',
                                    is_entry_block=index == 0, rationale='从基本目标开始')
                               for index, block in enumerate(payload['blocks'])]}
        if name == 'interblock_review':
            return {'edges': [dict(from_block=edge['from_block'], to_block=edge['to_block'],
                                   edge_kind='unidirectional', directness_score=5, rationale='按能力先后衔接')
                              for edge in payload['evidence']],
                    'entry_blocks': [payload['blocks'][0]['code']]}
        if name == 'intrablock_steps':
            atoms = sorted(payload['block']['atoms'], key=lambda atom: int(atom['code'][1:]))
            roles = payload['profile']['step_roles']
            return dict(steps=[dict(step_title=f'学习{atom["name"]}', step_role=roles[index],
                                   branch_condition='若检查阳性则进入下一鉴别步骤' if self.diagnostic else '',
                                   core_atoms=[atom['code']], extension_atoms=[], intra_lines=[])
                              for index, atom in enumerate(atoms)],
                        narrative_summary='，然后'.join(atom['name'] for atom in atoms))
        if name == 'interface_bind':
            source, target = payload['candidate_pairs'][0]
            return {'interfaces': [dict(from_atom=source, to_atom=target,
                                        interface_role='diagnostic_escalation' if self.diagnostic else 'prerequisite_handoff',
                                        bridge_explanation='前块能力为后块的具体动作提供输入')]}
        raise AssertionError(f'Unexpected AI call {name}')

    def http(self, url, **kwargs):
        assert url == config.EMBEDDING_BASE_URL.rstrip('/') + '/embeddings'
        assert kwargs['json']['model'] == config.EMBEDDING_MODEL
        dimension = kwargs['json']['dimensions']
        rows = []
        for index, text in enumerate(kwargs['json']['input']):
            second = self.titles[1] in text
            vector = [0.0] * dimension
            vector[int(second)] = 1.0
            vector[2] = .01
            rows.append(dict(index=index, embedding=vector))
        return httpx.Response(200, json={'data': rows, 'model': config.EMBEDDING_MODEL,
            'usage': {'prompt_tokens': len(rows) * 10}}, request=httpx.Request('POST', url))


@pytest.fixture
def semantic_fixture(monkeypatch):
    fixture = SemanticFixture()
    monkeypatch.setattr(config, 'EMBEDDING_BASE_URL', 'http://127.0.0.1:8012/v1')
    monkeypatch.setattr(config, 'EMBEDDING_MODEL', 'Qwen/Qwen3-Embedding-0.6B')
    monkeypatch.setattr(config, 'EMBEDDING_DIMENSIONS', 24)
    monkeypatch.setattr(AIService, 'structured_output', fixture.ai)
    monkeypatch.setattr('knowledge_builder.embedding_client.httpx.post', fixture.http)
    return fixture


@pytest.mark.parametrize('subject,diagnostic', [
    ('微积分极限与连续性', False),
    ('急性胸痛急诊鉴别诊断', True),
])
def test_subject_only_six_stage_tree(monkeypatch, subject, diagnostic):
    fixture = SemanticFixture(diagnostic=diagnostic)
    monkeypatch.setattr(config, 'EMBEDDING_BASE_URL', 'http://127.0.0.1:8012/v1')
    monkeypatch.setattr(config, 'EMBEDDING_MODEL', 'Qwen/Qwen3-Embedding-0.6B')
    monkeypatch.setattr(config, 'EMBEDDING_DIMENSIONS', 24)
    monkeypatch.setattr(AIService, 'structured_output', fixture.ai)
    monkeypatch.setattr('knowledge_builder.embedding_client.httpx.post', fixture.http)
    build = create_build(subject)
    stages = []
    result = run_build(build.pk, progress=stages.append)
    build.refresh_from_db()
    assert result.pk == build.pk
    assert build.status == 'COMPLETED'
    assert build.archetype == fixture.profile
    assert build.error_message == ''
    assert build.completed_at is not None
    assert len(stages) == 6
    assert build.modules.count() == 4
    assert build.atoms.count() == 6
    assert build.atom_edges.count() == 5
    assert build.blocks.count() == 2
    assert BlockStepAtom.objects.filter(step__block__build=build).count() == 6
    retained = build.block_edges.filter(is_retained=True)
    assert retained.count() == 1
    assert build.cross_block_interfaces.count() >= retained.count()
    assert fixture.calls['archetype_classify'] == 1
    assert fixture.calls['edge_cycle_resolve'] == 0
    for edge in retained.select_related('from_block', 'to_block'):
        assert edge.from_block.layer < edge.to_block.layer
        assert edge.interfaces.exists()
    for edge in build.atom_edges.select_related('from_atom__block_assignment__step', 'to_atom__block_assignment__step'):
        source = edge.from_atom.block_assignment.step
        target = edge.to_atom.block_assignment.step
        if source.block_id == target.block_id and edge.edge_strength == 'strong':
            assert source.step_index <= target.step_index
    if diagnostic:
        assert all(atom.branch_condition for atom in build.atoms.all())
        assert all(step.branch_condition for block in build.blocks.all() for step in block.steps.all())
    payload = FullKnowledgeTreeSerializer(build).data
    encoded = json.dumps(payload, allow_nan=False)
    assert 'question_ids' not in encoded
    assert 'cooccurrence' not in encoded
    assert set(('modules', 'atoms', 'atom_edges', 'blocks', 'block_edges', 'interfaces')) <= set(payload)
    counts = (build.atoms.count(), build.blocks.count(), build.cross_block_interfaces.count())
    with pytest.raises(InvariantViolationError, match='PENDING'):
        run_build(build.pk)
    build.refresh_from_db()
    assert build.status == 'COMPLETED'
    assert counts == (build.atoms.count(), build.blocks.count(), build.cross_block_interfaces.count())


def assert_failed(build, message):
    build.refresh_from_db()
    assert build.status == 'FAILED'
    assert message in build.error_message
    assert build.modules.count() == 0
    assert build.atoms.count() == 0
    assert build.blocks.count() == 0


@pytest.mark.parametrize('failure_at', ['interblock_review', 'intrablock_steps', 'publication'])
def test_ulr_build_resumes_validated_stages_and_publishes_once(monkeypatch, settings, user, api_client, failure_at, caplog, tmp_path):
    from ai_engine.observability import log_ai_operation, runtime_observation
    from knowledge_builder import pipeline

    settings.DEBUG = settings.UNIMIND_ULR_PROTOTYPE = True
    settings.ROOT_URLCONF = 'knowledge_builder.urls'
    settings.UNIMIND_DSH_GENERATION_ENABLED = settings.UNIMIND_DSH_TEACHING_ENABLED = False
    settings.UNIMIND_KB_ONLINE_AUTO_MOUNT = False
    fixture = SemanticFixture()
    monkeypatch.setattr(config, 'EMBEDDING_DIMENSIONS', 24)
    requests = []
    observations = []
    reviews = []
    embeddings = []
    persist = pipeline._persist

    def embed(url, **kwargs):
        embeddings.append(url)
        return fixture.http(url, **kwargs)

    def interrupted_publish(*args):
        raise RuntimeError('本次构建中断')

    def provider(messages, *, tools, raise_on_error, **kwargs):
        name = tools[0]['function']['name']
        requests.append(name)
        observations.append(runtime_observation.get().copy())
        if name == 'interblock_review':
            reviews.append((messages[0]['content'], messages[1]['content']))
        if name == failure_at and requests.count(name) == 1:
            raise RuntimeError('本次构建中断')
        if failure_at == 'publication':
            log_ai_operation(kwargs['operation'], True, 1, metadata={
                'model': 'capture-fixture-model', 'reported_model': 'capture-fixture-model',
                'max_output_tokens': kwargs['max_tokens'], 'prompt_tokens': 50,
                'completion_tokens': 10, 'cached_tokens': 30,
            })
        if name == 'outline_decompose' and requests.count(name) == 1:
            output = {'modules': '格式错误'}
        else:
            if name == 'outline_decompose':
                assert '字段 modules 未通过 type 校验' in messages[1]['content']
            output = fixture.ai(tool_name=name, raise_on_error=raise_on_error,
                                system_prompt=messages[0]['content'], user_prompt=messages[1]['content'])
        return {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [{
            'function': {'name': name, 'arguments': json.dumps(output)},
        }]}}]}

    monkeypatch.setattr(AIEngine, 'call_provider', provider)
    monkeypatch.setattr('knowledge_builder.embedding_client.httpx.post', embed)
    submissions = []
    monkeypatch.setattr('knowledge_builder.views.build_knowledge_tree.delay', submissions.append)
    if failure_at == 'publication':
        monkeypatch.setattr(pipeline, '_persist', interrupted_publish)
    api_client.force_authenticate(user=user)
    caplog.set_level('INFO', logger='ai_engine.observability')
    created = api_client.post('/', {'subject': '合成微积分知识图谱'}, format='json')
    assert created.status_code == 202
    build = KnowledgeTreeBuild.objects.get(pk=created.data['id'])
    assert submissions == [str(build.pk)] and build.requires_ulr
    with pytest.raises(RuntimeError, match='本次构建中断'):
        build_knowledge_tree(str(build.pk))
    build.refresh_from_db()
    assert build.status == 'FAILED'
    assert build.current_stage == ('interblock_graph' if failure_at == 'interblock_review' else 'intrablock_steps_and_interfaces')
    assert not build.modules.exists() and not build.blocks.exists()
    status = api_client.get(f'/{build.pk}/status/').data
    assert status['can_resume'] and 'checkpoint' not in status
    assert ('intrablock_steps_and_interfaces' in build.checkpoint) == (failure_at == 'publication')

    count, embedding_count = len(requests), len(embeddings)
    monkeypatch.setattr(pipeline, '_persist', persist)
    url = f'/{build.pk}/resume/'
    if failure_at == 'publication':
        checkpoint = build.checkpoint
        assert api_client.post(url).status_code == 202
        with override_settings(UNIMIND_LEARNING_RUNTIME='legacy', UNIMIND_ULR_PROTOTYPE=False):
            with pytest.raises(InvariantViolationError, match='requires an ULR worker'):
                build_knowledge_tree(str(build.pk))
        build.refresh_from_db()
        assert build.status == 'FAILED' and build.checkpoint == checkpoint
        assert (len(requests), len(embeddings)) == (count, embedding_count)

    previous_submissions = len(submissions)
    resumed = api_client.post(url)
    assert resumed.status_code == 202 and resumed.data['id'] == str(build.pk)
    assert api_client.post(url).status_code == 409
    assert submissions == [str(build.pk)] * (previous_submissions + 1)
    assert build_knowledge_tree(str(build.pk)) == str(build.pk)
    build.refresh_from_db()
    assert build.status == 'COMPLETED' and build.current_stage == 'completed'
    assert build.checkpoint == {} and len(embeddings) == embedding_count
    expected = {'intrablock_steps', 'interface_bind'} if failure_at != 'publication' else set()
    if failure_at == 'interblock_review':
        expected.add('interblock_review')
        assert len(reviews) == 2 and reviews[0] == reviews[1]
    assert set(requests[count:]) == expected
    request_id = f'build:{build.pk}'
    assert {row['request_id'] for row in observations} == {request_id}
    assert len({row['attempt_id'] for row in observations[:count]}) == 1
    if expected:
        assert len({row['attempt_id'] for row in observations[count:]}) == 1
        assert observations[0]['attempt_id'] != observations[count]['attempt_id']
    embedding_logs = [row.args for row in caplog.records if row.name == 'ai_engine.observability'
                      and row.args[0] == 'knowledge_tree.embedding']
    assert all(row[1] and row[3] == 'none' for row in embedding_logs)
    embedded = [row[4] for row in embedding_logs]
    assert len(embedded) == embedding_count == 3
    assert {row['request_id'] for row in embedded} == {request_id}
    assert {row['attempt_id'] for row in embedded} == {str(observations[0]['attempt_id'])}
    assert all(row['kind'] == 'embedding' and row['stage'] == 'atom_edges' for row in embedded)
    assert '合成微积分知识图谱' not in repr(embedded)
    assert not runtime_observation.get()
    assert (build.modules.count(), build.atoms.count(), build.atom_edges.count(), build.blocks.count()) == (4, 6, 5, 2)
    assert build.cross_block_interfaces.count() == 1
    assert requests.count('outline_decompose') == 2
    count = len(requests)
    with pytest.raises(InvariantViolationError, match='PENDING'):
        build_knowledge_tree(str(build.pk))
    assert len(requests) == count
    assert build.atoms.count() == 6
    local = [row.args for row in caplog.records if row.name == 'ai_engine.observability'
             and row.args[4].get('kind') == 'build_local']
    if failure_at != 'publication':
        assert not local
        return
    assert [(row[0], row[1], row[4]['runtime'], row[4]['attempts']) for row in local] == [
        ('knowledge_tree.worker_guard', False, 'legacy', '0'),
        ('knowledge_tree.checkpoint_publication', True, 'ulr', '0'),
    ]
    tool = run_path(str(Path(settings.BASE_DIR).parent / 'scripts/ulr_review_pairs.py'))
    logfile = tmp_path / 'model-operations.log'
    logfile.write_text('\n'.join(f'{row.name} {row.getMessage()}' for row in caplog.records
                                 if row.name == 'ai_engine.observability'))
    operations = tool['read_operations']([logfile])
    original_attempt = str(observations[0]['attempt_id'])
    model_operations = operations[request_id, original_attempt]
    local_attempts = [row[4]['attempt_id'] for row in local]
    record = {'request_id': request_id, 'attempt_ids': [original_attempt, *local_attempts], 'runtime': 'ulr',
              'model': {call['operation']: call['reported_model'] for call in model_operations}}
    metrics = dict.fromkeys(tool['METRICS']) | {'model_requests': count, 'embedding_requests': embedding_count}
    rates = {'models': {'capture-fixture-model': {'uncached_input': 1_000_000, 'cached_input': 100_000, 'output': 2_000_000},
                        config.EMBEDDING_MODEL: {'embedding_input': 1_000_000}}}
    values = metrics.copy()
    trace = tool['reconcile'](record, values, operations, rates)
    assert trace['local_build_attempt_ids'] == local_attempts and not trace['unobserved_attempt_ids']
    assert trace['model_verified'] and tool['request_configurations'](trace)
    assert values['input_tokens'] == count * 50 and values['embedding_input_tokens'] == 180
    assert values['cost_microusd'] == count * 43 + 180

    publication = (request_id, local_attempts[-1])
    missing = {key: rows for key, rows in operations.items() if key != publication}
    values = metrics.copy()
    trace = tool['reconcile'](record, values, missing, rates)
    assert trace['unobserved_attempt_ids'] == [local_attempts[-1]] and values['cost_microusd'] is None
    operations[publication].append({**model_operations[0], 'attempt_id': local_attempts[-1]})
    with pytest.raises(ValueError, match='本地构建批次'):
        tool['reconcile'](record, metrics.copy(), operations, rates)


def test_ai_failure_is_rethrown_and_recorded(monkeypatch):
    failure = RuntimeError('semantic service unavailable')
    def fail(**kwargs):
        assert kwargs['raise_on_error'] is True
        raise failure
    monkeypatch.setattr(AIService, 'structured_output', fail)
    build = create_build('微积分极限与连续性')
    with pytest.raises(RuntimeError) as raised:
        run_build(build.pk)
    assert raised.value is failure
    assert_failed(build, 'semantic service unavailable')


@pytest.mark.parametrize('status', [400, 503])
def test_embedding_http_failure_is_rethrown_and_recorded(monkeypatch, semantic_fixture, status, caplog):
    def fail(url, **kwargs):
        return httpx.Response(status, request=httpx.Request('POST', url))
    monkeypatch.setattr('knowledge_builder.embedding_client.httpx.post', fail)
    build = create_build('微积分极限与连续性')
    caplog.set_level('INFO', logger='ai_engine.observability')
    with pytest.raises(EmbeddingError, match='HTTP/JSON'):
        run_build(build.pk)
    assert_failed(build, 'EmbeddingError')
    observation, = [row.args for row in caplog.records if row.name == 'ai_engine.observability'
                    and row.args[0] == 'knowledge_tree.embedding']
    assert observation[1] is False and observation[3] == 'upstream'
    assert 'prompt_tokens' not in observation[4]


def test_nonfinite_embedding_is_rethrown_and_recorded(monkeypatch, semantic_fixture, caplog):
    original = semantic_fixture.http
    def fail(url, **kwargs):
        response = original(url, **kwargs)
        # Bypass JSON serialization only to model a decoded nonfinite provider payload.
        payload = response.json()
        payload.update(model=config.EMBEDDING_MODEL, usage={'prompt_tokens': 41})
        payload['data'][0]['embedding'][0] = float('nan')
        response.json = lambda: copy.deepcopy(payload)
        return response
    monkeypatch.setattr('knowledge_builder.embedding_client.httpx.post', fail)
    build = create_build('微积分极限与连续性')
    caplog.set_level('INFO', logger='ai_engine.observability')
    with pytest.raises(EmbeddingError, match='finite'):
        run_build(build.pk)
    assert_failed(build, 'EmbeddingError')
    observation, = [row.args for row in caplog.records if row.name == 'ai_engine.observability'
                    and row.args[0] == 'knowledge_tree.embedding']
    assert observation[1] is False and observation[3] == 'invalid_response'
    assert observation[4]['prompt_tokens'] == '41' and observation[4]['reported_model'] == config.EMBEDDING_MODEL


def test_strong_cycle_repairs_stop_after_two_rounds(monkeypatch, semantic_fixture):
    semantic_fixture.cyclic = True
    build = create_build('微积分极限与连续性')
    with pytest.raises(PipelineRepairExhaustedError, match='R1'):
        run_build(build.pk)
    assert semantic_fixture.calls['edge_cycle_resolve'] == 2
    assert_failed(build, 'R1')


def test_atom_repairs_stop_after_two_rounds(semantic_fixture):
    semantic_fixture.invalid_atoms = True
    build = create_build('微积分极限与连续性')
    with pytest.raises(PipelineRepairExhaustedError, match='granularity_minutes'):
        run_build(build.pk)
    assert semantic_fixture.calls['atom_repair'] == 2
    assert_failed(build, 'granularity_minutes')


def test_service_failure_becomes_typed_domain_error(monkeypatch):
    failure = AICallError('provider rejected the request', upstream_status=503)
    def fail(**kwargs):
        assert kwargs['raise_on_error'] is True
        raise failure
    monkeypatch.setattr(AIService, 'structured_output', fail)
    build = create_build('微积分极限与连续性')
    with pytest.raises(AIResponseError, match='provider rejected') as raised:
        run_build(build.pk)
    assert raised.value.__cause__ is failure
    assert_failed(build, 'AIResponseError')


def test_schema_failure_is_recorded_without_semantic_fallback(monkeypatch):
    monkeypatch.setattr(AIService, 'structured_output', lambda **kwargs: {'archetype': 'unrecognized'})
    build = create_build('微积分极限与连续性')
    with pytest.raises(AIResponseError, match='invalid structured response'):
        run_build(build.pk)
    assert_failed(build, 'archetype_classify')
