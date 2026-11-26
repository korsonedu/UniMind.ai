"""Fine-grained misconception diagnosis & hybrid retrieval service (BM25 + Dense RRF + optional LLM rerank).

Addresses the limitation of coarse 5-bucket keyword rules in wrong_question_insights.py by
indexing structured misconception catalogs (e.g., Eedi, MathDial, or curriculum misconception banks)
and matching student errors using lexical BM25, optional semantic embeddings, and optional
LLM error-diff reranking.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
import json
import math
import re
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple


_EN_STOPWORDS = frozenset(
    "a an and are as at be by for from has have how in is it of on or that the this to was were "
    "what when where which who with".split()
)


def tokenize_bilingual(text: str) -> List[str]:
    """Tokenize English words + Chinese character unigrams/bigrams for bilingual BM25."""
    if not text:
        return []
    low = text.lower()
    tokens: List[str] = []
    # English / numeric tokens
    for w in re.findall(r"[a-z0-9]+", low):
        if len(w) > 1 and w not in _EN_STOPWORDS:
            tokens.append(w)
    # Chinese character sequences -> unigrams + bigrams
    for seg in re.findall(r"[\u4e00-\u9fff]+", low):
        if len(seg) == 1:
            tokens.append(seg)
        else:
            for i in range(len(seg)):
                tokens.append(seg[i])
                if i + 1 < len(seg):
                    tokens.append(seg[i : i + 2])
    return tokens


@dataclass(frozen=True)
class MisconceptionEntry:
    misconception_id: str
    name: str
    subject: str = ""
    topic: str = ""
    description: str = ""

    def index_text(self) -> str:
        parts = [self.name, self.description, self.topic, self.subject]
        return " ".join(p.strip() for p in parts if p and p.strip())


class MisconceptionDiagnoser:
    """Hybrid BM25 + optional dense embedding + optional LLM error-diff misconception diagnoser."""

    def __init__(
        self,
        catalog: Sequence[MisconceptionEntry],
        *,
        k1: float = 1.5,
        b: float = 0.75,
        embed_fn: Optional[Callable[[List[str]], List[List[float]]]] = None,
    ):
        self.catalog = list(catalog)
        self.k1 = k1
        self.b = b
        self._embed_fn = embed_fn
        self._doc_texts = [e.index_text() for e in self.catalog]
        self._tfs = [Counter(tokenize_bilingual(t)) for t in self._doc_texts]
        self._doc_lens = [sum(c.values()) for c in self._tfs]
        self._avgdl = (sum(self._doc_lens) / len(self._doc_lens)) if self._doc_lens else 1.0
        self._n = len(self.catalog)

        df = Counter()
        self._postings: Dict[str, List[Tuple[int, int]]] = defaultdict(list)
        for idx, c in enumerate(self._tfs):
            for tok, tf in c.items():
                df[tok] += 1
                self._postings[tok].append((idx, tf))
        self._idf = {
            tok: math.log((self._n - freq + 0.5) / (freq + 0.5) + 1.0)
            for tok, freq in df.items()
        }

        self._doc_vecs: Optional[List[List[float]]] = None
        if self._embed_fn is not None and self._doc_texts:
            self._doc_vecs = self._normalize_vecs(self._embed_fn(self._doc_texts))

    @staticmethod
    def _normalize_vecs(vecs: Sequence[Sequence[float]]) -> List[List[float]]:
        normed = []
        for v in vecs:
            n = math.sqrt(sum(float(x) * float(x) for x in v)) or 1.0
            normed.append([float(x) / n for x in v])
        return normed

    def _bm25_scores(self, query: str) -> List[float]:
        scores = [0.0] * self._n
        for tok in set(tokenize_bilingual(query)):
            idf = self._idf.get(tok)
            if not idf:
                continue
            for idx, tf in self._postings[tok]:
                denom = tf + self.k1 * (1.0 - self.b + self.b * self._doc_lens[idx] / self._avgdl)
                scores[idx] += idf * (tf * (self.k1 + 1.0) / denom)
        return scores

    def _dense_scores(self, query: str) -> Optional[List[float]]:
        if self._embed_fn is None or not self._doc_vecs:
            return None
        q_vec = self._normalize_vecs(self._embed_fn([query]))[0]
        return [sum(a * b for a, b in zip(q_vec, d_vec)) for d_vec in self._doc_vecs]

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 10,
        rrf_k: int = 60,
        bm25_weight: float = 1.0,
        dense_weight: float = 1.0,
    ) -> List[Dict[str, object]]:
        """Retrieve ranked misconception candidates using BM25 or Hybrid BM25+Dense RRF."""
        if not self.catalog:
            return []
        bm25 = self._bm25_scores(query)
        bm25_order = sorted(range(self._n), key=lambda i: -bm25[i])
        dense = self._dense_scores(query)

        if dense is None:
            ranked_indices = bm25_order[:top_k]
            final_scores = {i: bm25[i] for i in ranked_indices}
        else:
            dense_order = sorted(range(self._n), key=lambda i: -dense[i])
            rrf: Dict[int, float] = defaultdict(float)
            pool = min(self._n, max(50, top_k * 3))
            for rank, idx in enumerate(bm25_order[:pool], 1):
                if bm25[idx] > 0:
                    rrf[idx] += bm25_weight / (rrf_k + rank)
            for rank, idx in enumerate(dense_order[:pool], 1):
                rrf[idx] += dense_weight / (rrf_k + rank)
            ranked_indices = [idx for idx, _ in sorted(rrf.items(), key=lambda x: -x[1])[:top_k]]
            final_scores = dict(rrf)

        return [
            {
                "misconception_id": self.catalog[idx].misconception_id,
                "name": self.catalog[idx].name,
                "subject": self.catalog[idx].subject,
                "topic": self.catalog[idx].topic,
                "score": round(float(final_scores.get(idx, 0.0)), 6),
            }
            for idx in ranked_indices
        ]

    def diagnose_with_llm(
        self,
        *,
        question: str,
        student_answer: str,
        correct_answer: str = "",
        llm_call: Callable[[str], str],
        top_k: int = 5,
        candidate_pool: int = 20,
    ) -> Dict[str, object]:
        """Two-stage diagnosis: hybrid retrieval -> LLM error-diff reranking over candidate pool."""
        query = f"Question: {question}\nCorrect answer: {correct_answer}\nStudent wrong answer: {student_answer}"
        candidates = self.retrieve(query, top_k=candidate_pool)
        if not candidates:
            return {"candidates": [], "ranked_ids": [], "reasoning": ""}

        cand_lines = "\n".join(
            f"- [{c['misconception_id']}] {c['name']}" for c in candidates
        )
        prompt = (
            "You are a math/education misconception diagnostician.\n"
            "Analyze WHY the student produced the wrong answer compared to the correct answer, "
            "then rank the most likely misconception IDs from the candidate list.\n"
            f"Question: {question}\n"
            f"Correct answer: {correct_answer}\n"
            f"Student answer: {student_answer}\n\n"
            f"Candidate misconceptions:\n{cand_lines}\n\n"
            'Return ONLY valid JSON: {"reasoning": "1 sentence error diff", '
            '"ranked_ids": ["id1", "id2", ...]} (up to ' + str(top_k) + ' IDs from candidates only).'
        )
        raw = llm_call(prompt)
        valid_ids = {c["misconception_id"] for c in candidates}
        by_id = {c["misconception_id"]: c for c in candidates}
        reasoning = ""
        ranked_ids: List[str] = []
        try:
            cleaned = raw.strip()
            if "```" in cleaned:
                cleaned = cleaned.split("```")[1].removeprefix("json").strip()
            parsed = json.loads(cleaned)
            reasoning = str(parsed.get("reasoning", "")).strip()
            for mid in parsed.get("ranked_ids", []):
                mid_s = str(mid)
                if mid_s in valid_ids and mid_s not in ranked_ids:
                    ranked_ids.append(mid_s)
        except Exception:
            pass

        # Append remaining hybrid candidates to preserve recall beyond top_k
        for c in candidates:
            if c["misconception_id"] not in ranked_ids:
                ranked_ids.append(c["misconception_id"])
        ordered = [by_id[mid] for mid in ranked_ids[:top_k]]
        return {
            "reasoning": reasoning,
            "ranked_ids": ranked_ids,
            "candidates": ordered,
        }


# Built-in fine-grained misconception catalog covering UniMind's core curriculum subjects
# (Finance 431, High School Math, High School Physics, General Algebra/Arithmetic).
CORE_SUBJECT_MISCONCEPTIONS: Tuple[MisconceptionEntry, ...] = (
    # ── Finance 431 ──
    MisconceptionEntry(
        "fin_cashflow_t0_discount",
        "把第0期初始现金流误当成第1期进行折现，或在NPV计算中遗漏期初投入的负号",
        "金融431", "现金流折现与NPV",
        "净现值 折现 第0期 时间轴 期初投资 现金流时点",
    ),
    MisconceptionEntry(
        "fin_duration_convexity_sign",
        "混淆麦考利久期与修正久期，或忽略利率上升时债券价格下跌的反向关系与凸性二阶项",
        "金融431", "债券久期与凸性",
        "久期 修正久期 凸性 利率变动 债券价格 票息 折现因子",
    ),
    MisconceptionEntry(
        "fin_capm_beta_risk",
        "混淆系统性风险(β)与总风险(标准差σ)，在CAPM中错误使用标准差替代贝塔系数",
        "金融431", "CAPM与资产定价",
        "CAPM 贝塔 系统性风险 非系统性风险 期望收益率 市场风险溢价",
    ),
    MisconceptionEntry(
        "fin_wacc_tax_shield",
        "计算WACC加权平均资本成本时忘记对债务成本乘以(1-T)税盾，或误用账面价值替代市场价值权重",
        "金融431", "资本成本与WACC",
        "WACC 加权平均资本成本 税盾 债务成本 股权成本 市值权重",
    ),
    MisconceptionEntry(
        "fin_mm_leverage_value",
        "混淆无税MM定理与有税MM定理，错误认为财务杠杆在无税条件下能提升公司总价值",
        "金融431", "资本结构与MM定理",
        "MM定理 财务杠杆 资本结构 破产成本 权衡理论 税盾现值",
    ),
    MisconceptionEntry(
        "fin_money_multiplier",
        "计算货币乘数时遗漏超额准备金率或现金漏损率，误用简单存款乘数1/rd",
        "金融431", "货币供给与货币乘数",
        "货币乘数 基础货币 法定准备金率 超额准备金 现金漏损率",
    ),
    MisconceptionEntry(
        "fin_ppp_irp_parity",
        "混淆购买力平价(PPP)与利率平价(IRP)的升贴水方向，把高利率货币误判为远期升水",
        "金融431", "国际金融与汇率平价",
        "购买力平价 利率平价 远期汇率 升水 贴水 汇率决定",
    ),
    # ── High School Math ──
    MisconceptionEntry(
        "math_domain_neglected",
        "求解函数单调性、极值或对数/分式方程时忽略定义域限制，导致增根或区间错误",
        "高中数学", "函数与定义域",
        "定义域 对数真数大于零 分母不为零 单调区间 增根",
    ),
    MisconceptionEntry(
        "math_derivative_extremum",
        "误把导数为零(f'(x0)=0)当成极值点的充分条件，未检验左右两侧导数变号",
        "高中数学", "导数与极值",
        "导数 极值点 驻点 变号 单调性 充分必要条件",
    ),
    MisconceptionEntry(
        "math_inequality_sign_flip",
        "不等式两边同乘或同除负数时忘记改变不等号方向，或未对含参系数分类讨论正负",
        "高中数学", "不等式与代数变形",
        "不等号方向 负数 含参分类讨论 inequality sign flip negative",
    ),
    MisconceptionEntry(
        "math_sequence_n1_check",
        "由前n项和Sn求通项an=Sn-S(n-1)时忘记单独验证n=1的情况",
        "高中数学", "数列通项与求和",
        "数列 通项公式 前n项和 Sn n=1 分段验证",
    ),
    MisconceptionEntry(
        "math_probability_independence",
        "混淆互斥事件与相互独立事件，误将P(A∪B)=P(A)+P(B)用于非互斥事件或误用乘法公式",
        "高中数学", "概率与统计",
        "互斥 独立事件 条件概率 全概率 贝叶斯 排列组合",
    ),
    MisconceptionEntry(
        "math_vector_angle_projection",
        "混淆向量数量积正负与夹角钝锐角关系，漏掉反向共线(180°)或同向共线(0°)的边界情形",
        "高中数学", "平面与空间向量",
        "向量 数量积 夹角 投影 钝角 共线 空间几何",
    ),
    # ── High School Physics ──
    MisconceptionEntry(
        "phys_force_motion_aristotle",
        "误以为物体维持匀速直线运动需要外力作用，或混淆速度方向与加速度/合外力方向",
        "高中物理", "牛顿运动定律",
        "牛顿定律 合外力 加速度 匀速 惯性 受力分析",
    ),
    MisconceptionEntry(
        "phys_friction_direction_max",
        "误把动摩擦因数直接用于静摩擦力计算，或误认为摩擦力方向总与物体运动方向相反",
        "高中物理", "摩擦力与受力分析",
        "静摩擦力 滑动摩擦力 相对运动趋势 受力分析",
    ),
    MisconceptionEntry(
        "phys_conservation_condition",
        "忽略动量守恒或机械能守恒的适用条件，在有外力做功或非弹性碰撞时误套守恒公式",
        "高中物理", "动量与能量守恒",
        "动量守恒 机械能守恒 动能定理 非弹性碰撞 摩擦生热",
    ),
    MisconceptionEntry(
        "phys_em_lenz_direction",
        "应用楞次定律或左手/右手定则时混淆磁场方向与磁通量变化方向，导致感应电流或安培力方向反向",
        "高中物理", "电磁感应与磁场",
        "楞次定律 磁通量 感应电流 安培力 洛伦兹力 左手定则 右手定则",
    ),
    # ── General Algebra / Arithmetic ──
    MisconceptionEntry(
        "gen_order_of_operations",
        "违反四则运算优先级(先乘除后加减/括号优先)，按从左到右顺序直接计算",
        "通用数学", "运算顺序",
        "运算顺序 括号 乘除 加减 order of operations PEMDAS BODMAS",
    ),
    MisconceptionEntry(
        "gen_fraction_add_denom",
        "分数相加减时未先通分，直接把分子与分子、分母与分母分别相加",
        "通用数学", "分数运算",
        "分数 通分 分子 分母 fraction numerator denominator",
    ),
    MisconceptionEntry(
        "gen_sign_distribution",
        "去括号或移项时漏改负号，或展开(a+b)^2时遗漏交叉项2ab",
        "通用数学", "代数展开与符号",
        "去括号 移项 负号 完全平方 分配律 distribute negative sign",
    ),
)

_DEFAULT_DIAGNOSER: Optional[MisconceptionDiagnoser] = None


def get_default_diagnoser() -> MisconceptionDiagnoser:
    """Return cached bilingual BM25 diagnoser over UniMind's core subject misconception catalog."""
    global _DEFAULT_DIAGNOSER
    if _DEFAULT_DIAGNOSER is None:
        _DEFAULT_DIAGNOSER = MisconceptionDiagnoser(CORE_SUBJECT_MISCONCEPTIONS)
    return _DEFAULT_DIAGNOSER
