import json
import logging
import re
from collections import defaultdict
from typing import Any, Dict, List

from ai_service import AIService
from quizzes.models import ExamQuestionResult, UserQuestionStatus
from quizzes.services.review_insights import CAUSE_LABELS, infer_primary_cause

logger = logging.getLogger(__name__)

MAX_KP_GROUPS = 8
MAX_QUESTIONS_PER_KP = 3

SYSTEM_PROMPT = (
    "你是431金融学综合考试命题专家。你必须输出一个纯 JSON 数组，"
    "没有任何 markdown 标记（不要 ```json 代码块）、注释或额外文字。"
    "输出必须可直接被 Python json.loads() 解析。"
    "你命制的每一道题都必须是全新的，严禁与错题记录中的原题相同或高度相似。"
)

# 每题输出 schema 说明，两次调用共用
QUESTION_SCHEMA = """
每道题输出格式：
{
  "q_type": "objective",
  "subjective_type": "",
  "question": "题干",
  "options": {"A": "选项A", "B": "选项B", "C": "选项C", "D": "选项D"},
  "answer": "A（单个字母）",
  "grading_points": [],
  "difficulty_level": "easy|normal|hard",
  "related_knowledge_id": "知识点code",
  "explanation": "解题思路+考点定位+易错点"
}
主观题 q_type 为 "subjective"，subjective_type 为 "noun"/"calculate"/"essay"，
options 填空对象 {}，answer 填完整参考答案，
grading_points 填 [{"point": "采分点描述", "score": 分值}]。
"""


class MockExamGeneratorService:
    """基于用户错题调用 AI 生成全新模拟试卷题目（不入库），分两次 AI 调用防止响应溢出"""

    # ── 错题数据采集 ──

    @classmethod
    def _collect_wrong_question_data(cls, user) -> Dict[str, Any]:
        statuses = (
            UserQuestionStatus.objects
            .filter(user=user, wrong_count__gt=0)
            .select_related('question__knowledge_point')
            .order_by('-wrong_count')
        )
        if not statuses.exists():
            return {"is_empty": True, "knowledge_points": [], "overview": {"total_wrong_questions": 0, "total_kps": 0}}

        kp_groups = defaultdict(list)
        for s in statuses:
            q = s.question
            kp = q.knowledge_point
            if not kp:
                continue
            kp_groups[kp].append((s, q))

        kp_list = []
        for kp, items in sorted(kp_groups.items(), key=lambda x: len(x[1]), reverse=True)[:MAX_KP_GROUPS]:
            questions = []
            for s, q in items[:MAX_QUESTIONS_PER_KP]:
                latest_result = (
                    ExamQuestionResult.objects
                    .filter(exam__user=user, question=q)
                    .order_by('-exam__created_at')
                    .first()
                )
                cause = infer_primary_cause(
                    getattr(latest_result, 'feedback', '') or '',
                    getattr(latest_result, 'analysis', '') or '',
                )
                questions.append({
                    "text": q.text,
                    "q_type": q.q_type,
                    "subjective_type": q.subjective_type or "",
                    "user_answer": getattr(latest_result, 'user_answer', '') or '',
                    "correct_answer": q.correct_answer or "",
                    "cause": cause,
                    "cause_label": CAUSE_LABELS.get(cause, cause),
                })
            kp_list.append({
                "kp_id": kp.id,
                "kp_name": kp.name,
                "kp_code": kp.code or "",
                "total_wrong": len(items),
                "questions": questions,
            })

        return {
            "is_empty": False,
            "knowledge_points": kp_list,
            "overview": {
                "total_wrong_questions": statuses.count(),
                "total_kps": len(kp_list),
            },
        }

    # ── 错题上下文格式化 ──

    @classmethod
    def _format_wrong_question_context(cls, wrong_data: Dict[str, Any]) -> str:
        if wrong_data.get("is_empty"):
            return "该学生暂无错题记录。请根据431金融学综合核心知识点（货币银行学、国际金融、公司金融、投资学、衍生品）生成综合性模拟题。"

        lines = []
        for i, kp in enumerate(wrong_data["knowledge_points"], 1):
            lines.append(f"\n### 薄弱知识点 {i}：{kp['kp_name']} ({kp['kp_code']})")
            lines.append(f"该知识点下错题数：{kp['total_wrong']}")
            for j, q in enumerate(kp["questions"], 1):
                lines.append(f"\n错题{j}：{q['text']}")
                if q['user_answer']:
                    lines.append(f"  学生作答：{q['user_answer']}")
                if q['correct_answer']:
                    lines.append(f"  正确答案：{q['correct_answer']}")
                lines.append(f"  错误类型：{q['cause_label']}")
                lines.append(f"  题目类型：{q['q_type']}{'/' + q['subjective_type'] if q['subjective_type'] else ''}")
        return "\n".join(lines)

    # ── AI 调用 ──

    @classmethod
    def _call_ai_and_parse(cls, system_prompt: str, user_prompt: str, max_tokens: int = 8000) -> List[Dict[str, Any]]:
        """单次 AI 调用，解析 JSON 并返回题目列表"""
        try:
            response = AIService.simple_chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.4,
                max_tokens=max_tokens,
                raise_on_error=True,
                operation="quizzes.mock_exam_generate",
            )
        except Exception as exc:
            logger.exception("AI mock exam generation failed")
            raise RuntimeError(f"AI 命题服务暂时不可用: {str(exc)}") from exc

        content = AIService.extract_content(response)
        if not content:
            raise RuntimeError("AI 命题服务返回空内容，请稍后重试")

        # 先尝试 AIService.extract_json（处理 markdown 包裹情况）
        parsed = AIService.extract_json(content)
        if parsed is not None and isinstance(parsed, list):
            return parsed

        # 再尝试直接 json.loads
        try:
            parsed = json.loads(content)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

        # 最后尝试用正则提取 JSON 数组
        match = re.search(r'\[.*\]', content, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass

        logger.error("Failed to parse AI output (first 500 chars): %s", content[:500])
        raise RuntimeError("AI 命题格式解析失败: 返回内容非合法 JSON 数组")

    # ── 分批生成 ──

    @classmethod
    def _generate_objectives_and_nouns(cls, wrong_context: str) -> List[Dict[str, Any]]:
        """第 1 批：生成 10 道客观题 + 4 道名词解释"""
        user_prompt = f"""学生错题记录：
{wrong_context}

请生成 **10 道单选题** 和 **4 道名词解释**，基于上述薄弱知识点，采用同类知识点题、扩展题、改编题策略。

{QUESTION_SCHEMA}

输出格式：纯 JSON 数组，共 14 个对象。客观题 answer 只填单个字母，名词解释 answer 填120-220字完整参考答案。"""

        return cls._call_ai_and_parse(SYSTEM_PROMPT, user_prompt, max_tokens=8000)

    @classmethod
    def _generate_calcs_and_essays(cls, wrong_context: str) -> List[Dict[str, Any]]:
        """第 2 批：生成 2 道计算题 + 2 道论述题"""
        user_prompt = f"""学生错题记录：
{wrong_context}

请生成 **2 道计算题** 和 **2 道论述题**，基于上述薄弱知识点，采用同类知识点题、扩展题、改编题策略。

{QUESTION_SCHEMA}

计算题答案必须有"已知条件→公式→代入→计算过程→结果（含单位/经济含义）"完整推导。
论述题答案500-900字，结构为：核心原理解释 → ≥3个分论点 → 每个分论点展开"理论机制→公式/数量关系→结论"。

输出格式：纯 JSON 数组，共 4 个对象。"""

        return cls._call_ai_and_parse(SYSTEM_PROMPT, user_prompt, max_tokens=8000)

    # ── 字段映射 ──

    @staticmethod
    def _parse_grading_points_to_rubric(gp_value) -> List[Dict[str, Any]]:
        if isinstance(gp_value, list):
            return gp_value
        if isinstance(gp_value, str) and gp_value.strip():
            items = re.findall(r'(.+?)\((\d+)\s*分\)', gp_value)
            if items:
                return [{"point": p.strip(), "score": int(s)} for p, s in items]
        return []

    @classmethod
    def _categorize(cls, ai_questions: List[Dict[str, Any]]) -> Dict[str, list]:
        categorized: Dict[str, list] = {
            "objectives": [],
            "nouns": [],
            "calcs": [],
            "essays": [],
        }
        for q in ai_questions:
            q_type = str(q.get("q_type", "")).strip().lower()
            sub_type = str(q.get("subjective_type", "")).strip().lower()

            item = {
                "text": q.get("question", q.get("text", "")),
                "options": q.get("options") or {},
                "correct_answer": q.get("answer", q.get("correct_answer", "")),
                "ai_answer": q.get("explanation", q.get("ai_answer", "")),
                "rubric": cls._parse_grading_points_to_rubric(q.get("grading_points", [])),
            }

            if q_type == "objective":
                categorized["objectives"].append(item)
            elif q_type == "subjective":
                if sub_type == "noun":
                    categorized["nouns"].append(item)
                elif sub_type in ("calculate", "calc"):
                    categorized["calcs"].append(item)
                elif sub_type in ("essay", "short"):
                    categorized["essays"].append(item)
                else:
                    categorized["objectives"].append(item)
            else:
                categorized["objectives"].append(item)
        return categorized

    # ── 入口 ──

    @classmethod
    def generate_mock_exam_questions(cls, user) -> Dict[str, Any]:
        wrong_data = cls._collect_wrong_question_data(user)
        wrong_context = cls._format_wrong_question_context(wrong_data)

        # 分两批并行调用 AI，防止单次响应过大导致 JSON 解析失败
        questions_part1 = cls._generate_objectives_and_nouns(wrong_context)
        logger.info("Batch 1 (objectives+nouns) returned %d questions", len(questions_part1))

        questions_part2 = cls._generate_calcs_and_essays(wrong_context)
        logger.info("Batch 2 (calcs+essays) returned %d questions", len(questions_part2))

        all_questions = questions_part1 + questions_part2
        return cls._categorize(all_questions)
