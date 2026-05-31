"""
Agent 工具执行器。

每个工具方法返回 JSON 字符串，供模型在多轮工具调用中消费。
"""

import json
from datetime import timedelta
from typing import Any, Dict, List
from django.db import models


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
        'get_due_reviews': lambda a: f"查询未来{a.get('days', 7)}天的复习任务",
        'get_exam_history': lambda a: "查询考试历史",
        'save_study_plan': lambda a: "保存学习计划",
        'get_active_plan': lambda a: "获取当前学习计划",
        'update_plan_task': lambda a: f"更新计划任务「{a.get('task_id', '')}」",
        'search_courses': lambda a: f"搜索课程「{a.get('query', '')}」",
        'search_asr': lambda a: f"搜索视频字幕「{a.get('query', '')}」",
        'search_articles': lambda a: f"搜索文章「{a.get('query', '')}」",
        'search_knowledge_points': lambda a: f"搜索知识点「{a.get('query', '')}」",
        'generate_questions': lambda a: f"基于{len(a.get('knowledge_point_ids', []))}个知识点生成{a.get('count', 5)}道题",
        'render_visual': lambda a: f"渲染{a.get('type', '可视化')}",
        'launch_arc_pipeline': lambda a: "启动题目审查（ARC 管线）",
        'check_pipeline_status': lambda a: "检查管线执行进度",
        'save_questions_to_library': lambda a: f"保存{len(a.get('question_ids', []))}道题到题库",
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
        'generate_questions': lambda r: f"生成 {len(r.get('questions', []))} 道题",
        'render_visual': lambda r: f"渲染可视化: {r.get('type', '')}",
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
            name__icontains=query,
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

        for node in nodes:
            node['child_count'] = KnowledgePoint.objects.filter(parent_id=node['id']).count()

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
        total_correct = uqs.filter(last_correct=True).count()
        total_wrong = uqs.filter(wrong_count__gt=0).count()

        # Study streak: consecutive days with review activity in last 30 days
        review_days = (
            ReviewLog.objects.filter(user=self.user, review_time__gte=now - timedelta(days=30))
            .values_list('review_time__date', flat=True)
            .distinct()
        )
        streak = 0
        check_date = now.date()
        for d in sorted(set(review_days), reverse=True):
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

        return {
            "due_count": due_count,
            "reviews": [
                {
                    "question_id": d.question_id,
                    "question_text": (d.question.text or '')[:200],
                    "kp_name": d.question.knowledge_point.name if d.question.knowledge_point else '',
                    "wrong_count": d.wrong_count,
                    "stability": round(d.stability, 2),
                    "next_review_at": d.next_review_at.isoformat() if d.next_review_at else None,
                }
                for d in due_list
            ],
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

        courses = qs[:limit]

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

    def _handle_render_visual(self, args: Dict) -> Dict:
        """将可视化数据返回给前端，同时缓存到实例供消息持久化。"""
        visual_type = args.get('type', '')
        payload = args.get('payload', {})
        # DeepSeek 有时把 payload 作为 JSON 字符串传入
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                payload = {}

        valid_types = {'data_card', 'latex_derivation', 'step_solution', 'knowledge_map', 'action_cards'}
        if visual_type not in valid_types:
            alias_map = {'table': 'data_card', 'chart': 'data_card', 'gauge': 'data_card',
                         'progress': 'data_card', 'radar': 'data_card'}
            visual_type = alias_map.get(visual_type, 'data_card')

        visual = {"type": visual_type, "payload": payload}
        self.pending_visuals.append(visual)
        return visual
