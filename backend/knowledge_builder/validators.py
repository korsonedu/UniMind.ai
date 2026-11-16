"""Precise validation errors used by bounded semantic repair rounds."""
from collections import Counter, defaultdict
from math import isfinite
import unicodedata

BRANCH_TERMS = ("分支", "分流", "路由", "鉴别", "诊断", "决策")
GOAL_TYPES = {"概念辨析", "公式推导", "实操计算", "机制分析", "对比区分", "综合应用", "操作方法", "排错诊断"}
COGNITIVE_LEVELS = {"记忆", "理解", "应用", "分析", "评价"}


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _branch_role(value):
    return any(term in value for term in BRANCH_TERMS)


def validate_atoms(atoms, modules, profile):
    errors = []
    if len(atoms) < 6:
        errors.append("atoms: total atom count must be at least 6")
    module_map = {module["code"]: module for module in modules}
    codes = Counter(atom["code"] for atom in atoms)
    names = Counter(unicodedata.normalize("NFKC", atom["name"]).strip().casefold() for atom in atoms)
    covered = set()
    for atom in atoms:
        code = atom["code"]
        if codes[code] > 1:
            errors.append(f"{code}: duplicate atom code")
        name = unicodedata.normalize("NFKC", atom["name"]).strip().casefold()
        if not name or names[name] > 1:
            errors.append(f"{code}: empty or globally duplicate atom name")
        for field in ("goal_statement", "parent_path"):
            if not _nonempty(atom.get(field)):
                errors.append(f"{code}: {field} must be nonempty")
        minutes = atom.get("granularity_minutes")
        if type(minutes) is not int or not 3 <= minutes <= 6:
            errors.append(f"{code}: granularity_minutes must be an integer in [3, 6]")
        for field in ("key_elements", "prerequisites_hint", "common_misconceptions"):
            values = atom.get(field)
            if not isinstance(values, list) or any(not _nonempty(value) for value in values):
                errors.append(f"{code}: {field} must contain nonempty strings")
        if not atom.get("key_elements"):
            errors.append(f"{code}: key_elements must be nonempty")
        if atom.get("goal_type") not in GOAL_TYPES:
            errors.append(f"{code}: unsupported goal_type")
        if atom.get("cognitive_level") not in COGNITIVE_LEVELS:
            errors.append(f"{code}: unsupported cognitive_level")
        module_code = atom.get("module_code")
        if module_code not in module_map:
            errors.append(f"{code}: unknown module_code {module_code!r}")
            continue
        module = module_map[module_code]
        branch_text = f"{module['title']} {atom['name']} {atom.get('goal_type', '')}"
        if profile.require_branch_condition and _branch_role(branch_text) and not _nonempty(atom.get("branch_condition")):
            errors.append(f"{code}: diagnostic/decision atom requires branch_condition")
        ancestors = set()
        while module_code:
            if module_code in ancestors or module_code not in module_map:
                errors.append(f"{code}: invalid module ancestry at {module_code}")
                break
            ancestors.add(module_code)
            covered.add(module_code)
            module_code = module_map[module_code].get("parent_code")
    for code in module_map.keys() - covered:
        errors.append(f"{code}: module has no atoms in its subtree")
    return errors


def find_strong_cycle(edges):
    """Return the directed edges of one strong cycle, or an empty list."""
    adjacency = defaultdict(list)
    for edge in edges:
        if edge["edge_strength"] == "strong":
            adjacency[edge["from_atom"]].append(edge)
    state = {}
    for root in list(adjacency):
        if state.get(root):
            continue
        state[root] = 1
        stack = [(root, iter(adjacency[root]))]
        path = []
        while stack:
            node, children = stack[-1]
            edge = next(children, None)
            if edge is None:
                state[node] = 2
                stack.pop()
                if path:
                    path.pop()
                continue
            target = edge["to_atom"]
            if state.get(target) == 1:
                start = next(index for index, (code, _) in enumerate(stack) if code == target)
                return path[start:] + [edge]
            if state.get(target) != 2:
                state[target] = 1
                stack.append((target, iter(adjacency[target])))
                path.append(edge)
    return []


def validate_edges(edges, atoms, profile):
    errors = []
    atom_map = {atom["code"]: atom for atom in atoms}
    seen = set()
    contrast_degree = Counter()
    contrast_count = 0
    for edge in edges:
        source, target = edge["from_atom"], edge["to_atom"]
        pair = (source, target)
        strength = edge["edge_strength"]
        if source not in atom_map or target not in atom_map:
            errors.append(f"R3 {pair}: unknown atom endpoint")
            continue
        if source == target:
            errors.append(f"R3 {pair}: self-loop")
        if pair in seen:
            errors.append(f"R3 {pair}: duplicate or mutually exclusive ordered relation")
        seen.add(pair)
        if strength not in {"strong", "weak", "contrast", "bidirectional"}:
            errors.append(f"R3 {pair}: invalid edge_strength")
        for field, low, high in (("confidence", 0, 1), ("similarity", -1, 1)):
            value = edge.get(field)
            if type(value) not in (int, float) or not isfinite(value) or not low <= value <= high:
                errors.append(f"R3 {pair}: {field} outside finite [{low}, {high}]")
        if not _nonempty(edge.get("rationale")):
            errors.append(f"R3 {pair}: rationale must be nonempty")
        if strength == "contrast":
            contrast_count += 1
            contrast_degree.update((source, target))
        label = edge.get("relation_label", "").casefold()
        if strength == "strong" and any(term in label for term in ("包含", "从属", "组成", "上下级", "contains", "part_of", "is_a")):
            errors.append(f"R5 {pair}: containment relation cannot be a strong prerequisite")
    for code, degree in contrast_degree.items():
        if degree > 5:
            errors.append(f"R3 {code}: contrast degree {degree} exceeds 5")
    if edges and contrast_count / len(edges) > profile.max_contrast_ratio:
        errors.append(f"R3 contrast ratio exceeds profile maximum {profile.max_contrast_ratio}")
    cycle = find_strong_cycle(edges)
    if cycle:
        errors.append("R1 strong prerequisite cycle: " + " -> ".join([cycle[0]["from_atom"]] + [edge["to_atom"] for edge in cycle]))
    return errors


def _reachable(adjacency, source, target):
    pending = [source]
    visited = set()
    while pending:
        node = pending.pop()
        if node == target:
            return True
        if node not in visited:
            visited.add(node)
            pending.extend(adjacency.get(node, ()))
    return False


def validate_steps(plan, atoms, edges, profile):
    errors = []
    steps = plan["steps"]
    count = len(atoms)
    minimum, maximum = (2, 5) if count >= 4 else (1, count)
    if not minimum <= len(steps) <= maximum:
        errors.append(
            f"steps: got {len(steps)}, expected {minimum}..{maximum} steps for {count} atoms "
            f"(each step holds 1..4 atoms; merge or adjust into {minimum}..{maximum} steps)"
        )
    atom_map = {atom["code"]: atom for atom in atoms}
    memberships = []
    positions = {}
    adjacencies = []
    core_codes = []
    lines_count = 0
    for index, step in enumerate(steps):
        core, extension = step["core_atoms"], step["extension_atoms"]
        codes = core + extension
        if not core or len(codes) > 4:
            errors.append(f"step {index + 1}: requires core atoms and at most 4 total atoms")
        for field in ("step_title", "step_role"):
            if not _nonempty(step.get(field)):
                errors.append(f"step {index + 1}: {field} must be nonempty")
        memberships.extend(codes)
        core_codes.extend(core)
        positions.update({code: index for code in codes})
        adjacency = defaultdict(list)
        seen_lines = set()
        for line in step["intra_lines"]:
            source, target = line["from_atom_code"], line["to_atom_code"]
            kind = line["kind"]
            key = (source, target, kind)
            if source not in codes or target not in codes or source == target:
                errors.append(f"step {index + 1}: intra-line endpoints must be distinct atoms in the same step")
            if key in seen_lines:
                errors.append(f"step {index + 1}: duplicate intra-line {key}")
            seen_lines.add(key)
            if kind not in {"progression", "contrast"} or not _nonempty(line.get("reason")):
                errors.append(f"step {index + 1}: intra-line requires valid kind and reason")
            if kind == "progression":
                adjacency[source].append(target)
        adjacencies.append(adjacency)
        lines_count += len(step["intra_lines"])
        if profile.require_branch_condition and _branch_role(step["step_role"]) and not _nonempty(step.get("branch_condition")):
            errors.append(f"step {index + 1}: branching step requires branch_condition")
    frequency = Counter(memberships)
    missing = sorted(set(atom_map) - set(memberships))
    duplicated = sorted(code for code, value in frequency.items() if value > 1)
    unknown = sorted(set(memberships) - set(atom_map))
    if missing or duplicated or unknown:
        details = []
        if missing:
            details.append(f"missing={missing}")
        if duplicated:
            details.append(f"duplicated={duplicated}")
        if unknown:
            details.append(f"unknown={unknown}")
        errors.append("coverage: core_atoms + extension_atoms must be an exclusive complete partition of block atoms (" + ", ".join(details) + ")")
    if count >= 2 and lines_count > count // 2:
        errors.append(
            f"intra_lines: total {lines_count} exceeds {count // 2} "
            "(drop contrast/redundant lines, or move strong-edge targets to later steps so cross-step edges need 0 lines)"
        )
    for edge in edges:
        source, target = edge["from_atom"], edge["to_atom"]
        if edge["edge_strength"] != "strong" or source not in positions or target not in positions:
            continue
        if positions[source] > positions[target]:
            errors.append(f"backward strong edge: {source} -> {target}")
        if positions[source] == positions[target] and not _reachable(adjacencies[positions[source]], source, target):
            errors.append(
                f"same-step strong edge lacks directed intra-line path: {source} -> {target} "
                f"(move {target} to a later step than {source}, or add progression intra_line {source}->{target} in step {positions[source] + 1})"
            )
    if profile.require_branch_condition and len(steps) >= 2 and not any(_nonempty(step.get("branch_condition")) for step in steps):
        errors.append("diagnostic plan: at least one branching step requires branch_condition")
    summary = plan.get("narrative_summary", "")
    for code in core_codes:
        if code in atom_map and atom_map[code]["name"] not in summary:
            errors.append(f"narrative_summary: missing core atom name {atom_map[code]['name']}")
    return errors
