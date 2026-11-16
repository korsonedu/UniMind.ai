"""Numerical kernels, bounded clustering and deterministic learning-graph reduction."""
from collections import Counter, defaultdict, deque
import math

import numpy as np
from scipy.cluster.hierarchy import cut_tree, fcluster, linkage
from scipy.spatial.distance import squareform
from scipy.stats import rankdata

from .exceptions import InvariantViolationError


def normalize_embeddings(values):
    matrix = np.asarray(values, dtype=np.float64)
    if matrix.ndim != 2 or min(matrix.shape) == 0 or not np.isfinite(matrix).all():
        raise InvariantViolationError('Embeddings must be a finite nonempty matrix')
    norms = np.linalg.norm(matrix, axis=1)
    if not np.isfinite(norms).all() or np.any(norms <= 0):
        raise InvariantViolationError('Embedding vectors must have finite positive norms')
    return matrix / norms[:, None]


def _square(matrix, name):
    matrix = np.asarray(matrix, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or not matrix.size:
        raise InvariantViolationError(f'{name} must be a nonempty square matrix')
    if not np.isfinite(matrix).all() or not np.allclose(matrix, matrix.T):
        raise InvariantViolationError(f'{name} must be finite and symmetric')
    return matrix


def normalize_kernel(kernel):
    kernel = _square(kernel, 'Kernel')
    diagonal = np.diag(kernel)
    if np.any(diagonal <= 0):
        raise InvariantViolationError('Kernel diagonal must be positive')
    result = kernel / np.sqrt(diagonal[:, None] * diagonal[None, :])
    result = (result + result.T) / 2
    np.fill_diagonal(result, 1.0)
    return result


def compute_semantic_kernel(views, view_weights=(0.5, 0.3, 0.2)):
    matrices = [views[name] for name in ('parent', 'point', 'namegoal')] if isinstance(views, dict) else list(views)
    if len(matrices) != len(view_weights) or not matrices:
        raise InvariantViolationError('Semantic views and weights must match')
    weights = np.asarray(view_weights, dtype=float)
    if not np.isfinite(weights).all() or np.any(weights < 0) or not np.isclose(weights.sum(), 1):
        raise InvariantViolationError('Semantic weights must be nonnegative and sum to one')
    matrices = [normalize_embeddings(matrix) for matrix in matrices]
    if len({matrix.shape for matrix in matrices}) != 1:
        raise InvariantViolationError('All embedding views must have equal dynamic dimensions')
    count = len(matrices[0])
    if count < 2:
        raise InvariantViolationError('Semantic ranking requires at least two atoms')
    semantic = np.zeros((count, count))
    for weight, matrix in zip(weights, matrices):
        cosine = matrix @ matrix.T
        ranks = np.eye(count)
        for index in range(count):
            mask = np.arange(count) != index
            ranks[index, mask] = rankdata(cosine[index, mask], method='average') / (count - 1)
        semantic += weight * (ranks + ranks.T) / 2
    values, vectors = np.linalg.eigh(semantic)
    positive = values > 1e-10
    if not positive.any():
        raise InvariantViolationError('Semantic kernel has no positive spectrum')
    return normalize_kernel((vectors[:, positive] * values[positive]) @ vectors[:, positive].T)


def compute_diffusion_kernel(weights, alpha=0.5):
    weights = _square(weights, 'Diffusion signal')
    if np.any(weights < 0) or not 0 <= alpha < 1:
        raise InvariantViolationError('Diffusion requires nonnegative weights and alpha in [0, 1)')
    degree = weights.sum(axis=1)
    scale = np.zeros(len(weights))
    nonzero = degree > 0
    scale[nonzero] = 1 / np.sqrt(degree[nonzero])
    graph = weights * scale[:, None] * scale[None, :]
    identity = np.eye(len(weights))
    return normalize_kernel(np.linalg.solve(identity - alpha * graph, identity))


def fuse_kernels(kernels, weights):
    """Omitted/zero sparse signals receive no mass. Semantic signal is mandatory."""
    if 'semantic' not in kernels or not np.any(kernels['semantic']):
        raise InvariantViolationError('Semantic kernel is required')
    active = {name: _square(value, name) for name, value in kernels.items() if np.any(value)}
    if len({value.shape for value in active.values()}) != 1:
        raise InvariantViolationError('Kernel shapes differ')
    if any(name not in weights or not math.isfinite(weights[name]) or weights[name] < 0 for name in active):
        raise InvariantViolationError('Invalid fusion weights')
    total = sum(weights[name] for name in active)
    if total <= 0:
        raise InvariantViolationError('Active kernel weight must be positive')
    return normalize_kernel(sum(weights[name] / total * value for name, value in active.items()))


def kernel_distance(kernel):
    kernel = normalize_kernel(kernel)
    distance = np.sqrt(np.maximum(0.0, 2.0 - 2.0 * kernel))
    distance = (distance + distance.T) / 2
    np.fill_diagonal(distance, 0.0)
    return distance


def silhouette_score(distance, labels):
    groups = [np.flatnonzero(labels == label) for label in np.unique(labels)]
    if len(groups) < 2 or len(groups) == len(labels):
        return 0.0
    scores = np.zeros(len(labels))
    for group in groups:
        if len(group) == 1:
            continue
        for index in group:
            within = distance[index, group].sum() / (len(group) - 1)
            nearest = min(distance[index, other].mean() for other in groups if other[0] != group[0])
            denominator = max(within, nearest)
            scores[index] = (nearest - within) / denominator if denominator > 0 else 0.0
    return float(scores.mean())


def cluster_atoms(kernel, block_size_range):
    kernel = normalize_kernel(kernel)
    distance = kernel_distance(kernel)
    count = len(kernel)
    minimum, maximum = block_size_range
    if minimum < 1 or maximum < minimum or count < 2:
        raise InvariantViolationError('Invalid clustering size bounds')
    tree = linkage(squareform(distance, checks=False), method='average')
    lower = min(count, max(2, math.ceil(count / maximum)))
    upper = min(count, max(lower, count // max(2, minimum)))
    candidates = []
    for requested in range(lower, upper + 1):
        labels = fcluster(tree, t=requested, criterion='maxclust')
        sizes = Counter(labels)
        penalty = sum(max(0, minimum - size) + max(0, size - maximum) for size in sizes.values()) / count
        score = silhouette_score(distance, labels)
        candidates.append((score - penalty, score, requested, labels))
    _, score, requested, labels = max(candidates, key=lambda item: (item[0], -item[2]))
    pending = [list(np.flatnonzero(labels == label)) for label in np.unique(labels)]
    groups = []
    while pending:
        members = pending.pop(0)
        if len(members) <= maximum:
            groups.append(members)
            continue
        subtree = linkage(squareform(distance[np.ix_(members, members)], checks=False), method='average')
        split = cut_tree(subtree, n_clusters=2).ravel()
        pending.extend([[members[index] for index in np.flatnonzero(split == label)] for label in np.unique(split)])
    changed = True
    while changed:
        changed = False
        for index in sorted(range(len(groups)), key=lambda item: (len(groups[item]), groups[item][0])):
            members = groups[index]
            if len(members) >= minimum:
                continue
            targets = [other for other in range(len(groups)) if other != index and len(groups[other]) + len(members) <= maximum]
            if not targets:
                continue
            target = max(targets, key=lambda other: (kernel[np.ix_(members, groups[other])].mean(), -other))
            groups[target].extend(members)
            groups.pop(index)
            changed = True
            break
    groups = sorted([sorted(group) for group in groups], key=lambda group: group[0])
    undersized = [group for group in groups if len(group) < minimum]
    if any(len(group) == 1 for group in undersized):
        raise InvariantViolationError('Clustering cannot place singleton within block bounds')
    return groups, {'selected_k': requested, 'block_count': len(groups), 'silhouette': score,
                    'undersized_blocks': [len(group) for group in undersized]}


def _contracted(nodes, edges, selected):
    parents = {node: node for node in nodes}
    def root(node):
        while parents[node] != node:
            parents[node] = parents[parents[node]]
            node = parents[node]
        return node
    for index in selected:
        edge = edges[index]
        if edge['edge_kind'] == 'bidirectional':
            left, right = root(edge['from_block']), root(edge['to_block'])
            parents[max(left, right)] = min(left, right)
    return {node: root(node) for node in nodes}


def _path(start, end, edges, selected, exclude=None, threshold=0, undirected=False):
    adjacent = defaultdict(list)
    for index in selected:
        edge = edges[index]
        if index == exclude or edge['directness_score'] < threshold:
            continue
        if not undirected and edge['edge_kind'] != 'unidirectional':
            continue
        adjacent[edge['from_block']].append(edge['to_block'])
        if undirected:
            adjacent[edge['to_block']].append(edge['from_block'])
    queue = deque([start])
    seen = {start}
    while queue:
        node = queue.popleft()
        if node == end:
            return True
        for target in adjacent[node]:
            if target not in seen:
                seen.add(target)
                queue.append(target)
    return False


def _cycle(nodes, edges, selected):
    groups = _contracted(nodes, edges, selected)
    adjacent = defaultdict(list)
    for index in sorted(selected):
        edge = edges[index]
        if edge['edge_kind'] == 'unidirectional':
            adjacent[groups[edge['from_block']]].append((groups[edge['to_block']], index))
    visited, visiting, stack, edge_stack = set(), set(), [], []
    def visit(node):
        visiting.add(node)
        stack.append(node)
        for target, index in adjacent[node]:
            if target in visiting:
                return edge_stack[stack.index(target):] + [index]
            if target not in visited:
                edge_stack.append(index)
                found = visit(target)
                if found:
                    return found
                edge_stack.pop()
        stack.pop()
        visiting.remove(node)
        visited.add(node)
        return []
    for node in sorted(set(groups.values())):
        if node not in visited:
            found = visit(node)
            if found:
                return found
    return []


def layers_for(nodes, edges, selected):
    groups = _contracted(nodes, edges, selected)
    incoming, outgoing = defaultdict(set), defaultdict(set)
    for index in selected:
        edge = edges[index]
        if edge['edge_kind'] == 'unidirectional':
            source, target = groups[edge['from_block']], groups[edge['to_block']]
            incoming[target].add(source)
            outgoing[source].add(target)
    degree = {group: len(incoming[group]) for group in set(groups.values())}
    queue = deque(sorted(group for group in degree if degree[group] == 0))
    levels = {group: 1 for group in degree}
    seen = 0
    while queue:
        node = queue.popleft()
        seen += 1
        for target in sorted(outgoing[node]):
            levels[target] = max(levels[target], levels[node] + 1)
            degree[target] -= 1
            if degree[target] == 0:
                queue.append(target)
    if seen != len(degree):
        raise InvariantViolationError('Contracted block graph contains a cycle')
    return {node: levels[groups[node]] for node in nodes}, groups


def reduce_and_layer_block_graph(blocks, edges, edge_cap=4, allow_bidirectional_contraction=True):
    nodes = [block['code'] for block in blocks]
    entries = {block['code'] for block in blocks if block['is_entry_block']}
    if not nodes or len(nodes) != len(set(nodes)) or edge_cap < 1:
        raise InvariantViolationError('Invalid block graph nodes or edge cap')
    edges = [dict(edge) for edge in edges]
    pairs = set()
    for edge in edges:
        source, target = edge['from_block'], edge['to_block']
        pair = tuple(sorted((source, target)))
        if source not in nodes or target not in nodes or source == target or pair in pairs:
            raise InvariantViolationError('Invalid or duplicate block edge')
        pairs.add(pair)
        if edge['edge_kind'] not in ('unidirectional', 'bidirectional'):
            raise InvariantViolationError('Invalid block edge kind')
        if edge['edge_kind'] == 'bidirectional' and not allow_bidirectional_contraction:
            raise InvariantViolationError('Profile forbids bidirectional contraction')
        if not math.isfinite(edge['similarity']) or not -1 <= edge['similarity'] <= 1:
            raise InvariantViolationError('Invalid block similarity')
        if edge['hard_net'] < 0 or edge['hard_constraint_count'] < edge['hard_net']:
            raise InvariantViolationError('Invalid block hard evidence counts')
        if not math.isfinite(edge['directness_score']) or not 0 <= edge['directness_score'] <= 5:
            raise InvariantViolationError('Invalid directness score')
    selected = set(range(len(edges)))
    reasons = {}
    def rank(index):
        edge = edges[index]
        return (-edge['directness_score'], -edge['hard_constraint_count'], -edge['similarity'], edge['from_block'], edge['to_block'])
    def remove(index, reason):
        selected.remove(index)
        reasons[index] = reason
    def incoming(node, subset):
        groups = _contracted(nodes, edges, subset)
        entry_groups = {groups[entry] for entry in entries}
        return groups[node] in entry_groups or any(edges[index]['edge_kind'] == 'unidirectional' and groups[edges[index]['to_block']] == groups[node] for index in subset)
    def connected(subset):
        return all(_path(nodes[0], node, edges, subset, undirected=True) for node in nodes)
    def degrees():
        return Counter(node for index in selected for node in (edges[index]['from_block'], edges[index]['to_block']))
    for index in sorted(list(selected), key=rank):
        edge = edges[index]
        if edge['edge_kind'] == 'unidirectional' and 3 <= edge['directness_score'] <= 4 and _path(edge['from_block'], edge['to_block'], edges, selected, exclude=index, threshold=edge['directness_score']):
            remove(index, '同分以上替代路径')
    for index in list(selected):
        if edges[index]['directness_score'] < 3:
            remove(index, '直接性得分不足')
    top = {node: set(sorted([index for index in selected if node in (edges[index]['from_block'], edges[index]['to_block'])], key=rank)[:edge_cap]) for node in nodes}
    for index in list(selected):
        edge = edges[index]
        if index not in top[edge['from_block']] or index not in top[edge['to_block']]:
            remove(index, '未进入两端最高排名')
    for node in nodes:
        candidates = sorted([index for index, edge in enumerate(edges) if node in (edge['from_block'], edge['to_block'])], key=rank)
        if candidates:
            selected.add(candidates[0])
    cycle = _cycle(nodes, edges, selected)
    while cycle:
        index = max(cycle, key=lambda item: (edges[item]['hard_net'] < 2, -edges[item]['directness_score'], -edges[item]['hard_constraint_count'], item))
        remove(index, '缩点有向图去环')
        cycle = _cycle(nodes, edges, selected)
    for node in nodes:
        if node in entries or incoming(node, selected):
            continue
        candidates = sorted([index for index, edge in enumerate(edges) if edge['edge_kind'] == 'unidirectional' and edge['to_block'] == node and index not in selected], key=rank)
        choice = next((index for index in candidates if not _cycle(nodes, edges, selected | {index})), None)
        if choice is None:
            raise InvariantViolationError(f'Non-entry block {node} has no acyclic incoming candidate')
        selected.add(choice)
    while not connected(selected):
        candidates = sorted([index for index, edge in enumerate(edges) if index not in selected and not _path(edge['from_block'], edge['to_block'], edges, selected, undirected=True)], key=rank)
        choice = next((index for index in candidates if not _cycle(nodes, edges, selected | {index})), None)
        if choice is None:
            raise InvariantViolationError('Block graph cannot be connected without a cycle')
        selected.add(choice)
    for _ in range(len(edges)):
        levels, groups = layers_for(nodes, edges, selected)
        changed = False
        for index in sorted(set(range(len(edges))) - selected, key=rank):
            edge = edges[index]
            degree = degrees()
            if edge['edge_kind'] != 'unidirectional' or edge['hard_net'] < 2 or levels[edge['from_block']] < levels[edge['to_block']]:
                continue
            if max(degree[edge['from_block']], degree[edge['to_block']]) < edge_cap + 1 and not _cycle(nodes, edges, selected | {index}):
                selected.add(index)
                changed = True
        if not changed:
            break
    while max(degrees().values(), default=0) > edge_cap + 1:
        degree = degrees()
        candidates = sorted([index for index in selected if max(degree[edges[index]['from_block']], degree[edges[index]['to_block']]) > edge_cap + 1 and edges[index]['hard_net'] < 2], key=rank, reverse=True)
        choice = next((index for index in candidates if connected(selected - {index}) and all(node in entries or incoming(node, selected - {index}) for node in nodes)), None)
        if choice is None:
            raise InvariantViolationError('Mandatory block graph exceeds the degree cap')
        remove(choice, '恢复连线后修整度数')
    levels, groups = layers_for(nodes, edges, selected)
    if not connected(selected) or any(not incoming(node, selected) for node in nodes):
        raise InvariantViolationError('Final graph lacks connectivity or non-entry incoming edges')
    if any(edge['edge_kind'] == 'unidirectional' and levels[edge['from_block']] >= levels[edge['to_block']] for index, edge in enumerate(edges) if index in selected):
        raise InvariantViolationError('Final graph violates strict directed layers')
    shapes = {}
    for node in nodes:
        ins = [edges[index]['from_block'] for index in selected if edges[index]['edge_kind'] == 'unidirectional' and edges[index]['to_block'] == node]
        outs = [edges[index]['to_block'] for index in selected if edges[index]['edge_kind'] == 'unidirectional' and edges[index]['from_block'] == node]
        merge = any(not _path(left, right, edges, selected) and not _path(right, left, edges, selected) for offset, left in enumerate(ins) for right in ins[offset + 1:])
        shapes[node] = {'entry': node in entries, 'overview': len(outs) >= 3, 'merge': merge, 'start': not ins, 'end': not outs}
    for index, edge in enumerate(edges):
        edge['is_retained'] = index in selected
        edge['exclusion_reason'] = '' if index in selected else reasons[index]
    return {'edges': edges, 'layers': levels, 'contraction_groups': groups, 'node_shapes': shapes}
