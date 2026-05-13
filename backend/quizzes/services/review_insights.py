from collections import Counter
from typing import Dict, Iterable, List

from quizzes.models import ExamQuestionResult


CAUSE_RULES = [
    ("concept", ["概念", "定义", "术语", "本质", "含义"]),
    ("calculation", ["计算", "公式", "运算", "推导", "数量"]),
    ("reasoning", ["逻辑", "因果", "审题", "链条", "论证"]),
    ("memory", ["记忆", "混淆", "遗忘", "漏写", "遗漏"]),
]

CAUSE_LABELS = {
    "concept": "概念理解",
    "calculation": "计算推导",
    "reasoning": "审题与逻辑",
    "memory": "记忆稳定性",
    "expression": "表达完整性",
}


def infer_primary_cause(feedback: str, analysis: str) -> str:
    text = f"{feedback or ''} {analysis or ''}".strip().lower()
    if not text:
        return "expression"

    for key, keywords in CAUSE_RULES:
        if any(kw in text for kw in keywords):
            return key
    return "expression"


def build_exam_review_summary(results: Iterable[ExamQuestionResult], total_score: float, max_score: float, elo_change: int) -> Dict[str, object]:
    rows = list(results)
    if not rows:
        return {
            "summary_markdown": "本次暂无可复盘数据。",
            "cause_distribution": {},
            "wrong_count": 0,
            "action_items": [],
        }

    wrong_rows = [row for row in rows if not row.is_correct]
    wrong_count = len(wrong_rows)

    if wrong_count == 0:
        summary = (
            f"本次得分 **{total_score:.1f}/{max_score:.1f}**，ELO 变化 **{elo_change:+d}**。\n\n"
            "全部题目达标，建议下一轮提高题目难度并缩短答题时长，进入提速训练。"
        )
        return {
            "summary_markdown": summary,
            "cause_distribution": {},
            "wrong_count": 0,
            "action_items": [
                "下一轮题量+20%，保持正确率不低于80%",
                "开始计时训练，每题平均时长压缩到2-3分钟",
            ],
        }

    causes = [infer_primary_cause(row.feedback, row.analysis) for row in wrong_rows]
    counter = Counter(causes)
    top_causes = counter.most_common(3)

    cause_lines = [f"- {CAUSE_LABELS.get(cause, cause)}：{count} 题" for cause, count in top_causes]

    action_items: List[str] = []
    if counter.get("concept", 0) > 0:
        action_items.append("先用 15 分钟回看相关定义与核心结论，再做 3 题同考点小练。")
    if counter.get("calculation", 0) > 0:
        action_items.append("针对公式推导做 2 轮手算复现，重点记录易错步骤。")
    if counter.get("reasoning", 0) > 0:
        action_items.append("答题前先写结论框架（因果链/步骤），再填充细节。")
    if counter.get("memory", 0) > 0:
        action_items.append("把错题加入 24 小时内复习清单，明天同时间二次回测。")
    if not action_items:
        action_items.append("复盘本次错题的得分点缺口，并在下一轮先做同类型 5 题。")

    summary = (
        f"本次得分 **{total_score:.1f}/{max_score:.1f}**，ELO 变化 **{elo_change:+d}**。\n\n"
        f"共需重点复盘 **{wrong_count}** 题，主要短板：\n"
        + "\n".join(cause_lines)
        + "\n\n**下一轮执行建议**\n"
        + "\n".join([f"{idx + 1}. {item}" for idx, item in enumerate(action_items[:3])])
    )

    return {
        "summary_markdown": summary,
        "cause_distribution": {CAUSE_LABELS.get(k, k): v for k, v in counter.items()},
        "wrong_count": wrong_count,
        "action_items": action_items[:3],
    }
