"""
Agent 工具执行器。

每个工具方法返回 JSON 字符串，供模型在多轮工具调用中消费。
"""

import json
import logging
from datetime import timedelta
from typing import Any, Dict, List
from django.db import models

logger = logging.getLogger(__name__)


def generate_step_label(tool_name: str, args: dict) -> str:
    """根据 tool name 和 args 动态生成中文步骤描述。"""
    labels = {
        'search_knowledge_tree': lambda a: f"检索「{a.get('query', '')}」相关知识点",
        'get_user_weak_points': lambda a: "分析你的薄弱知识点",
        'get_user_wrong_questions': lambda a: f"查看{a.get('topic', '')}错题" if a.get('topic') else "查看你的错题记录",
        'get_class_weak_points': lambda a: "分析班级薄弱知识点",
        'get_class_performance_summary': lambda a: "获取班级表现概览",
        'lookup_question': lambda a: f"查找题目（ID: {a.get('question_id', '')}）",
        'get_learning_stats': lambda a: "获取学习统计数据",
        'get_knowledge_mastery_map': lambda a: f"生成{a.get('subject', '')}知识掌握图谱" if a.get('subject') else "生成知识掌握图谱",
        'get_due_reviews': lambda a: "查询到期待复习的题目",
        'get_exam_history': lambda a: "查询考试历史",
        'save_study_plan': lambda a: "保存学习计划",
        'get_active_plan': lambda a: "获取当前学习计划",
        'update_plan_task': lambda a: f"更新计划任务「{a.get('task_id', '')}」",
        'search_courses': lambda a: f"搜索课程「{a.get('query', '')}」",
        'search_asr': lambda a: f"搜索视频字幕「{a.get('query', '')}」",
        'search_articles': lambda a: f"搜索文章「{a.get('query', '')}」",
        'search_knowledge': lambda a: f"搜索知识点「{a.get('query', '')}」",
        'get_practice_questions': lambda a: f"抽取{a.get('kp_name', '')}相关练习题" if a.get('kp_name') else "抽取练习题",
        'grade_student_answer': lambda a: f"批改题目 #{a.get('question_id', '')}",
        'quick_generate': lambda a: f"快速生成{a.get('count', 5)}道题",
        'render_visual': lambda a: f"渲染{a.get('type', '可视化')}",
        'launch_arc_pipeline': lambda a: "启动 ARC 精修管线",
        'check_pipeline_status': lambda a: "检查管线执行进度",
        'get_workbench_stats': lambda a: "获取题库统计",
    }
    generator = labels.get(tool_name)
    if generator:
        try:
            return generator(args)
        except Exception:
            pass
    return f"执行 {tool_name}"


def summarize_tool_result(tool_name: str, result) -> str:
    """将工具结果转为人类可读摘要（用于前端步骤卡片展示）。"""
    import json as _json
    if isinstance(result, str):
        try:
            result = _json.loads(result)
        except Exception:
            return result[:200]

    if not isinstance(result, dict):
        return str(result)[:200]

    summaries = {
        'search_knowledge_tree': lambda r: f"找到 {r.get('found', 0)} 个知识点",
        'get_user_weak_points': lambda r: f"发现 {len(r.get('weak_points', []))} 个薄弱点",
        'get_learning_stats': lambda r: f"正确率 {r.get('accuracy', 0)}%，已练 {r.get('total_questions_attempted', 0)} 题",
        'get_knowledge_mastery_map': lambda r: f"覆盖 {len(r.get('mastery_map', {}))} 个学科",
        'get_due_reviews': lambda r: f"{r.get('due_count', 0)} 个待复习",
        'get_exam_history': lambda r: f"共 {len(r.get('exams', []))} 次考试",
        'get_active_plan': lambda r: (
            f"「{r.get('title', '')}」进度 {r.get('progress_pct', 0):.0f}%"
            if r.get('has_active_plan') else "无活跃计划"
        ),
        'save_study_plan': lambda r: f"已保存「{r.get('title', '')}」共 {r.get('task_count', 0)} 个任务",
        'search_courses': lambda r: f"找到 {len(r.get('courses', []))} 门课程",
        'search_articles': lambda r: f"找到 {len(r.get('articles', []))} 篇文章",
        'quick_generate': lambda r: f"生成 {r.get('count', len(r.get('questions', [])))} 道题",
        'render_visual': lambda r: f"渲染可视化: {r.get('type', '')}",
        'get_user_wrong_questions': lambda r: f"找到 {r.get('total_found', 0)} 道错题",
        'search_asr': lambda r: f"找到 {r.get('total_found', 0)} 个视频片段",
        'get_practice_questions': lambda r: f"抽取 {len(r.get('questions', []))} 道练习题",
        'grade_student_answer': lambda r: f"得分 {r.get('score', 0)}/{r.get('max_score', 0)}",
        'update_plan_task': lambda r: f"任务已更新为 {r.get('new_status', 'unknown')}",
    }

    fn = summaries.get(tool_name)
    if fn:
        try:
            return fn(result)
        except Exception:
            pass

    # Fallback: pick first meaningful value
    for key in ('found', 'count', 'total', 'due_count', 'accuracy'):
        if key in result:
            return f"{key}: {result[key]}"
    return str(result)[:150]


class BaseToolExecutor:
    """基础工具执行器。将 tool_name 映射到实际数据库查询，捕获 user 和 institution 上下文。"""

    def __init__(self, user, institution=None):
        self.user = user
        self._allowed_tool_names = None
        self.institution = institution or getattr(user, 'institution', None)
        self.on_step = None  # 由 views 注入，用于工具内部发进度事件

    def __call__(self, tool_name: str, args: Dict[str, Any]) -> str:
        # 工具白名单校验：防止 LLM 被注入后调用非预期工具
        allowed = getattr(self, '_allowed_tool_names', None)
        if allowed is not None and tool_name not in allowed:
            return json.dumps({"error": f"Tool not allowed: {tool_name}"}, ensure_ascii=False)

        handler = getattr(self, f'_handle_{tool_name}', None)
        if handler is None:
            return json.dumps({"error": f"Unknown tool: {tool_name}"}, ensure_ascii=False)
        try:
            result = handler(args)
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    def _get_user_subjects(self):
        """Return list of subjects the user has questions for."""
        from quizzes.models import UserQuestionStatus
        return list(
            UserQuestionStatus.objects.filter(user=self.user)
            .values_list('question__knowledge_point__subject', flat=True)
            .distinct()
        )

    # ── Tool handlers ──────────────────────────────────────────

    def _handle_search_knowledge_tree(self, args: Dict) -> Dict:
        from django.db.models import Q
        from quizzes.models import KnowledgePoint

        query = (args.get('query') or '').strip()
        subject = (args.get('subject') or '').strip()

        qs = KnowledgePoint.objects.filter(
            Q(name__icontains=query) | Q(description__icontains=query),
        )
        if subject:
            qs = qs.filter(subject=subject)
        else:
            user_subjects = self._get_user_subjects()
            if user_subjects:
                qs = qs.filter(Q(subject__in=user_subjects) | Q(subject__isnull=True))
        if self.institution:
            qs = qs.filter(Q(institution=self.institution) | Q(institution__isnull=True))

        nodes = list(qs.select_related('parent').values(
            'id', 'code', 'name', 'level', 'subject', 'parent__name',
        )[:15])

        from django.db.models import Count
        node_ids = [n['id'] for n in nodes]
        child_counts = dict(
            KnowledgePoint.objects.filter(parent_id__in=node_ids)
            .values_list('parent_id')
            .annotate(cnt=Count('id'))
            .values_list('parent_id', 'cnt')
        )
        for node in nodes:
            node['child_count'] = child_counts.get(node['id'], 0)

        return {
            "found": len(nodes),
            "results": [
                {
                    "id": n['id'],
                    "code": n['code'] or '',
                    "name": n['name'],
                    "level": n['level'],
                    "subject": n['subject'] or '',
                    "parent": n['parent__name'] or '',
                    "child_count": n['child_count'],
                }
                for n in nodes
            ],
        }

    def _handle_get_user_weak_points(self, args: Dict) -> Dict:
        from django.db.models import Sum
        from quizzes.models import UserQuestionStatus

        qs = UserQuestionStatus.objects.filter(user=self.user, wrong_count__gt=0)
        if self.institution:
            qs = qs.filter(
                models.Q(question__institution=self.institution) |
                models.Q(question__institution__isnull=True)
            )

        aggregated = (
            qs.values('question__knowledge_point__name', 'question__knowledge_point__code')
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
        qs = UserQuestionStatus.objects.filter(user=self.user, wrong_count__gt=0)
        if self.institution:
            qs = qs.filter(
                models.Q(question__institution=self.institution) |
                models.Q(question__institution__isnull=True)
            )
        wrong_qs = qs.select_related('question__knowledge_point').order_by('-wrong_count')[:limit]

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

    def _handle_get_class_weak_points(self, args: Dict) -> Dict:
        """获取班级最薄弱的知识点（仅 teacher/owner 可用）。"""
        if not self.institution or getattr(self.user, 'institution_role', '') not in ('teacher', 'owner'):
            return {"error": "仅教师/机构主可使用班级分析功能"}

        from django.db.models import Sum, Count
        from quizzes.models import UserQuestionStatus

        limit = min(int(args.get('limit', 5)), 10)
        student_ids = list(
            self.institution.students.filter(institution_role='student').values_list('id', flat=True)
        )
        if not student_ids:
            return {"weak_points": [], "message": "该机构暂无学生"}

        qs = (
            UserQuestionStatus.objects
            .filter(user_id__in=student_ids, question__knowledge_point__isnull=False)
            .values(
                'question__knowledge_point__id',
                'question__knowledge_point__name',
                'question__knowledge_point__code',
            )
            .annotate(
                total_reps=Sum('reps'),
                total_lapses=Sum('lapses'),
                student_count=Count('user_id', distinct=True),
            )
        )

        scored = []
        for row in qs:
            total = (row['total_reps'] or 0) + (row['total_lapses'] or 0)
            if total == 0:
                continue
            correct_rate = (row['total_reps'] or 0) / total
            scored.append({
                'kp_name': row['question__knowledge_point__name'] or '',
                'kp_code': row['question__knowledge_point__code'] or '',
                'correct_rate': round(correct_rate * 100, 1),
                'total_attempts': total,
                'student_count': row['student_count'] or 0,
            })

        scored.sort(key=lambda x: x['correct_rate'])
        return {"weak_points": scored[:limit]}

    def _handle_get_class_performance_summary(self, args: Dict) -> Dict:
        """获取班级整体学习数据概览（仅 teacher/owner 可用）。"""
        if not self.institution or getattr(self.user, 'institution_role', '') not in ('teacher', 'owner'):
            return {"error": "仅教师/机构主可使用班级分析功能"}

        from django.db.models import Sum, Count
        from quizzes.models import UserQuestionStatus, ReviewLog

        student_ids = list(
            self.institution.students.filter(institution_role='student').values_list('id', flat=True)
        )
        if not student_ids:
            return {"summary": {}, "message": "该机构暂无学生"}

        from django.utils import timezone
        week_ago = timezone.now() - timedelta(days=7)

        total_students = len(student_ids)
        total_statuses = UserQuestionStatus.objects.filter(user_id__in=student_ids)
        total_questions = total_statuses.count()
        agg = total_statuses.aggregate(t_reps=Sum('reps'), t_lapses=Sum('lapses'))
        total_reps = agg['t_reps'] or 0
        total_lapses = agg['t_lapses'] or 0
        total_attempts = total_reps + total_lapses
        overall_rate = round(total_reps / total_attempts * 100, 1) if total_attempts > 0 else 0

        weekly_active = ReviewLog.objects.filter(
            user_id__in=student_ids, review_time__gte=week_ago,
        ).values('user_id').distinct().count()

        # KP count with weak performance (correct_rate < 60%)
        kp_agg = (
            total_statuses
            .filter(question__knowledge_point__isnull=False)
            .values('question__knowledge_point__id')
            .annotate(t_reps=Sum('reps'), t_lapses=Sum('lapses'))
        )
        weak_kp_count = 0
        for row in kp_agg:
            t = (row['t_reps'] or 0) + (row['t_lapses'] or 0)
            if t > 0 and (row['t_reps'] or 0) / t < 0.6:
                weak_kp_count += 1

        return {
            "summary": {
                "total_students": total_students,
                "weekly_active_students": weekly_active,
                "total_questions_tracked": total_questions,
                "total_attempts": total_attempts,
                "overall_correct_rate": overall_rate,
                "weak_kp_count": weak_kp_count,
            }
        }

    def _handle_lookup_question(self, args: Dict) -> Dict:
        from django.db.models import Q
        from quizzes.models import Question

        qid = int(args.get('question_id', 0))
        qs = Question.objects.select_related('knowledge_point')
        if self.institution:
            qs = qs.filter(Q(institution=self.institution) | Q(institution__isnull=True))
        try:
            q = qs.get(id=qid)
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


class PlannerToolExecutor(BaseToolExecutor):
    """扩展基础工具执行器，增加规划相关工具。继承全部基础工具。"""

    def __init__(self, user, institution=None):
        super().__init__(user, institution)
        self.pending_visuals = []  # Collect all render_visual outputs

    def _handle_get_learning_stats(self, args: Dict) -> Dict:
        from django.utils import timezone
        from quizzes.models import UserQuestionStatus, ReviewLog
        from datetime import timedelta

        now = timezone.now()
        uqs = UserQuestionStatus.objects.filter(user=self.user)
        total_questions = uqs.count()
        # NOTE: 真正的答题正确率需要 correct_reps/lapse_reps 字段，
        # 当前 UserQuestionStatus 只有 reps/lapses，无法精确计算。
        # 此处用 last_correct 占比近似"至少答对过一次的题目占比"。
        total_correct = uqs.filter(last_correct=True).count()
        total_wrong = uqs.filter(wrong_count__gt=0).count()

        # Study streak: consecutive days with review activity in last 30 days
        review_days = (
            ReviewLog.objects.filter(user=self.user, review_time__gte=now - timedelta(days=30))
            .values_list('review_time__date', flat=True)
            .distinct()
        )
        sorted_days = sorted(set(review_days), reverse=True)
        streak = 0
        if sorted_days:
            check_date = sorted_days[0]
            for d in sorted_days:
                if d == check_date:
                    streak += 1
                    check_date -= timedelta(days=1)
                elif d < check_date:
                    break

        # Subject coverage
        subjects_with_progress = (
            uqs.values('question__knowledge_point__subject')
            .distinct()
            .count()
        )

        return {
            "total_questions_attempted": total_questions,
            "correct_count": total_correct,
            "accuracy": round(total_correct / total_questions * 100, 1) if total_questions else 0,
            "wrong_count": total_wrong,
            "study_streak_days": streak,
            "subjects_with_progress": subjects_with_progress,
            "is_new_user": total_questions == 0,
            "suggested_action": "diagnostic_test" if total_questions == 0 else None,
            "diagnostic_url": "/tests" if total_questions == 0 else None,
        }

    def _handle_get_knowledge_mastery_map(self, args: Dict) -> Dict:
        from quizzes.models import UserKnowledgeState

        qs = UserKnowledgeState.objects.filter(user=self.user).select_related('knowledge_point')
        if self.institution:
            qs = qs.filter(
                models.Q(knowledge_point__institution=self.institution) |
                models.Q(knowledge_point__institution__isnull=True)
            )
        subject_filter = (args.get('subject') or '').strip()
        if subject_filter:
            qs = qs.filter(knowledge_point__subject=subject_filter)

        result = {}
        for uks in qs:
            kp = uks.knowledge_point
            subj = kp.subject or '未分类'
            if subj not in result:
                result[subj] = []
            result[subj].append({
                "kp_id": kp.id,
                "kp_code": kp.code or '',
                "kp_name": kp.name,
                "mastery_score": round(uks.mastery_score, 2),
            })

        for subj in result:
            result[subj].sort(key=lambda x: x['mastery_score'])

        return {"mastery_map": result}

    def _handle_get_due_reviews(self, args: Dict) -> Dict:
        from django.utils import timezone
        from quizzes.models import UserQuestionStatus

        limit = min(int(args.get('limit', 20)), 50)
        now = timezone.now()
        due_qs = UserQuestionStatus.objects.filter(user=self.user, next_review_at__lte=now)
        if self.institution:
            due_qs = due_qs.filter(
                models.Q(question__institution=self.institution) |
                models.Q(question__institution__isnull=True)
            )
        due_qs = due_qs.select_related('question__knowledge_point').order_by('next_review_at')
        due_count = due_qs.count()
        due_list = due_qs[:limit]

        def _calculate_memorix_priority(d):
            """基于 Memorix 数据计算复习优先级。"""
            if d.lapses >= 3:
                return "critical"  # 反复遗忘，需要重点关注
            if d.difficulty >= 7:
                return "high"  # 高难度
            if d.stability < 2:
                return "high"  # 稳定性低
            if d.stability < 7:
                return "medium"
            return "low"

        return {
            "due_count": due_count,
            "reviews": [
                {
                    "question_id": d.question_id,
                    "question_text": (d.question.text or '')[:200],
                    "kp_name": d.question.knowledge_point.name if d.question.knowledge_point else '',
                    "wrong_count": d.wrong_count,
                    "stability": round(d.stability, 2),
                    "difficulty": round(d.difficulty, 1),
                    "reps": d.reps,
                    "lapses": d.lapses,
                    "error_type": d.error_type or '',
                    "error_metadata": d.error_metadata or {},
                    "memorix_priority": _calculate_memorix_priority(d),
                    "next_review_at": d.next_review_at.isoformat() if d.next_review_at else None,
                }
                for d in due_list
            ],
        }

    def _handle_get_practice_questions(self, args: Dict) -> Dict:
        """根据知识点或薄弱点从题库中抽取题目供学生练习。

        参数:
            kp_name: 知识点名称（模糊匹配）
            subject: 学科过滤
            difficulty: 难度过滤（entry/easy/normal/hard/extreme）
            limit: 题目数量，默认 5，最大 10
            exclude_mastered: 是否排除已掌握题目，默认 true
        """
        from quizzes.models import Question, UserQuestionStatus

        kp_name = (args.get('kp_name') or '').strip()
        subject = (args.get('subject') or '').strip()
        difficulty = (args.get('difficulty') or '').strip()
        limit = min(int(args.get('limit', 5)), 10)
        exclude_mastered = args.get('exclude_mastered', True)

        qs = Question.objects.select_related('knowledge_point')

        # 机构隔离
        if self.institution:
            qs = qs.filter(
                models.Q(institution=self.institution) |
                models.Q(institution__isnull=True)
            )

        # 知识点过滤
        if kp_name:
            qs = qs.filter(knowledge_point__name__icontains=kp_name)
        if subject:
            qs = qs.filter(knowledge_point__subject=subject)

        # 难度过滤
        if difficulty:
            qs = qs.filter(difficulty_level=difficulty)

        # 排除已掌握的题目
        if exclude_mastered:
            mastered_ids = set(
                UserQuestionStatus.objects.filter(
                    user=self.user, is_mastered=True
                ).values_list('question_id', flat=True)
            )
            if mastered_ids:
                qs = qs.exclude(id__in=mastered_ids)

        # 优先选薄弱题目（做错过的），然后补充新题
        wrong_qids = set(
            UserQuestionStatus.objects.filter(
                user=self.user, wrong_count__gt=0
            ).values_list('question_id', flat=True)
        )

        # 先选做错过的题目
        wrong_qs = qs.filter(id__in=wrong_qids).order_by('?')[:limit]
        wrong_list = list(wrong_qs)

        remaining = limit - len(wrong_list)
        new_list = []
        if remaining > 0:
            wrong_ids = {q.id for q in wrong_list}
            new_qs = qs.exclude(id__in=wrong_ids | wrong_qids).order_by('?')[:remaining]
            new_list = list(new_qs)

        all_questions = wrong_list + new_list

        return {
            "total_found": qs.count(),
            "questions": [
                {
                    "id": q.id,
                    "text": (q.text or '')[:500],
                    "q_type": q.q_type,
                    "subjective_type": q.subjective_type or '',
                    "options": q.options or [],
                    "difficulty_level": q.difficulty_level,
                    "kp_name": q.knowledge_point.name if q.knowledge_point else '',
                    "kp_code": q.knowledge_point.code if q.knowledge_point else '',
                    "is_review": q.id in wrong_qids,
                }
                for q in all_questions
            ],
            "practice_url": "/quiz/practice",
            "message": f"已从题库抽取 {len(all_questions)} 道题目" + (
                f"（{len(wrong_list)} 道错题复习 + {len(new_list)} 道新题）"
                if wrong_list and new_list else
                f"（{len(wrong_list)} 道错题复习）" if wrong_list else
                f"（{len(new_list)} 道新题）"
            ),
        }

    def _handle_get_exam_history(self, args: Dict) -> Dict:
        from quizzes.models import QuizExam

        limit = min(int(args.get('limit', 10)), 20)
        exams = QuizExam.objects.filter(user=self.user).order_by('-created_at')[:limit]
        return {
            "exams": [
                {
                    "id": e.id,
                    "total_score": e.total_score,
                    "max_score": e.max_score,
                    "percentage": round(e.total_score / e.max_score * 100, 1) if e.max_score else 0,
                    "elo_change": e.elo_change,
                    "created_at": e.created_at.isoformat(),
                }
                for e in exams
            ],
        }

    def _handle_save_study_plan(self, args: Dict) -> Dict:
        from ai_assistant.models import StudyPlan

        title = args.get('title', '学习计划')
        summary = args.get('summary', '')
        tasks = args.get('tasks', [])
        total_days = args.get('total_days', max((t.get('day', 1) for t in tasks), default=1))

        for i, task in enumerate(tasks):
            if 'id' not in task:
                task['id'] = f"task_{i + 1}"
            task.setdefault('status', 'pending')
            task.setdefault('completed_at', None)
            # 归一化 LLM 可能用错的字段名
            if 'task' in task and 'title' not in task:
                task['title'] = task.pop('task')
            task.setdefault('title', task.get('description', f'任务 {i + 1}'))
            task.setdefault('day', 1)
            task.setdefault('estimated_minutes', 0)
            task.setdefault('subject', '')
            task.setdefault('description', '')

        # Archive any existing active plan
        StudyPlan.objects.filter(user=self.user, status='active').update(status='archived')

        plan = StudyPlan.objects.create(
            user=self.user,
            title=title,
            summary=summary,
            plan_data={
                "tasks": tasks,
                "total_days": total_days,
                "subjects_covered": list({t.get('subject', '') for t in tasks if t.get('subject')}),
                "diagnostic_suggested": args.get('diagnostic_suggested', False),
            },
            auto_generated=True,
        )
        return {"plan_id": plan.id, "title": plan.title, "task_count": len(tasks), "status": "active"}

    def _handle_get_active_plan(self, args: Dict) -> Dict:
        from ai_assistant.models import StudyPlan

        plan = StudyPlan.objects.filter(user=self.user, status='active').first()
        if not plan:
            return {"has_active_plan": False, "message": "当前没有进行中的学习计划。"}
        data = plan.plan_data or {}
        tasks = data.get('tasks', [])
        completed = sum(1 for t in tasks if t.get('status') == 'completed')
        return {
            "has_active_plan": True,
            "plan_id": plan.id,
            "title": plan.title,
            "summary": plan.summary,
            "total_tasks": len(tasks),
            "completed_tasks": completed,
            "progress_pct": round(completed / len(tasks) * 100, 1) if tasks else 0,
            "tasks": tasks,
            "created_at": plan.created_at.isoformat(),
        }

    def _handle_update_plan_task(self, args: Dict) -> Dict:
        from ai_assistant.models import StudyPlan
        from django.utils import timezone

        plan_id = int(args.get('plan_id', 0))
        task_id = args.get('task_id', '')
        new_status = args.get('status', 'pending')
        if new_status not in ('pending', 'completed', 'skipped'):
            return {"error": f"无效的状态值: {new_status}，支持: pending, completed, skipped"}

        try:
            plan = StudyPlan.objects.get(id=plan_id, user=self.user)
        except StudyPlan.DoesNotExist:
            return {"error": f"Plan #{plan_id} not found"}

        data = plan.plan_data or {}
        tasks = data.get('tasks', [])
        updated = False
        for task in tasks:
            if task.get('id') == task_id:
                task['status'] = new_status
                task['completed_at'] = timezone.now().isoformat() if new_status == 'completed' else None
                updated = True
                break

        if not updated:
            return {"error": f"Task '{task_id}' not found in plan #{plan_id}"}

        all_done = all(t.get('status') in ('completed', 'skipped') for t in tasks)
        if all_done:
            plan.status = 'completed'
            plan.completed_at = timezone.now()

        plan.plan_data = data
        plan.save()

        completed = sum(1 for t in tasks if t.get('status') == 'completed')
        return {
            "plan_id": plan.id,
            "task_id": task_id,
            "new_status": new_status,
            "total_tasks": len(tasks),
            "completed_tasks": completed,
            "plan_status": plan.status,
        }

    def _handle_search_courses(self, args: Dict) -> Dict:
        """搜索课程库，推荐学习资源。"""
        from courses.models import Course

        query = (args.get('query') or '').strip()
        subject = (args.get('subject') or '').strip()
        limit = min(int(args.get('limit', 5)), 10)

        if not query:
            return {"courses": [], "message": "请提供搜索关键词"}

        qs = Course.objects.filter(
            models.Q(title__icontains=query) |
            models.Q(description__icontains=query) |
            models.Q(knowledge_point__name__icontains=query)
        ).select_related('knowledge_point', 'album_obj')

        # Institution isolation
        institution = getattr(self.user, 'institution', None)
        if institution:
            qs = qs.filter(
                models.Q(institution=institution) |
                models.Q(institution__isnull=True)
            )

        if subject:
            qs = qs.filter(knowledge_point__subject=subject)

        courses = qs.order_by('-created_at')[:limit]

        return {
            "courses": [
                {
                    "id": c.id,
                    "title": c.title,
                    "description": (c.description or '')[:200],
                    "kp_name": c.knowledge_point.name if c.knowledge_point else '',
                    "album": c.album_obj.name if c.album_obj else '',
                    "url": f"/course/{c.id}",
                }
                for c in courses
            ],
            "total_found": qs.count(),
        }

    def _handle_search_asr(self, args: Dict) -> Dict:
        """搜索 ASR 转录文本，找到知识点在视频中的时间位置。"""
        from courses.models import TranscriptSegment, VideoTranscript, Course

        query = (args.get('query') or '').strip()
        course_id = args.get('course_id')
        limit = min(int(args.get('limit', 5)), 10)

        if not query:
            return {"segments": [], "message": "请提供搜索关键词"}

        # Search in transcript segments
        qs = TranscriptSegment.objects.filter(
            text__icontains=query
        ).select_related('transcript__course')

        # Institution isolation
        institution = getattr(self.user, 'institution', None)
        if institution:
            qs = qs.filter(
                models.Q(transcript__course__institution=institution) |
                models.Q(transcript__course__institution__isnull=True)
            )

        # Filter by course if specified
        if course_id:
            qs = qs.filter(transcript__course_id=course_id)

        segments = qs[:limit]

        def format_time(seconds):
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins}:{secs:02d}"

        return {
            "segments": [
                {
                    "course_id": s.transcript.course_id,
                    "course_title": s.transcript.course.title,
                    "start_time": format_time(s.start_time),
                    "end_time": format_time(s.end_time),
                    "start_seconds": s.start_time,
                    "text": s.text[:200],
                    "url": f"/course/{s.transcript.course_id}",
                }
                for s in segments
            ],
            "total_found": qs.count(),
        }

    def _handle_search_articles(self, args: Dict) -> Dict:
        """搜索文章库，推荐扩展阅读。"""
        from articles.models import Article

        query = (args.get('query') or '').strip()
        limit = min(int(args.get('limit', 5)), 10)

        if not query:
            return {"articles": [], "message": "请提供搜索关键词"}

        qs = Article.objects.filter(
            models.Q(title__icontains=query) |
            models.Q(content__icontains=query) |
            models.Q(tags__contains=[query])
        ).select_related('knowledge_point', 'author')

        # Institution isolation
        institution = getattr(self.user, 'institution', None)
        if institution:
            qs = qs.filter(
                models.Q(institution=institution) |
                models.Q(institution__isnull=True)
            )

        articles = qs[:limit]

        return {
            "articles": [
                {
                    "id": a.id,
                    "title": a.title,
                    "kp_name": a.knowledge_point.name if a.knowledge_point else '',
                    "tags": a.tags or [],
                    "views": a.views,
                    "author": a.author_display_name or (a.author.nickname or a.author.username if a.author else ''),
                    "url": f"/article/{a.id}",
                }
                for a in articles
            ],
            "total_found": qs.count(),
        }

    def _handle_get_knowledge_difficulty_analysis(self, args: Dict) -> Dict:
        """获取知识点的 Memorix 难度分析。"""
        from quizzes.models import UserQuestionStatus

        subject = (args.get('subject') or '').strip()

        # 获取用户的复习状态
        qs = UserQuestionStatus.objects.filter(
            user=self.user,
            is_active=True
        ).select_related('question__knowledge_point')

        if self.institution:
            qs = qs.filter(
                models.Q(question__institution=self.institution) |
                models.Q(question__institution__isnull=True)
            )

        if subject:
            qs = qs.filter(question__knowledge_point__subject=subject)

        # 按知识点聚合
        kp_stats = {}
        for status in qs:
            kp = status.question.knowledge_point
            if not kp:
                continue
            kp_name = kp.name
            if kp_name not in kp_stats:
                kp_stats[kp_name] = {
                    "difficulties": [],
                    "stabilities": [],
                    "total_reviews": 0,
                    "lapse_counts": []
                }
            kp_stats[kp_name]["difficulties"].append(status.difficulty)
            kp_stats[kp_name]["stabilities"].append(status.stability)
            kp_stats[kp_name]["total_reviews"] += status.reps
            kp_stats[kp_name]["lapse_counts"].append(status.lapses)

        # 计算统计
        knowledge_points = []
        for kp_name, stats in kp_stats.items():
            avg_diff = sum(stats["difficulties"]) / len(stats["difficulties"])
            avg_stab = sum(stats["stabilities"]) / len(stats["stabilities"])
            total_lapses = sum(stats["lapse_counts"])

            # 判断掌握程度
            if avg_diff >= 7 or avg_stab < 2:
                mastery = "weak"
            elif avg_diff >= 5 or avg_stab < 5:
                mastery = "developing"
            else:
                mastery = "strong"

            # 生成 Memorix 洞察
            insight_parts = []
            if avg_diff >= 7:
                insight_parts.append(f"平均难度较高（{avg_diff:.1f}）")
            if avg_stab < 3:
                insight_parts.append(f"记忆稳定性低（{avg_stab:.1f}天）")
            if total_lapses >= 5:
                insight_parts.append(f"累计遗忘 {total_lapses} 次")

            if insight_parts:
                insight = f"该知识点{', '.join(insight_parts)}，建议增加复习频率并使用间隔重复策略"
            else:
                insight = "该知识点掌握情况良好"

            knowledge_points.append({
                "name": kp_name,
                "avg_difficulty": round(avg_diff, 1),
                "avg_stability": round(avg_stab, 1),
                "total_reviews": stats["total_reviews"],
                "mastery_level": mastery,
                "memorix_insight": insight
            })

        # 按难度排序
        knowledge_points.sort(key=lambda x: x["avg_difficulty"], reverse=True)

        weak_count = sum(1 for kp in knowledge_points if kp["mastery_level"] == "weak")

        return {
            "knowledge_points": knowledge_points,
            "summary": f"共 {len(knowledge_points)} 个知识点，其中 {weak_count} 个需要重点关注"
        }

    def _handle_grade_student_answer(self, args: Dict) -> Dict:
        """批改学生的回答。查找题目→调用判分服务→返回评分反馈。"""
        from quizzes.models import Question
        from ai_assistant.services.grading_engine import GradingEngine
        from ai_engine.ai_service import AIService

        question_id = int(args.get('question_id', 0))
        user_answer = str(args.get('user_answer', '')).strip()

        if not question_id:
            return {"error": "请提供 question_id"}
        if not user_answer:
            return {"error": "请提供学生的回答内容", "score": 0, "max_score": 0,
                    "feedback": "学生未作答", "is_correct": False}

        try:
            question = Question.objects.select_related('knowledge_point').get(id=question_id)
        except Question.DoesNotExist:
            return {"error": f"题目 #{question_id} 不存在"}

        ai = AIService()
        result = GradingEngine.grade(
            ai=ai,
            question_text=question.question,
            user_answer=user_answer,
            correct_answer=question.answer,
            q_type=question.q_type,
            max_score=10.0,
            grading_points=question.grading_points,
            options=question.options,
            subjective_type=question.subjective_type or '主观题',
        )

        error_analysis = result.get('error_analysis')
        if error_analysis and error_analysis.get('type'):
            try:
                from quizzes.models import UserQuestionStatus
                from django.utils import timezone
                uqs = UserQuestionStatus.objects.filter(
                    user=self.user, question_id=question_id
                ).first()
                if uqs:
                    uqs.error_type = error_analysis['type']
                    uqs.error_metadata = {
                        'reasoning': error_analysis.get('reasoning', ''),
                        'suggested_focus': error_analysis.get('suggested_focus', ''),
                        'graded_at': timezone.now().isoformat(),
                    }
                    uqs.save(update_fields=['error_type', 'error_metadata'])
            except Exception:
                pass

        # 写入 GradingRecord 历史记录
        try:
            from quizzes.models import GradingRecord
            GradingRecord.objects.create(
                user=self.user,
                question_id=question_id,
                score=result.get('score', 0),
                max_score=result.get('max_score', 10.0),
                is_correct=result.get('is_correct', False),
                error_type=result.get('error_analysis', {}).get('type', ''),
                error_metadata=result.get('error_analysis', {}),
                feedback=result.get('feedback', ''),
                analysis=result.get('analysis', ''),
            )
        except Exception:
            pass

        return {
            "question_id": question_id,
            "kp_name": question.knowledge_point.name if question.knowledge_point else '',
            "score": result.get('score', 0),
            "max_score": 10.0,
            "is_correct": result.get('score', 0) >= 10.0 * 0.6,
            "feedback": result.get('feedback', ''),
            "analysis": result.get('analysis', ''),
            "error_analysis": error_analysis,
        }

    def _handle_render_visual(self, args: Dict) -> Dict:
        """将可视化数据返回给前端，同时缓存到实例供消息持久化。"""
        visual_type = args.get('type', '')
        payload = args.get('payload', {})
        priority = args.get('priority', 'normal')
        # DeepSeek 有时把 payload 作为 JSON 字符串传入
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                payload = {}

        valid_types = {'data_card', 'latex_derivation', 'step_solution', 'knowledge_map', 'action_cards'}
        if visual_type not in valid_types:
            visual_type = 'data_card'

        visual = {"type": visual_type, "payload": payload, "priority": priority}
        self.pending_visuals.append(visual)
        return visual
