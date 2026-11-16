"""Requirement-aware six-stage knowledge tree construction with atomic publication."""
import heapq
import json
import logging
from itertools import combinations

import numpy as np
from django.db import transaction
from django.utils import timezone
from ai_engine.service import AICallError

from .archetypes import get_profile
from .embedding_client import embed_views
from .exceptions import AIResponseError, InvariantViolationError, PipelineRepairExhaustedError
from .graph_math import (normalize_embeddings, compute_semantic_kernel,
                         compute_diffusion_kernel, fuse_kernels, cluster_atoms,
                         reduce_and_layer_block_graph)
from .models import (KnowledgeTreeBuild, TreeModule, TreeAtomPoint, TreeAtomEdge,
                     LearningBlock, BlockEdge, BlockStep, BlockStepAtom, CrossBlockInterface)
from .prompts import ask
from .validators import validate_atoms, validate_edges, validate_steps


def create_build(subject: str, archetype_override: str = 'auto', created_by=None, requirements: dict | None = None) -> KnowledgeTreeBuild:
    subject = subject.strip()
    if not subject or len(subject) > 200:
        raise InvariantViolationError('subject must contain 1..200 characters')
    if archetype_override != 'auto':
        get_profile(archetype_override)
    if requirements is not None and not isinstance(requirements, dict):
        raise InvariantViolationError('requirements must be an object')
    json.dumps(requirements, allow_nan=False)
    return KnowledgeTreeBuild.objects.create(subject=subject, archetype=archetype_override, created_by=created_by, requirements=requirements or {})


def base_context(build):
    context = {'subject': build.subject}
    if build.requirements:
        context['requirements'] = build.requirements
    return context


def repair(value, validator, template, context, key=None):
    for attempt in range(3):
        errors = validator(value)
        if not errors:
            return value
        if attempt == 2:
            raise PipelineRepairExhaustedError(f'{template}: ' + '; '.join(errors))
        result = ask(template, {**context, 'current': value, 'errors': errors}, 'knowledge_tree_repair')
        value = result[key] if key else result


def _normalize_outline(modules):
    if not modules:
        raise InvariantViolationError('outline must contain at least one module')
    by_code = {}
    for module in modules:
        code = (module.get('code') or '').strip()
        title = (module.get('title') or '').strip()
        if not code or not title:
            raise InvariantViolationError('every module must have non-empty code and title')
        if code in by_code:
            raise InvariantViolationError(f'duplicate module code: {code}')
        by_code[code] = {**module, 'code': code, 'title': title, 'parent_code': (module.get('parent_code') or '').strip()}

    memo = {}

    def resolve(code, trail):
        if code in memo:
            return memo[code]
        if code in trail:
            raise InvariantViolationError(f'module ancestry cycle detected at {code}')
        node = by_code[code]
        parent = node['parent_code']
        if not parent:
            depth, path = 1, node['title']
        else:
            if parent not in by_code:
                raise InvariantViolationError(f'{code}: unknown parent {parent}')
            p_depth, p_path = resolve(parent, trail | {code})
            depth, path = p_depth + 1, f"{p_path} > {node['title']}"
        if depth > 3:
            raise InvariantViolationError(f'{code}: outline depth {depth} exceeds maximum 3')
        memo[code] = (depth, path)
        return memo[code]

    normalized = []
    for index, code in enumerate(by_code):
        depth, path = resolve(code, set())
        item = dict(by_code[code])
        item['depth'] = depth
        item['path'] = path
        normalized.append((depth, index, item))

    if max(depth for depth, _, _ in normalized) < 2:
        raise InvariantViolationError('outline must have 2..3 levels')
    normalized.sort(key=lambda row: (row[0], row[1]))
    return [row[2] for row in normalized]


def _repair_atoms(atoms, modules, profile, context):
    if len(atoms) <= 25:
        return repair(atoms, lambda value: validate_atoms(value, modules, profile), 'atom_repair', {**context, 'modules': modules}, 'atoms')
    atom_codes = {a['code'] for a in atoms}
    for attempt in range(3):
        errors = validate_atoms(atoms, modules, profile)
        if not errors:
            return atoms
        if attempt == 2:
            raise PipelineRepairExhaustedError('atom_repair: ' + '; '.join(errors))
        offending = []
        for err in errors:
            prefix = err.split(':', 1)[0].strip()
            if prefix not in atom_codes:
                offending = []
                break
            if prefix not in offending:
                offending.append(prefix)
        if not offending or len(offending) >= len(atoms):
            result = ask('atom_repair', {**context, 'modules': modules, 'current': atoms, 'errors': errors}, 'knowledge_tree_repair')
            atoms = result['atoms']
            continue
        offending_set = set(offending)
        subset = [a for a in atoms if a['code'] in offending_set]
        untouched_names = [a['name'] for a in atoms if a['code'] not in offending_set]
        repaired_list = ask(
            'atom_repair',
            {**context, 'modules': modules, 'current': subset, 'existing_names': untouched_names, 'errors': errors},
            'knowledge_tree_repair',
        )['atoms']
        repaired_map = {a['code']: a for a in repaired_list}
        if set(repaired_map) != offending_set:
            raise PipelineRepairExhaustedError('atom_repair: subset repair returned mismatched atom codes')
        atoms = [repaired_map.get(a['code'], a) for a in atoms]


def _edge_atom_view(atom):
    return {
        'code': atom['code'],
        'name': atom['name'],
        'goal_statement': atom['goal_statement'],
        'parent_path': atom['parent_path'],
        'key_elements': atom['key_elements'],
        'prerequisites_hint': atom['prerequisites_hint'],
    }


def _edge_pair_ref(atom):
    return {'code': atom['code'], 'name': atom['name']}


def _candidates(atoms, vectors, top_k=6):
    cosine = np.clip(vectors @ vectors.T, -1.0, 1.0)
    pairs = set()
    for i, atom in enumerate(atoms):
        peers = np.argsort(-cosine[i], kind='stable')
        for j in [int(j) for j in peers if j != i][:top_k]:
            pairs.add(tuple(sorted((i, j))))
        cross = [int(j) for j in peers if atoms[j]['module_code'] != atom['module_code']]
        for j in cross[:2]:
            pairs.add(tuple(sorted((i, j))))
        if i + 1 < len(atoms):
            pairs.add((i, i + 1))
        hints = atom['prerequisites_hint']
        for j, target in enumerate(atoms):
            if i != j and any(hint in target['name'] or target['name'] in hint for hint in hints):
                pairs.add(tuple(sorted((i, j))))
    return sorted(pairs), cosine


def _collect_chunk(items, item_key, row_key, fetch_rows, error_message, max_rounds=3):
    expected = {item_key(item): item for item in items}
    pending = list(items)
    collected = {}
    for _ in range(max_rounds):
        for row in fetch_rows(pending):
            key = row_key(row)
            if key in expected and key not in collected:
                collected[key] = row
        if len(collected) == len(expected):
            return collected
        pending = [item for key, item in expected.items() if key not in collected]
    raise InvariantViolationError(error_message)


def _classify_edge_batch(atoms, batch, profile, atom_catalog=None, subject=None, requirements=None):
    catalog = atom_catalog if atom_catalog is not None else [_edge_atom_view(atom) for atom in atoms]
    collected = _collect_chunk(
        batch,
        item_key=lambda pair: frozenset((atoms[pair[0]]['code'], atoms[pair[1]]['code'])),
        row_key=lambda edge: frozenset((edge['from_atom'], edge['to_atom'])),
        fetch_rows=lambda pending: ask(
            'edge_classify',
            {
                **({'subject': subject} if subject else {}),
                **({'requirements': requirements} if requirements else {}),
                'profile': profile,
                'atom_catalog': catalog,
                'pairs': [[_edge_pair_ref(atoms[i]), _edge_pair_ref(atoms[j])] for i, j in pending],
            },
            'knowledge_tree_edges',
        )['edges'],
        error_message='edge classification must cover each candidate pair exactly once',
    )
    return [e for e in collected.values() if e['edge_strength'] != 'none']


def _repair_edges(edges, check_edges, atoms, profile, requirements=None):
    extra = {'requirements': requirements} if requirements else {}
    if len(edges) <= 50:
        return repair(edges, check_edges, 'edge_cycle_resolve', {**extra, 'atoms': atoms, 'profile': profile}, 'edges')
    for attempt in range(3):
        errors = check_edges(edges)
        if not errors:
            return edges
        if attempt == 2:
            raise PipelineRepairExhaustedError('edge_cycle_resolve: ' + '; '.join(errors))
        focus_codes = set()
        for err in errors:
            for atom in atoms:
                if atom['code'] in err:
                    focus_codes.add(atom['code'])
        if focus_codes:
            subset = [e for e in edges if e['from_atom'] in focus_codes or e['to_atom'] in focus_codes]
        else:
            contrast_edges = sorted([e for e in edges if e['edge_strength'] == 'contrast'], key=lambda e: e['confidence'])
            subset = contrast_edges[:min(25, len(contrast_edges))]
        subset_ids = {id(e) for e in subset}
        subset_pairs = {frozenset((e['from_atom'], e['to_atom'])) for e in subset}
        if not subset or len(subset) >= len(edges):
            edges = ask('edge_cycle_resolve', {**extra, 'atoms': [_edge_atom_view(a) for a in atoms], 'profile': profile, 'current': edges, 'errors': errors}, 'knowledge_tree_repair')['edges']
            continue
        atom_lookup = {a['code']: a for a in atoms}
        involved_atoms = sorted({c for e in subset for c in (e['from_atom'], e['to_atom']) if c in atom_lookup})
        repaired = ask(
            'edge_cycle_resolve',
            {
                **extra,
                'atoms': [_edge_atom_view(atom_lookup[c]) for c in involved_atoms],
                'profile': profile,
                'current': subset,
                'errors': errors,
            },
            'knowledge_tree_repair',
        )['edges']
        kept = [e for e in edges if id(e) not in subset_ids]
        kept_pairs = {frozenset((e['from_atom'], e['to_atom'])) for e in kept}
        for edge in repaired:
            if edge.get('edge_strength') == 'none':
                continue
            pair = frozenset((edge['from_atom'], edge['to_atom']))
            if pair in subset_pairs and pair not in kept_pairs:
                kept.append(edge)
                kept_pairs.add(pair)
        edges = kept


def _atom_edges(atoms, views, profile, subject=None, requirements=None):
    atom_catalog = [_edge_atom_view(atom) for atom in atoms]
    pairs, cosine = _candidates(atoms, views['namegoal'])
    edges = []
    for start in range(0, len(pairs), 20):
        edges.extend(_classify_edge_batch(atoms, pairs[start:start + 20], profile, atom_catalog=atom_catalog, subject=subject, requirements=requirements))
    # R3 explicitly retains the five highest-confidence contrast edges per endpoint.
    counts = {a['code']: 0 for a in atoms}
    filtered = []
    for edge in sorted(edges, key=lambda e: -e['confidence']):
        if edge['edge_strength'] == 'contrast':
            a, b = edge['from_atom'], edge['to_atom']
            if counts[a] >= 5 or counts[b] >= 5:
                continue
            counts[a] += 1
            counts[b] += 1
        filtered.append(edge)
    lookup = {a['code']: i for i,a in enumerate(atoms)}
    def check_edges(value):
        for edge in value:
            if edge['from_atom'] in lookup and edge['to_atom'] in lookup:
                edge['similarity'] = float(cosine[lookup[edge['from_atom']], lookup[edge['to_atom']]])
        return validate_edges(value, atoms, get_profile(profile['archetype']))
    edges = _repair_edges(filtered, check_edges, atoms, profile, requirements=requirements)
    lookup = {a['code']: i for i,a in enumerate(atoms)}
    for edge in edges:
        edge['similarity'] = float(cosine[lookup[edge['from_atom']], lookup[edge['to_atom']]])
    return edges, cosine


def _cluster(atoms, edges, views, profile):
    n = len(atoms)
    lookup = {a['code']: i for i,a in enumerate(atoms)}
    signals = {name: np.zeros((n,n)) for name in ('hierarchy','strong_edge','weak_contrast')}
    for i,j in combinations(range(n), 2):
        a,b = atoms[i],atoms[j]
        affinity = 1.0 if a['module_code'] == b['module_code'] else float(a['parent_path'].split(' > ')[0] == b['parent_path'].split(' > ')[0]) * .5
        signals['hierarchy'][i,j] = signals['hierarchy'][j,i] = affinity
    for edge in edges:
        i,j = lookup[edge['from_atom']],lookup[edge['to_atom']]
        key = 'strong_edge' if edge['edge_strength'] == 'strong' else 'weak_contrast'
        signals[key][i,j] = signals[key][j,i] = edge['confidence']
    kernels = {'semantic': compute_semantic_kernel(views)}
    kernels.update({name: compute_diffusion_kernel(matrix) for name,matrix in signals.items() if np.any(matrix)})
    total = fuse_kernels(kernels, profile.kernel_weights)
    return cluster_atoms(total, profile.block_size_range)


def _block_naming_view(block):
    return {
        'code': block['code'],
        'atoms': [
            {
                'code': atom['code'],
                'name': atom['name'],
                'goal_statement': atom['goal_statement'],
                'parent_path': atom['parent_path'],
            }
            for atom in block['atoms']
        ],
    }


def _name_blocks(blocks, context):
    compact = [_block_naming_view(block) for block in blocks]
    outline = [{'code': block['code'], 'atom_names': [atom['name'] for atom in block['atoms']]} for block in blocks]
    naming = {}
    for start in range(0, len(compact), 12):
        chunk = compact[start:start + 12]
        payload_base = {**context}
        if len(compact) > 12:
            payload_base['block_outline'] = outline
        naming.update(_collect_chunk(
            chunk,
            item_key=lambda b: b['code'],
            row_key=lambda b: b['code'],
            fetch_rows=lambda pending: ask('block_naming', {**payload_base, 'blocks': pending}, 'knowledge_tree_block')['blocks'],
            error_message='block naming must cover all blocks once',
        ))
    for block in blocks:
        block.update(naming[block['code']])


def _build_reviewed_edges(reviewed, by_pair):
    results = []
    for pair, edge in reviewed.items():
        proof = by_pair[pair]
        item = dict(edge)
        if proof['hard_net'] >= 2:
            a, b = proof['from_block'], proof['to_block']
            if proof['b_to_a'] > proof['a_to_b']:
                a, b = b, a
            item.update(from_block=a, to_block=b, edge_kind='unidirectional')
        if item['edge_kind'] == 'none':
            continue
        item.update({key: proof[key] for key in ('hard_net', 'hard_constraint_count', 'similarity')})
        results.append(item)
    return results


def _orphan_repair_pairs(blocks, entries, results, evidence, error_text):
    incoming_targets = {e['to_block'] for e in results if e['edge_kind'] == 'unidirectional'}
    problem = {b['code'] for b in blocks if b['code'] not in entries and b['code'] not in incoming_targets}
    for block in blocks:
        if block['code'] in error_text:
            problem.add(block['code'])
    if not problem:
        adj = {b['code']: set() for b in blocks}
        for edge in results:
            adj[edge['from_block']].add(edge['to_block'])
            adj[edge['to_block']].add(edge['from_block'])
        seen, stack = set(), [blocks[0]['code']]
        while stack:
            cur = stack.pop()
            if cur not in seen:
                seen.add(cur)
                stack.extend(adj[cur] - seen)
        problem = set(adj) - seen
    if not problem:
        problem = {blocks[0]['code']}
    candidates = [e for e in evidence if e['from_block'] in problem or e['to_block'] in problem]
    return sorted(candidates, key=lambda e: (
        int(e['from_block'] in problem and e['to_block'] in problem),
        -e['hard_constraint_count'],
        -e['similarity'],
    ))[:20]


def _block_summaries(blocks):
    return [
        {
            'code': b['code'],
            'short_title': b.get('short_title', ''),
            'is_entry_block': b.get('is_entry_block', False),
            'atom_names': [a['name'] for a in b['atoms']],
        }
        for b in blocks
    ]


def _block_step_view(block):
    return {
        'code': block['code'],
        'short_title': block['short_title'],
        'is_entry_block': block['is_entry_block'],
        'atoms': [
            {
                **_edge_atom_view(atom),
                'goal_type': atom['goal_type'],
                'cognitive_level': atom['cognitive_level'],
                'branch_condition': atom['branch_condition'],
            }
            for atom in block['atoms']
        ],
    }


def _strong_topo_order(atoms, local_edges):
    order_index = {atom['code']: i for i, atom in enumerate(atoms)}
    indegree = {atom['code']: 0 for atom in atoms}
    outgoing = {atom['code']: set() for atom in atoms}
    for edge in local_edges:
        if edge['edge_strength'] != 'strong':
            continue
        source, target = edge['from_atom'], edge['to_atom']
        if source in order_index and target in order_index and source != target and target not in outgoing[source]:
            outgoing[source].add(target)
            indegree[target] += 1
    depth = {atom['code']: 0 for atom in atoms}
    heap = [(0, order_index[code], code) for code, deg in indegree.items() if deg == 0]
    heapq.heapify(heap)
    ordered = []
    while heap:
        cur_depth, _, code = heapq.heappop(heap)
        ordered.append(code)
        for target in outgoing[code]:
            depth[target] = max(depth[target], cur_depth + 1)
            indegree[target] -= 1
            if indegree[target] == 0:
                heapq.heappush(heap, (depth[target], order_index[target], target))
    if len(ordered) < len(atoms):
        seen = set(ordered)
        ordered.extend(atom['code'] for atom in atoms if atom['code'] not in seen)
    return ordered


def _suggest_step_buckets(atoms, local_edges):
    topo = _strong_topo_order(atoms, local_edges)
    n = len(topo)
    if n == 0:
        return []
    if n <= 3:
        return [[code] for code in topo]
    strong_set = {(e['from_atom'], e['to_atom']) for e in local_edges if e['edge_strength'] == 'strong'}

    def needed_lines(slice_codes):
        inside = set(slice_codes)
        adj = {c: set() for c in slice_codes}
        for u, v in strong_set:
            if u in inside and v in inside and u != v:
                adj[u].add(v)
        needed = 0
        for u in slice_codes:
            for v in adj[u]:
                seen, stack = set(), [w for w in adj[u] if w != v]
                while stack:
                    cur = stack.pop()
                    if cur == v:
                        break
                    if cur not in seen:
                        seen.add(cur)
                        stack.extend(adj[cur])
                else:
                    needed += 1
        return needed

    inf = (10**9, 10**9)
    dp = [[inf] * (n + 1) for _ in range(6)]
    back = [[-1] * (n + 1) for _ in range(6)]
    dp[0][0] = (0, 0)
    for steps in range(1, 6):
        for r in range(steps, n + 1):
            for l in range(max(steps - 1, r - 4), r):
                prev_cost = dp[steps - 1][l]
                if prev_cost == inf:
                    continue
                size = r - l
                cand = (prev_cost[0] + needed_lines(topo[l:r]), prev_cost[1] + size * size)
                if cand < dp[steps][r]:
                    dp[steps][r] = cand
                    back[steps][r] = l
    best_steps = min(range(2, 6), key=lambda s: dp[s][n])
    buckets = []
    idx = n
    for steps in range(best_steps, 0, -1):
        start = back[steps][idx]
        buckets.append(topo[start:idx])
        idx = start
    buckets.reverse()
    return buckets


def _review_blocks(blocks, groups, atoms, edges, views, profile, subject=None, requirements=None):
    membership = {atoms[i]['code']: blocks[b]['code'] for b, g in enumerate(groups) for i in g}
    means = normalize_embeddings(np.array([views['namegoal'][g].mean(axis=0) for g in groups]))
    block_count = len(blocks)
    sim_matrix = np.clip(means @ means.T, -1.0, 1.0)
    sim_neighbors = set()
    neighbor_k = max(6, profile.edge_cap + 2)
    for i in range(block_count):
        peers = [int(j) for j in np.argsort(-sim_matrix[i], kind='stable') if j != i][:neighbor_k]
        for j in peers:
            sim_neighbors.add(tuple(sorted((i, j))))
    evidence = []
    for i, j in combinations(range(block_count), 2):
        a, b = blocks[i]['code'], blocks[j]['code']
        cross = [e for e in edges if {membership[e['from_atom']], membership[e['to_atom']]} == {a, b}]
        if not cross and (i, j) not in sim_neighbors:
            continue
        forward = sum(e['edge_strength'] == 'strong' and membership[e['from_atom']] == a for e in cross)
        backward = sum(e['edge_strength'] == 'strong' and membership[e['from_atom']] == b for e in cross)
        compact_cross = [{'from_atom': e['from_atom'], 'to_atom': e['to_atom'], 'edge_strength': e['edge_strength']} for e in cross[:10]]
        evidence.append(dict(
            from_block=a, to_block=b, a_to_b=forward, b_to_a=backward,
            hard_net=abs(forward - backward), hard_constraint_count=forward + backward,
            weak_contrast_count=sum(e['edge_strength'] != 'strong' for e in cross),
            similarity=float(sim_matrix[i, j]), atom_edges=compact_cross,
        ))
    if not evidence:
        blocks[0]['is_entry_block'] = True
        return reduce_and_layer_block_graph(blocks, [], profile.edge_cap, profile.allow_bidirectional_contraction)
    block_summaries = _block_summaries(blocks)
    prefix = {
        **({'subject': subject} if subject else {}),
        **({'requirements': requirements} if requirements else {}),
        'profile': profile.as_dict(), 'blocks': block_summaries,
    }
    by_pair = {frozenset((e['from_block'], e['to_block'])): e for e in evidence}
    codes = {b['code'] for b in blocks}
    entries = set()
    reviewed = {}

    def apply_review(review):
        batch_entries = set(review['entry_blocks'])
        if not batch_entries <= codes:
            raise InvariantViolationError('unknown entry block')
        entries.update(batch_entries)
        return review['edges']

    for start in range(0, len(evidence), 20):
        chunk = evidence[start:start + 20]
        reviewed.update(_collect_chunk(
            chunk,
            item_key=lambda e: frozenset((e['from_block'], e['to_block'])),
            row_key=lambda e: frozenset((e['from_block'], e['to_block'])),
            fetch_rows=lambda pending: apply_review(ask(
                'interblock_review',
                {**prefix, 'evidence': pending},
                'knowledge_tree_block',
            )),
            error_message='block review must cover every candidate pair once',
        ))
    for attempt in range(2):
        for block in blocks:
            block['is_entry_block'] = block['code'] in entries
        results = _build_reviewed_edges(reviewed, by_pair)
        try:
            return reduce_and_layer_block_graph(blocks, results, profile.edge_cap, profile.allow_bidirectional_contraction)
        except InvariantViolationError as exc:
            if attempt == 1:
                raise
            repair_pairs = _orphan_repair_pairs(blocks, entries, results, evidence, str(exc))
            if not repair_pairs:
                raise
            repair_review = ask(
                'interblock_review',
                {
                    **prefix,
                    'evidence': repair_pairs,
                    'entry_candidates': sorted(entries),
                    'repair_reason': str(exc),
                },
                'knowledge_tree_block',
            )
            repair_expected = {frozenset((e['from_block'], e['to_block'])) for e in repair_pairs}
            for edge in apply_review(repair_review):
                pair = frozenset((edge['from_block'], edge['to_block']))
                if pair in repair_expected:
                    reviewed[pair] = edge


def _interfaces(edge, local_from, local_to, atom_edges, cosine, lookup, profile, subject=None, block_summaries=None, requirements=None):
    pairs = {(e['from_atom'],e['to_atom']) for e in atom_edges
             if e['from_atom'] in local_from and e['to_atom'] in local_to}
    ranked = sorted(((a,b) for a in local_from for b in local_to),
                    key=lambda pair:-cosine[lookup[pair[0]],lookup[pair[1]]])
    pairs.update(ranked[:3])
    atoms = [_edge_atom_view(atom) for atom in list(local_from.values()) + list(local_to.values())]
    payload = {
        **({'subject': subject} if subject else {}),
        **({'requirements': requirements} if requirements else {}),
        'profile': profile.as_dict(),
        **({'block_summaries': block_summaries} if block_summaries is not None else {}),
        'block_edge': edge,
        'candidate_pairs': [list(p) for p in sorted(pairs)],
        'atoms': atoms,
    }
    for _ in range(3):
        result = ask('interface_bind', payload, 'knowledge_tree_block')['interfaces']
        selected = [(r['from_atom'], r['to_atom']) for r in result]
        if 1 <= len(selected) <= 3 and len(set(selected)) == len(selected) and set(selected) <= pairs:
            return result
        payload = {**payload, 'error': 'select 1..3 unique [from_atom, to_atom] pairs strictly from candidate_pairs'}
    raise InvariantViolationError('interfaces must select 1..3 unique supplied cross-block atom pairs')


def _persist(build, modules, atoms, atom_edges, blocks, graph, plans, interfaces):
    """Publish every graph table in one transaction after all semantic validation."""
    with transaction.atomic():
        module_rows = {}
        for data in sorted(modules,key=lambda m:m['depth']):
            fields = {k:v for k,v in data.items() if k != 'parent_code'}
            module_rows[data['code']] = TreeModule.objects.create(build=build,parent=module_rows.get(data['parent_code']),**fields)
        atom_rows = {}
        for data in atoms:
            fields = {k:v for k,v in data.items() if k != 'module_code'}
            atom_rows[data['code']] = TreeAtomPoint.objects.create(build=build,module=module_rows[data['module_code']],**fields)
        for data in atom_edges:
            fields = {k:v for k,v in data.items() if k not in ('from_atom','to_atom')}
            TreeAtomEdge.objects.create(build=build,from_atom=atom_rows[data['from_atom']],to_atom=atom_rows[data['to_atom']],**fields)
        block_rows = {}
        for order,data in enumerate(blocks):
            code = data['code']
            block = LearningBlock.objects.create(build=build,code=code,short_title=data['short_title'],
                is_entry_block=data['is_entry_block'],narrative_summary=plans[code]['narrative_summary'],
                layer=graph['layers'][code],contraction_group=graph['contraction_groups'][code],
                node_shape=graph['node_shapes'][code],order=order)
            block_rows[code] = block
            for index,step in enumerate(plans[code]['steps'],1):
                row = BlockStep.objects.create(block=block,step_index=index,**{k:v for k,v in step.items() if k not in ('core_atoms','extension_atoms')})
                for key,kind in (('core_atoms','core'),('extension_atoms','extension')):
                    for position,atom in enumerate(step[key]):
                        BlockStepAtom.objects.create(step=row,atom=atom_rows[atom],membership_type=kind,position=position)
        for data in graph['edges']:
            fields = {k:v for k,v in data.items() if k not in ('from_block','to_block')}
            row = BlockEdge.objects.create(build=build,from_block=block_rows[data['from_block']],to_block=block_rows[data['to_block']],**fields)
            for interface in interfaces.get((data['from_block'],data['to_block']),[]):
                CrossBlockInterface.objects.create(build=build,block_edge=row,from_atom=atom_rows[interface['from_atom']],
                    to_atom=atom_rows[interface['to_atom']],interface_role=interface['interface_role'],bridge_explanation=interface['bridge_explanation'])
        build.status = 'COMPLETED'
        build.completed_at = timezone.now()
        build.current_stage = 'completed'
        build.save()


def run_build(build_id, progress=None):
    # Compare-and-set prevents concurrent or repeated tasks from publishing twice.
    claimed = KnowledgeTreeBuild.objects.filter(pk=build_id,status='PENDING').update(status='RUNNING',updated_at=timezone.now())
    if not claimed:
        raise InvariantViolationError('build must be PENDING to start')
    build = KnowledgeTreeBuild.objects.get(pk=build_id)
    def stage(name):
        build.current_stage = name
        build.save(update_fields=['current_stage','updated_at'])
        if progress:
            progress(name)
    try:
        stage('archetype_dispatch')
        archetype = build.archetype
        if archetype == 'auto':
            archetype = ask('archetype_classify', base_context(build), 'knowledge_tree_dispatch')['archetype']
        profile = get_profile(archetype)
        build.archetype = archetype
        build.dispatch_profile = profile.as_dict()
        build.save(update_fields=['archetype','dispatch_profile','updated_at'])
        context = {**base_context(build), 'profile':profile.as_dict()}
        stage('outline_and_atoms')
        modules = _normalize_outline(ask('outline_decompose', context, 'knowledge_tree_decompose')['modules'])
        outline = [{'code': m['code'], 'parent_code': m['parent_code'], 'title': m['title'], 'path': m['path']} for m in modules]
        parents = {m['parent_code'] for m in modules}
        atoms = []
        for module in modules:
            if module['code'] not in parents:
                atoms.extend(ask('atom_generate', {**context, 'outline': outline, 'module': module, 'existing_names': [a['name'] for a in atoms]}, 'knowledge_tree_decompose')['atoms'])
        atoms = _repair_atoms(atoms, modules, profile, context)
        stage('atom_edges')
        views = embed_views(atoms)
        edges,cosine = _atom_edges(atoms, views, profile.as_dict(), subject=build.subject, requirements=build.requirements)
        stage('kernel_clustering')
        groups,stats = _cluster(atoms,edges,views,profile)
        blocks = [{'code':f'B{i+1:02d}','atoms':[atoms[j] for j in group]} for i,group in enumerate(groups)]
        _name_blocks(blocks, context)
        stage('interblock_graph')
        graph = _review_blocks(blocks, groups, atoms, edges, views, profile, subject=build.subject, requirements=build.requirements)
        stage('intrablock_steps_and_interfaces')
        block_summaries = _block_summaries(blocks)
        plans = {}
        for block in blocks:
            local_codes = {atom['code'] for atom in block['atoms']}
            local_edges = [e for e in edges if e['from_atom'] in local_codes and e['to_atom'] in local_codes]
            payload = {
                **context,
                'block_summaries': block_summaries,
                'block': _block_step_view(block),
                'atom_codes': [atom['code'] for atom in block['atoms']],
                'suggested_step_buckets': _suggest_step_buckets(block['atoms'], local_edges),
                'topological_order': _strong_topo_order(block['atoms'], local_edges),
                'strong_edges': [[e['from_atom'], e['to_atom']] for e in local_edges if e['edge_strength'] == 'strong'],
                'max_intra_lines': len(block['atoms']) // 2,
                'atom_edges': local_edges,
            }
            plan = ask('intrablock_steps', payload, 'knowledge_tree_block')
            plans[block['code']] = repair(plan, lambda value: validate_steps(value, block['atoms'], local_edges, profile), 'intrablock_repair', payload)
        lookup = {a['code']:i for i,a in enumerate(atoms)}
        by_block = {b['code']:{a['code']:a for a in b['atoms']} for b in blocks}
        interfaces = {}
        for edge in graph['edges']:
            if edge['is_retained']:
                a,b = edge['from_block'],edge['to_block']
                interfaces[a,b] = _interfaces(edge, by_block[a], by_block[b], edges, cosine, lookup, profile, subject=build.subject, block_summaries=block_summaries, requirements=build.requirements)
        build.stats = {**stats,'atom_count':len(atoms),'atom_edge_count':len(edges),'block_count':len(blocks),
                       'module_count':len(modules),'layer_count':max(graph['layers'].values()),
                       'step_count':sum(len(p['steps']) for p in plans.values()),
                       'interface_count':sum(len(v) for v in interfaces.values())}
        _persist(build,modules,atoms,edges,blocks,graph,plans,interfaces)
        try:
            from .block_study import auto_mount_internal_resources
            with transaction.atomic():
                auto_mount_internal_resources(build)
        except Exception:
            logging.getLogger(__name__).exception('Initial resource matching failed for build %s', build.pk)
        return build
    except Exception as exc:
        # This is the single orchestration boundary. Preserve the original exception.
        if isinstance(exc, AICallError):
            failure = AIResponseError(str(exc))
        else:
            failure = exc
        build.status = 'FAILED'
        build.error_message = f'{build.current_stage}: {type(failure).__name__}: {failure}'
        build.save(update_fields=['status','error_message','updated_at'])
        if failure is not exc:
            raise failure from exc
        raise
