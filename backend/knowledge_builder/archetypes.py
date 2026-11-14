"""Profiles that control clustering, graph reduction and step generation."""
from dataclasses import asdict, dataclass

from .exceptions import ArchetypeDispatchError


@dataclass(frozen=True)
class ArchetypeProfile:
    archetype: str
    block_size_range: tuple[int, int]
    edge_cap: int
    kernel_weights: dict[str, float]
    step_roles: tuple[str, ...]
    require_branch_condition: bool
    allow_bidirectional_contraction: bool
    max_contrast_ratio: float

    def as_dict(self):
        return asdict(self)


PROFILES = {
    "institution_mechanism_theory": ArchetypeProfile(
        "institution_mechanism_theory", (3, 14), 4,
        {"semantic": .65, "hierarchy": .15, "strong_edge": .12, "weak_contrast": .08},
        ("核心概念", "制度/规则", "传导机制", "理论与比较"), False, True, .35,
    ),
    "formula_derivation_chain": ArchetypeProfile(
        "formula_derivation_chain", (3, 12), 3,
        {"semantic": .55, "hierarchy": .15, "strong_edge": .25, "weak_contrast": .05},
        ("前置定义与公理", "定理推导链", "典型计算与建模", "边界与反例"), False, True, .2,
    ),
    "taskflow_diagnostic_tree": ArchetypeProfile(
        "taskflow_diagnostic_tree", (3, 14), 4,
        {"semantic": .60, "hierarchy": .15, "strong_edge": .18, "weak_contrast": .07},
        ("触发与表征识别", "鉴别诊断/分支路由", "标准处置与执行", "并发症/复盘验证"), True, True, .25,
    ),
    "case_synthesis_deduction": ArchetypeProfile(
        "case_synthesis_deduction", (3, 14), 4,
        {"semantic": .62, "hierarchy": .13, "strong_edge": .12, "weak_contrast": .13},
        ("情境与事实解构", "规则/框架匹配", "多方权衡推演", "综合结论与边界"), False, True, .4,
    ),
}


def get_profile(archetype):
    if archetype not in PROFILES:
        raise ArchetypeDispatchError(f"Unsupported archetype: {archetype!r}")
    return PROFILES[archetype]
