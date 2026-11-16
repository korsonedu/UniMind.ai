"""Six-stage integration using real kernels, graph algorithms and ORM writes."""
import copy
import json
from collections import Counter

import httpx
import pytest

from ai_engine import config
from ai_engine.ai_service import AIService
from ai_engine.service import AICallError
from knowledge_builder.exceptions import (AIResponseError, EmbeddingError,
                                          InvariantViolationError, PipelineRepairExhaustedError)
from knowledge_builder.models import BlockStepAtom, KnowledgeTreeBuild
from knowledge_builder.pipeline import create_build, run_build
from knowledge_builder.serializers import FullKnowledgeTreeSerializer

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
        return httpx.Response(200, json={'data': rows}, request=httpx.Request('POST', url))


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
def test_embedding_http_failure_is_rethrown_and_recorded(monkeypatch, semantic_fixture, status):
    def fail(url, **kwargs):
        return httpx.Response(status, request=httpx.Request('POST', url))
    monkeypatch.setattr('knowledge_builder.embedding_client.httpx.post', fail)
    build = create_build('微积分极限与连续性')
    with pytest.raises(EmbeddingError, match='HTTP/JSON'):
        run_build(build.pk)
    assert_failed(build, 'EmbeddingError')


def test_nonfinite_embedding_is_rethrown_and_recorded(monkeypatch, semantic_fixture):
    original = semantic_fixture.http
    def fail(url, **kwargs):
        response = original(url, **kwargs)
        # Bypass JSON serialization only to model a decoded nonfinite provider payload.
        payload = response.json()
        payload['data'][0]['embedding'][0] = float('nan')
        response.json = lambda: copy.deepcopy(payload)
        return response
    monkeypatch.setattr('knowledge_builder.embedding_client.httpx.post', fail)
    build = create_build('微积分极限与连续性')
    with pytest.raises(EmbeddingError, match='finite'):
        run_build(build.pk)
    assert_failed(build, 'EmbeddingError')


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
