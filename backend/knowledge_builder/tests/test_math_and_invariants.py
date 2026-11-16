import numpy as np
import pytest

from knowledge_builder.exceptions import InvariantViolationError
from knowledge_builder.graph_math import (
    cluster_atoms, compute_diffusion_kernel, compute_semantic_kernel, fuse_kernels,
    normalize_embeddings, reduce_and_layer_block_graph,
)


@pytest.mark.parametrize('dimension', [384, 1024, 1536])
def test_dynamic_embeddings_semantic_psd(dimension):
    rng = np.random.default_rng(17)
    views = [rng.normal(size=(10, dimension)) for _ in range(3)]
    normalized = normalize_embeddings(views[0])
    np.testing.assert_allclose(np.linalg.norm(normalized, axis=1), 1)
    kernel = compute_semantic_kernel(views)
    np.testing.assert_allclose(kernel, kernel.T)
    np.testing.assert_allclose(np.diag(kernel), 1)
    assert np.linalg.eigvalsh(kernel).min() > -1e-10


@pytest.mark.parametrize('values', [np.zeros((2, 3)), [[1, np.nan]], [[1, np.inf]]])
def test_invalid_embeddings_raise(values):
    with pytest.raises(InvariantViolationError):
        normalize_embeddings(values)


def test_diffusion_isolated_rows_and_zero_signal_fusion():
    signal = np.array([[0., 2., 0.], [2., 0., 0.], [0., 0., 0.]])
    diffusion = compute_diffusion_kernel(signal)
    assert np.linalg.eigvalsh(diffusion).min() > 0
    assert diffusion[0, 1] > 0
    assert diffusion[0, 2] == 0
    semantic = compute_semantic_kernel([np.eye(3)] * 3)
    result = fuse_kernels({'semantic': semantic, 'hierarchy': np.zeros((3, 3))}, {'semantic': .6, 'hierarchy': .4})
    np.testing.assert_allclose(result, semantic)


def test_cluster_size_repair_real_scipy():
    rng = np.random.default_rng(91)
    samples = np.concatenate([rng.normal(size=(8, 6)) * .03 + center for center in np.eye(6)[:4]])
    kernel = normalize_embeddings(samples) @ normalize_embeddings(samples).T
    groups, stats = cluster_atoms(kernel, (3, 7))
    assert sorted(index for group in groups for index in group) == list(range(len(samples)))
    assert all(3 <= len(group) <= 7 for group in groups)
    assert np.isfinite(stats['silhouette'])


def edge(source, target, score=5, kind='unidirectional', hard=0):
    return {'from_block': source, 'to_block': target, 'edge_kind': kind,
            'directness_score': score, 'hard_constraint_count': hard,
            'hard_net': hard, 'similarity': .5}


def blocks(*codes, entries=('A',)):
    return [{'code': code, 'is_entry_block': code in entries} for code in codes]


def test_reduction_removes_equal_score_detour_and_longest_path():
    result = reduce_and_layer_block_graph(blocks('A', 'B', 'C'), [edge('A', 'B', 4), edge('B', 'C', 4), edge('A', 'C', 3)])
    assert [item['is_retained'] for item in result['edges']] == [True, True, False]
    assert result['layers'] == {'A': 1, 'B': 2, 'C': 3}


def test_bidirectional_contraction():
    result = reduce_and_layer_block_graph(blocks('A', 'B', 'C'), [edge('A', 'B', kind='bidirectional'), edge('B', 'C')])
    assert result['contraction_groups']['A'] == result['contraction_groups']['B']
    assert result['layers']['A'] == result['layers']['B'] < result['layers']['C']


def test_cycle_removes_optional_edge():
    result = reduce_and_layer_block_graph(blocks('A', 'B', 'C'), [edge('A', 'B', hard=2), edge('B', 'C', hard=2), edge('C', 'A', score=3)])
    assert not result['edges'][-1]['is_retained']
    for item in result['edges']:
        if item['is_retained']:
            assert result['layers'][item['from_block']] < result['layers'][item['to_block']]


def test_low_score_incoming_and_connectivity_restoration():
    result = reduce_and_layer_block_graph(blocks('A', 'B', 'C', 'D'), [edge('A', 'B'), edge('C', 'D'), edge('B', 'C', score=1)])
    assert all(item['is_retained'] for item in result['edges'])
    assert result['layers']['D'] == 4


def test_impossible_incoming_raises():
    with pytest.raises(InvariantViolationError, match='incoming'):
        reduce_and_layer_block_graph(blocks('A', 'B', entries=()), [edge('A', 'B')])


def test_omitted_hard_evidence_restores_strict_layer_order():
    result = reduce_and_layer_block_graph(blocks('A', 'B', 'C'), [edge('A', 'B'), edge('A', 'C'), edge('C', 'B', score=1, hard=2)])
    assert result['edges'][-1]['is_retained']
    assert result['layers']['C'] < result['layers']['B']


def test_impossible_mandatory_degree_cap_raises():
    nodes = blocks('A', 'B', 'C', 'D', 'E')
    with pytest.raises(InvariantViolationError, match='degree cap'):
        reduce_and_layer_block_graph(nodes, [edge('A', target) for target in ('B', 'C', 'D', 'E')], edge_cap=2)
