"""Exercise strict trust boundaries and repair-driving invariant reports."""
import httpx
import numpy as np
import pytest

from ai_engine import config
from knowledge_builder.archetypes import get_profile
from knowledge_builder.embedding_client import embed_views
from knowledge_builder.exceptions import ArchetypeDispatchError, EmbeddingError
from knowledge_builder.validators import find_strong_cycle, validate_atoms, validate_edges, validate_steps


def atoms_fixture(count=6):
    return [{"code": f"A{index}", "module_code": "M1", "name": f"学习点{index}",
             "goal_statement": "独立完成一个计算动作", "parent_path": "基础", "goal_type": "实操计算",
             "granularity_minutes": 4, "cognitive_level": "应用", "key_elements": ["核心要素"],
             "prerequisites_hint": [], "common_misconceptions": [], "branch_condition": ""}
            for index in range(count)]


def plan_fixture(atoms):
    return {"steps": [{"step_title": "定义", "step_role": "前置定义与公理", "branch_condition": "",
                       "core_atoms": [atom["code"] for atom in atoms[:3]], "extension_atoms": [], "intra_lines": []},
                      {"step_title": "应用", "step_role": "典型计算与建模", "branch_condition": "",
                       "core_atoms": [atom["code"] for atom in atoms[3:]], "extension_atoms": [], "intra_lines": []}],
            "narrative_summary": "、".join(atom["name"] for atom in atoms)}


def edge(source, target, strength="strong"):
    return {"from_atom": source, "to_atom": target, "edge_strength": strength,
            "relation_label": "计算输入", "rationale": "前者提供后者所需输入", "confidence": .9, "similarity": .5}


def test_profile_dispatch_and_atom_coverage():
    profile = get_profile("formula_derivation_chain")
    modules = [{"code": "M1", "title": "基础", "parent_code": None}]
    atoms = atoms_fixture()
    assert validate_atoms(atoms, modules, profile) == []
    atoms[-1]["name"] = atoms[0]["name"]
    atoms[0]["granularity_minutes"] = 7
    errors = validate_atoms(atoms, modules, profile)
    assert any("duplicate" in message for message in errors)
    assert any("granularity" in message for message in errors)
    with pytest.raises(ArchetypeDispatchError):
        get_profile("unrecognized")


def test_strong_cycle_r3_and_containment_are_reported():
    atoms = atoms_fixture()
    edges = [edge("A0", "A1"), edge("A1", "A2"), edge("A2", "A0")]
    assert len(find_strong_cycle(edges)) == 3
    errors = validate_edges(edges, atoms, get_profile("formula_derivation_chain"))
    assert any("R1" in message for message in errors)
    edges = [edge("A0", "A1"), edge("A0", "A1", "weak"), edge("A2", "A2")]
    edges[0]["relation_label"] = "组成"
    errors = validate_edges(edges, atoms, get_profile("formula_derivation_chain"))
    assert any("R5" in message for message in errors)
    assert any("duplicate" in message for message in errors)
    assert any("self-loop" in message for message in errors)


def test_step_positive_and_same_step_transitive_coverage():
    atoms = atoms_fixture()
    plan = plan_fixture(atoms)
    plan["steps"][0]["intra_lines"] = [
        {"from_atom_code": "A0", "to_atom_code": "A1", "kind": "progression", "reason": "推导"},
        {"from_atom_code": "A1", "to_atom_code": "A2", "kind": "progression", "reason": "应用"},
    ]
    assert validate_steps(plan, atoms, [edge("A0", "A2"), edge("A2", "A3")], get_profile("formula_derivation_chain")) == []


@pytest.mark.parametrize("violation", ["backward", "capacity", "lines", "missing", "duplicate", "summary", "same_step", "branch"])
def test_step_invariant_failures(violation):
    atoms = atoms_fixture()
    plan = plan_fixture(atoms)
    edges = []
    profile = get_profile("formula_derivation_chain")
    if violation == "backward":
        edges = [edge("A5", "A0")]
    elif violation == "capacity":
        plan["steps"][0]["core_atoms"] = [atom["code"] for atom in atoms[:5]]
        plan["steps"][1]["core_atoms"] = ["A5"]
    elif violation == "lines":
        plan["steps"][0]["intra_lines"] = [
            {"from_atom_code": "A0", "to_atom_code": "A1", "kind": "contrast", "reason": "比较"}
            for _ in range(4)]
    elif violation == "missing":
        plan["steps"][1]["core_atoms"].pop()
    elif violation == "duplicate":
        plan["steps"][1]["extension_atoms"].append("A0")
    elif violation == "summary":
        plan["narrative_summary"] = "学习点0"
    elif violation == "same_step":
        edges = [edge("A0", "A1")]
    else:
        profile = get_profile("taskflow_diagnostic_tree")
    assert validate_steps(plan, atoms, edges, profile)


@pytest.mark.parametrize("dimension", [384, 1024, 1536])
def test_online_embedding_dynamic_dimensions_and_normalization(monkeypatch, dimension):
    monkeypatch.setattr(config, "EMBEDDING_DIMENSIONS", dimension)
    calls = []

    def post(url, **kwargs):
        calls.append(kwargs["json"])
        data = [{"index": index, "embedding": [float(index + 1)] * dimension}
                for index in reversed(range(len(kwargs["json"]["input"])))]
        return httpx.Response(200, json={"data": data}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    views = embed_views(atoms_fixture(), batch_size=2)
    assert len(calls) == 9
    for matrix in views.values():
        assert matrix.shape == (6, dimension)
        assert matrix.dtype == np.float64
        np.testing.assert_allclose(np.linalg.norm(matrix, axis=1), 1)


@pytest.mark.parametrize("status", [400, 503])
def test_embedding_http_error_raises_typed_failure(monkeypatch, status):
    monkeypatch.setattr(httpx, "post", lambda url, **kwargs: httpx.Response(status, request=httpx.Request("POST", url)))
    with pytest.raises(EmbeddingError, match="HTTP/JSON"):
        embed_views(atoms_fixture())


@pytest.mark.parametrize("bad", ["zero", "nonfinite", "ragged", "index", "dimension"])
def test_embedding_malformed_response_raises(monkeypatch, bad):
    monkeypatch.setattr(config, "EMBEDDING_DIMENSIONS", 2)

    def post(url, **kwargs):
        rows = [{"index": index, "embedding": [1., 2.]} for index in range(len(kwargs["json"]["input"]))]
        if bad == "zero":
            rows[0]["embedding"] = [0., 0.]
        elif bad == "nonfinite":
            rows[0]["embedding"] = [np.nan, 1.]
        elif bad == "ragged":
            rows[0]["embedding"] = [1.]
        elif bad == "index":
            rows[0]["index"] = 1
        else:
            for row in rows:
                row["embedding"] = [1.]
        response = httpx.Response(200, request=httpx.Request("POST", url))
        response.json = lambda: {"data": rows}
        return response

    monkeypatch.setattr(httpx, "post", post)
    with pytest.raises(EmbeddingError):
        embed_views(atoms_fixture())


def test_diagnostic_atoms_require_explicit_branch_conditions():
    atoms = atoms_fixture()
    modules = [{"code": "M1", "title": "鉴别诊断", "parent_code": ""}]
    profile = get_profile("taskflow_diagnostic_tree")
    assert any("branch_condition" in message for message in validate_atoms(atoms, modules, profile))
    for atom in atoms:
        atom["branch_condition"] = "出现危险征象时转入紧急处置路径"
    assert validate_atoms(atoms, modules, profile) == []


def test_bge_model_omits_dimensions_param_for_siliconflow(monkeypatch):
    monkeypatch.setattr(config, "EMBEDDING_BASE_URL", "https://api.siliconflow.cn/v1")
    monkeypatch.setattr(config, "EMBEDDING_MODEL", "BAAI/bge-m3")
    monkeypatch.setattr(config, "EMBEDDING_DIMENSIONS", 8)
    bodies = []

    def post(url, **kwargs):
        assert url == "https://api.siliconflow.cn/v1/embeddings"
        bodies.append(kwargs["json"])
        data = [{"index": idx, "embedding": [float(idx + 1)] * 8} for idx in range(len(kwargs["json"]["input"]))]
        return httpx.Response(200, json={"data": data}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    views = embed_views(atoms_fixture(), batch_size=32)
    assert all("dimensions" not in body for body in bodies)
    assert views["namegoal"].shape == (6, 8)


def test_qwen3_model_sends_dimensions_and_normalizes_full_endpoint(monkeypatch):
    monkeypatch.setattr(config, "EMBEDDING_BASE_URL", "https://api.siliconflow.cn/v1/embeddings/")
    monkeypatch.setattr(config, "EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B")
    monkeypatch.setattr(config, "EMBEDDING_DIMENSIONS", 6)
    bodies = []

    def post(url, **kwargs):
        assert url == "https://api.siliconflow.cn/v1/embeddings"
        bodies.append(kwargs["json"])
        data = [{"index": idx, "embedding": [1.0] * 6} for idx in range(len(kwargs["json"]["input"]))]
        return httpx.Response(200, json={"data": data}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    views = embed_views(atoms_fixture(), batch_size=32)
    assert all(body["dimensions"] == 6 for body in bodies)
    assert views["parent"].shape == (6, 6)


def test_zero_configured_dimensions_discovers_native_dimension_dynamically(monkeypatch):
    monkeypatch.setattr(config, "EMBEDDING_BASE_URL", "https://api.siliconflow.cn/v1")
    monkeypatch.setattr(config, "EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-4B")
    monkeypatch.setattr(config, "EMBEDDING_DIMENSIONS", 0)
    bodies = []

    def post(url, **kwargs):
        bodies.append(kwargs["json"])
        data = [{"index": idx, "embedding": [2.0] * 12} for idx in range(len(kwargs["json"]["input"]))]
        return httpx.Response(200, json={"data": data}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    views = embed_views(atoms_fixture(), batch_size=3)
    assert all("dimensions" not in body for body in bodies)
    assert views["point"].shape == (6, 12)


def test_embedding_http_error_surfaces_provider_body(monkeypatch):
    def post(url, **kwargs):
        return httpx.Response(400, text='{"message":"dimensions unsupported"}', request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    with pytest.raises(EmbeddingError, match="dimensions unsupported"):
        embed_views(atoms_fixture())


def test_knowledge_builder_tasks_all_use_flash_tier(monkeypatch):
    monkeypatch.delenv("AI_MODEL_GENERATE_KNOWLEDGE_TREE", raising=False)
    monkeypatch.delenv("AI_MODEL_KNOWLEDGE_TREE_DISPATCH", raising=False)
    monkeypatch.delenv("AI_MODEL_SCHEMA_REPAIR", raising=False)
    monkeypatch.delenv("AI_MODEL_FAST", raising=False)
    for task in ("knowledge_tree_dispatch", "knowledge_tree_decompose", "knowledge_tree_edges",
                 "knowledge_tree_repair", "knowledge_tree_block"):
        assert config.get_model_for_task(task)["model"] == config.FALLBACK_FAST


def test_outline_normalization_derives_canonical_paths_and_rejects_broken_trees():
    from knowledge_builder.exceptions import InvariantViolationError
    from knowledge_builder.pipeline import _normalize_outline

    normalized = _normalize_outline([
        {"code": "M1.1", "parent_code": "M1", "title": "第二节", "path": "x/y", "depth": 0, "order": 1},
        {"code": "M1", "parent_code": "", "title": "第一章", "path": "ignored", "depth": 9, "order": 1},
    ])
    assert [m["code"] for m in normalized] == ["M1", "M1.1"]
    assert normalized[0]["depth"] == 1 and normalized[0]["path"] == "第一章"
    assert normalized[1]["depth"] == 2 and normalized[1]["path"] == "第一章 > 第二节"

    with pytest.raises(InvariantViolationError, match="cycle"):
        _normalize_outline([
            {"code": "A", "parent_code": "B", "title": "A", "path": "A", "depth": 1, "order": 1},
            {"code": "B", "parent_code": "A", "title": "B", "path": "B", "depth": 2, "order": 2},
        ])


def test_edge_batch_retries_only_missing_pairs_then_fails_fast(monkeypatch):
    from knowledge_builder.exceptions import InvariantViolationError
    from knowledge_builder.pipeline import _classify_edge_batch

    atoms = atoms_fixture(3)
    profile = get_profile("institution_mechanism_theory").as_dict()
    calls = []

    def fake_ask(name, context, operation):
        calls.append([tuple(item["code"] for item in pair) for pair in context["pairs"]])
        if len(calls) == 1:
            return {"edges": [{"from_atom": "A0", "to_atom": "A1", "edge_strength": "strong", "relation_label": "先修", "rationale": "依赖", "confidence": 0.9}]}
        return {"edges": [{"from_atom": "A1", "to_atom": "A2", "edge_strength": "none", "relation_label": "", "rationale": "无关", "confidence": 0.5}]}

    monkeypatch.setattr("knowledge_builder.pipeline.ask", fake_ask)
    edges = _classify_edge_batch(atoms, [(0, 1), (1, 2)], profile)
    assert calls == [[("A0", "A1"), ("A1", "A2")], [("A1", "A2")]]
    assert len(edges) == 1 and edges[0]["from_atom"] == "A0"

    monkeypatch.setattr("knowledge_builder.pipeline.ask", lambda *args, **kwargs: {"edges": []})
    with pytest.raises(InvariantViolationError, match="cover each candidate pair"):
        _classify_edge_batch(atoms, [(0, 1)], profile)


def test_block_naming_chunks_and_retries_missing_codes(monkeypatch):
    from knowledge_builder.pipeline import _name_blocks

    atoms = atoms_fixture(14)
    blocks = [{"code": f"B{i + 1:02d}", "atoms": [atoms[i]]} for i in range(14)]
    seen_batches = []

    def fake_ask(name, context, operation):
        assert name == "block_naming"
        assert "block_outline" in context
        seen_batches.append([b["code"] for b in context["blocks"]])
        assert all("common_misconceptions" not in a for b in context["blocks"] for a in b["atoms"])
        rows = context["blocks"][:-1] if len(seen_batches) == 1 else context["blocks"]
        return {"blocks": [{"code": b["code"], "short_title": f"学{b['code']}", "is_entry_block": b["code"] == "B01", "rationale": "清晰"} for b in rows]}

    monkeypatch.setattr("knowledge_builder.pipeline.ask", fake_ask)
    _name_blocks(blocks, {"subject": "私募", "profile": get_profile("institution_mechanism_theory").as_dict()})
    assert seen_batches[0] == [f"B{i + 1:02d}" for i in range(12)]
    assert seen_batches[1] == ["B12"]
    assert seen_batches[2] == ["B13", "B14"]
    assert all(b["short_title"] == f"学{b['code']}" for b in blocks)


def test_review_blocks_recovers_orphan_block_with_targeted_pass(monkeypatch):
    import numpy as np
    from knowledge_builder.pipeline import _review_blocks

    profile = get_profile("institution_mechanism_theory")
    atoms = atoms_fixture(3)
    blocks = [{"code": f"B{i + 1:02d}", "short_title": f"块{i}", "is_entry_block": i == 0, "atoms": [atoms[i]]} for i in range(3)]
    views = {"namegoal": np.eye(3, 6)}
    calls = []

    def fake_ask(name, context, operation):
        calls.append((context.get("repair_reason", ""), [(e["from_block"], e["to_block"]) for e in context["evidence"]]))
        if "repair_reason" not in context:
            edges = [{"from_block": e["from_block"], "to_block": e["to_block"],
                      "edge_kind": "unidirectional" if e["to_block"] == "B02" else "none",
                      "directness_score": 4, "rationale": "局部"} for e in context["evidence"]]
            return {"entry_blocks": ["B01"], "edges": edges}
        return {"entry_blocks": ["B01"], "edges": [{"from_block": e["from_block"], "to_block": e["to_block"],
                                                     "edge_kind": "unidirectional", "directness_score": 4, "rationale": "补全"} for e in context["evidence"]]}

    monkeypatch.setattr("knowledge_builder.pipeline.ask", fake_ask)
    graph = _review_blocks(blocks, [[0], [1], [2]], atoms, [], views, profile)
    assert len(calls) == 2
    assert "B03" in calls[1][0]
    assert graph["layers"]["B03"] > graph["layers"]["B01"]


def test_interfaces_retries_invalid_selection_then_succeeds(monkeypatch):
    import numpy as np
    from knowledge_builder.pipeline import _interfaces

    profile = get_profile("institution_mechanism_theory")
    atoms = atoms_fixture(2)
    calls = []

    def fake_ask(name, context, operation):
        calls.append(context.get("error", ""))
        if len(calls) == 1:
            return {"interfaces": [{"from_atom": "A1", "to_atom": "A0", "interface_role": "prerequisite_handoff", "bridge_explanation": "反向"}]}
        return {"interfaces": [{"from_atom": "A0", "to_atom": "A1", "interface_role": "prerequisite_handoff", "bridge_explanation": "正向"}]}

    monkeypatch.setattr("knowledge_builder.pipeline.ask", fake_ask)
    result = _interfaces({"from_block": "B01", "to_block": "B02"}, {"A0": atoms[0]}, {"A1": atoms[1]}, [], np.eye(2), {"A0": 0, "A1": 1}, profile)
    assert len(calls) == 2 and calls[1]
    assert result[0]["from_atom"] == "A0"


def test_ask_retries_once_on_schema_error_and_then_raises(monkeypatch):
    from ai_engine.ai_service import AIService
    from knowledge_builder.exceptions import AIResponseError
    from knowledge_builder.prompts import ask

    prompts = []

    def flaky(**kwargs):
        prompts.append(kwargs["user_prompt"])
        if len(prompts) == 1:
            return {"archetype": "wrong_enum"}
        return {"archetype": "institution_mechanism_theory"}

    monkeypatch.setattr(AIService, "structured_output", flaky)
    assert ask("archetype_classify", {"subject": "PE"}, "knowledge_tree_dispatch") == {"archetype": "institution_mechanism_theory"}
    assert len(prompts) == 2 and "schema_error" in prompts[1]

    monkeypatch.setattr(AIService, "structured_output", lambda **kwargs: {"archetype": "still_wrong"})
    with pytest.raises(AIResponseError, match="invalid structured response"):
        ask("archetype_classify", {"subject": "PE"}, "knowledge_tree_dispatch")


def test_render_messages_hoists_static_prefix_into_system_prompt_for_kv_cache():
    from knowledge_builder.prompts import render_messages

    profile = get_profile("institution_mechanism_theory").as_dict()
    catalog = [{"code": "A0", "name": "核心定义"}, {"code": "A1", "name": "募集流程"}]
    s1, u1 = render_messages("edge_classify", {"subject": "私募", "profile": profile, "atom_catalog": catalog, "pairs": [[{"code": "A0", "name": "核心定义"}, {"code": "A1", "name": "募集流程"}]]})
    s2, u2 = render_messages("edge_classify", {"subject": "私募", "profile": profile, "atom_catalog": catalog, "pairs": [[{"code": "A1", "name": "募集流程"}, {"code": "A0", "name": "核心定义"}]]})
    assert s1 == s2
    assert "atom_catalog" in s1 and "核心定义" in s1
    assert "atom_catalog" not in u1 and u1 != u2

    summaries = [{"code": "B01", "short_title": "基础", "is_entry_block": True, "atom_names": ["核心定义"]}]
    b1_sys, b1_user = render_messages("intrablock_steps", {"subject": "私募", "profile": profile, "block_summaries": summaries, "block": {"code": "B01"}})
    b2_sys, b2_user = render_messages("intrablock_steps", {"subject": "私募", "profile": profile, "block_summaries": summaries, "block": {"code": "B02"}})
    assert b1_sys == b2_sys and "block_summaries" in b1_sys
    assert "block_summaries" not in b1_user and "block_summaries" not in b2_user


def test_validate_steps_reports_exact_coverage_diffs():
    atoms = atoms_fixture(4)
    plan = {
        "steps": [
            {"step_title": "步一", "step_role": "核心概念", "branch_condition": "", "core_atoms": ["A0", "A0", "AX"], "extension_atoms": [], "intra_lines": []},
            {"step_title": "步二", "step_role": "传导机制", "branch_condition": "", "core_atoms": ["A1"], "extension_atoms": [], "intra_lines": []},
        ],
        "narrative_summary": "学习点0 学习点1 学习点2 学习点3",
    }
    errors = validate_steps(plan, atoms, [], get_profile("institution_mechanism_theory"))
    coverage = [msg for msg in errors if msg.startswith("coverage:")]
    assert len(coverage) == 1
    assert "missing=['A2', 'A3']" in coverage[0]
    assert "duplicated=['A0']" in coverage[0]
    assert "unknown=['AX']" in coverage[0]


def test_call_ai_logs_cached_tokens_from_usage(monkeypatch):
    from unittest.mock import Mock
    from ai_engine import service

    events = []
    fake_resp = Mock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {
        "choices": [{"message": {"content": "ok"}}],
        "usage": {"prompt_tokens": 1200, "completion_tokens": 50, "prompt_cache_hit_tokens": 1024, "prompt_cache_miss_tokens": 176},
    }
    monkeypatch.setattr(service, "get_model_for_task", lambda op: {"api_key": "k", "base_url": "https://example.com", "model": "deepseek-v4-flash", "thinking": None})
    monkeypatch.setattr(service._session, "post", lambda *args, **kwargs: fake_resp)
    monkeypatch.setattr(service, "record_ai_operation", lambda **kwargs: events.append(kwargs))

    service.AIEngine.call_ai([{"role": "user", "content": "hi"}], operation="knowledge_tree_edges")
    assert events[0]["metadata"]["cached_tokens"] == 1024
    assert events[0]["metadata"]["cache_miss_tokens"] == 176
    fake_resp.json.return_value.pop("usage")
    service.AIEngine.call_ai([{"role": "user", "content": "hi"}], operation="knowledge_tree_edges")
    assert not {"prompt_tokens", "completion_tokens"} & events[1]["metadata"].keys()


def test_strong_topo_order_respects_internal_strong_edges():
    from knowledge_builder.pipeline import _strong_topo_order, _suggest_step_buckets

    atoms = atoms_fixture(4)
    local_edges = [edge("A3", "A1", "strong"), edge("A1", "A0", "strong"), edge("A0", "A2", "contrast")]
    order = _strong_topo_order(atoms, local_edges)
    assert set(order) == {"A0", "A1", "A2", "A3"}
    assert order.index("A3") < order.index("A1") < order.index("A0")

    dense_atoms = atoms_fixture(12)
    dense_edges = [
        edge("A0", "A1", "strong"), edge("A1", "A2", "strong"),
        edge("A3", "A4", "strong"), edge("A4", "A5", "strong"),
        edge("A6", "A7", "strong"),
    ]
    buckets = _suggest_step_buckets(dense_atoms, dense_edges)
    assert 2 <= len(buckets) <= 5
    assert all(1 <= len(b) <= 4 for b in buckets)
    flat = [code for b in buckets for code in b]
    assert set(flat) == {a["code"] for a in dense_atoms} and len(flat) == 12
    pos = {code: idx for idx, b in enumerate(buckets) for code in b}
    assert all(pos[e["from_atom"]] <= pos[e["to_atom"]] for e in dense_edges)
