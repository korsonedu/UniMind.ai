"""
AI 助教 Agent 工具执行器。

每个工具方法返回 JSON 字符串，供模型在多轮工具调用中消费。
"""

import json
from typing import Any, Dict, List


class AssistantToolExecutor:
    """将 tool_name 映射到实际数据库查询。捕获 user 和 institution 上下文。"""

    def __init__(self, user, institution=None):
        self.user = user
        self.institution = institution or getattr(user, 'institution', None)

    def __call__(self, tool_name: str, args: Dict[str, Any]) -> str:
        handler = getattr(self, f'_handle_{tool_name}', None)
        if handler is None:
            return json.dumps({"error": f"Unknown tool: {tool_name}"}, ensure_ascii=False)
        try:
            result = handler(args)
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    # ── Tool handlers ──────────────────────────────────────────

    def _handle_search_knowledge_tree(self, args: Dict) -> Dict:
        from quizzes.models import KnowledgePoint

        query = (args.get('query') or '').strip()
        subject = (args.get('subject') or '').strip()

        qs = KnowledgePoint.objects.filter(
            name__icontains=query,
            level='kp',
        )
        if subject:
            qs = qs.filter(subject=subject)
        if self.institution:
            qs = qs.filter(institution__in=[self.institution, None])

        kps = qs.values('code', 'name', 'subject', 'description')[:10]
        return {
            "found": len(kps),
            "results": [
                {
                    "code": kp['code'],
                    "name": kp['name'],
                    "subject": kp['subject'] or '',
                    "description": (kp['description'] or '')[:300],
                }
                for kp in kps
            ],
        }

    def _handle_get_user_weak_points(self, args: Dict) -> Dict:
        from django.db.models import Sum
        from quizzes.models import UserQuestionStatus

        aggregated = (
            UserQuestionStatus.objects
            .filter(user=self.user, wrong_count__gt=0)
            .values('question__knowledge_point__name', 'question__knowledge_point__code')
            .annotate(total_wrong=Sum('wrong_count'))
            .order_by('-total_wrong')[:5]
        )

        return {
            "weak_points": [
                {
                    "kp_name": item['question__knowledge_point__name'] or '未知',
                    "kp_code": item['question__knowledge_point__code'] or '',
                    "total_wrong": item['total_wrong'],
                }
                for item in aggregated
            ],
        }

    def _handle_get_user_wrong_questions(self, args: Dict) -> Dict:
        from quizzes.models import UserQuestionStatus

        limit = min(int(args.get('limit', 5)), 10)
        wrong_qs = (
            UserQuestionStatus.objects
            .filter(user=self.user, wrong_count__gt=0)
            .select_related('question__knowledge_point')
            .order_by('-wrong_count')[:limit]
        )

        return {
            "questions": [
                {
                    "id": wq.question_id,
                    "text": (wq.question.text or '')[:500],
                    "answer": (wq.question.correct_answer or '')[:300],
                    "q_type": wq.question.q_type,
                    "kp_name": wq.question.knowledge_point.name if wq.question.knowledge_point else '',
                    "wrong_count": wq.wrong_count,
                }
                for wq in wrong_qs
            ],
        }

    def _handle_lookup_question(self, args: Dict) -> Dict:
        from quizzes.models import Question

        qid = int(args.get('question_id', 0))
        try:
            q = Question.objects.select_related('knowledge_point').get(id=qid)
        except Question.DoesNotExist:
            return {"error": f"Question #{qid} not found"}

        return {
            "id": q.id,
            "text": q.text or '',
            "q_type": q.q_type,
            "subjective_type": q.subjective_type or '',
            "options": q.options or [],
            "answer": q.correct_answer or '',
            "grading_points": q.grading_points or '',
            "kp_name": q.knowledge_point.name if q.knowledge_point else '',
            "kp_code": q.knowledge_point.code if q.knowledge_point else '',
            "difficulty_level": q.difficulty_level,
        }
