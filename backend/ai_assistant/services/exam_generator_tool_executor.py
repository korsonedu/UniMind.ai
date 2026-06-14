"""
出题 Agent 工具执行器。

继承 BaseToolExecutor，提供出题专用工具：
- search_knowledge: 搜索知识点或知识树（合并）
- quick_generate: Author 单步快速出题
- launch_arc_pipeline: 启动 ARC 精修管线
- check_pipeline_status: 查询管线进度
- get_workbench_stats: 题库统计
"""

import logging
from typing import Any, Dict, List

from ai_assistant.services.tool_executor import BaseToolExecutor

logger = logging.getLogger(__name__)


class ExamGeneratorToolExecutor(BaseToolExecutor):
    """出题 Agent 工具执行器。"""

    def __init__(self, user, institution=None):
        super().__init__(user, institution)
        self._last_generated: List[Dict[str, Any]] = []
        self._last_pipeline_task_id: int | None = None

    # ── 搜索知识点（合并） ────────────────────────────────────

    def _handle_search_knowledge(self, args: Dict) -> Dict:
        from django.db.models import Q
        from quizzes.models import KnowledgePoint

        query = (args.get('query') or '').strip()
        subject = (args.get('subject') or '').strip()
        mode = args.get('mode', 'auto')

        result = {}

        # 机构隔离：机构有自己知识树的学科，只返回机构数据；没有的才 fallback 到全局
        inst_subject_set = set()
        if self.institution:
            inst_subjects = list(
                KnowledgePoint.objects.filter(
                    institution=self.institution, level='kp',
                ).values_list('subject', flat=True).distinct()
            )
            inst_subject_set = {s for s in inst_subjects if s}
            result["institution_subjects"] = sorted(inst_subject_set)

        def _apply_institution_filter(qs, subj=''):
            """机构有知识树 → 只看机构数据；没有 → fallback 全局。"""
            if not self.institution:
                return qs
            if inst_subject_set:
                # 机构有自己的知识树，只搜机构数据
                return qs.filter(institution=self.institution)
            # 机构没有知识树，fallback 到全局
            return qs.filter(institution__isnull=True)

        # mode=kp 或 auto：搜知识点
        if mode in ('kp', 'auto'):
            qs = KnowledgePoint.objects.filter(name__icontains=query, level='kp')
            if subject:
                qs = qs.filter(subject=subject)
            qs = _apply_institution_filter(qs, subject)

            kps = list(qs.values('id', 'code', 'name', 'subject', 'description')[:15])
            result = {
                "found": len(kps),
                "results": [
                    {
                        "id": kp['id'],
                        "code": kp['code'] or '',
                        "name": kp['name'],
                        "subject": kp['subject'] or '',
                        "description": (kp['description'] or '')[:200],
                    }
                    for kp in kps
                ],
            }

            if kps:
                return result

        # mode=tree 或 auto（kp 无结果时）：搜知识树
        if mode in ('tree', 'auto'):
            tree_qs = KnowledgePoint.objects.filter(
                name__icontains=query,
                level__in=['sub', 'ch', 'sec'],
            )
            if subject:
                tree_qs = tree_qs.filter(subject=subject)
            tree_qs = _apply_institution_filter(tree_qs, subject)

            tree_nodes = list(tree_qs.select_related('parent').values(
                'id', 'code', 'name', 'level', 'subject', 'parent__name',
            )[:8])

            if tree_nodes:
                for node in tree_nodes:
                    child_count = KnowledgePoint.objects.filter(parent_id=node['id']).count()
                    node['child_count'] = child_count
                result["tree_matches"] = [
                    {
                        "id": n['id'],
                        "code": n['code'] or '',
                        "name": n['name'],
                        "level": n['level'],
                        "subject": n['subject'] or '',
                        "parent": n['parent__name'] or '',
                        "child_count": n['child_count'],
                    }
                    for n in tree_nodes
                ]
                result["hint"] = "在知识树结构中找到匹配的模块/章节。可以用这些节点名称重新搜索知识点。"
                return result

        # 全无结果：提供引导
        if inst_subject_set:
            result["available_subjects"] = sorted(inst_subject_set)
            sample_kps = list(
                KnowledgePoint.objects.filter(
                    institution=self.institution, level='kp',
                ).order_by('?').values_list('name', flat=True)[:8]
            )
        else:
            base_qs = KnowledgePoint.objects.filter(level='kp', institution__isnull=True)
            subjects = list(base_qs.values_list('subject', flat=True).distinct()[:10])
            result["available_subjects"] = [s for s in subjects if s]
            sample_kps = list(base_qs.order_by('?').values_list('name', flat=True)[:8])
        result["sample_keywords"] = sample_kps
        result["hint"] = "搜索无结果。可用学科和知识点示例见上方，换关键词重试。"
        return result

    # ── 快速出题（Author 单步） ────────────────────────────────

    def _handle_quick_generate(self, args: Dict) -> Dict:
        from quizzes.services.single_generate_pipeline import run_single_generate_pipeline

        kp_ids = args.get('kp_ids', [])
        if not kp_ids:
            return {"error": "请提供至少一个知识点 ID"}

        count = int(args.get('count', 5))
        count_per_kp = max(1, count // len(kp_ids))
        difficulty = str(args.get('difficulty', 'normal')).strip()
        if difficulty not in ('entry', 'easy', 'normal', 'hard', 'extreme'):
            difficulty = 'normal'

        _on_step = self.on_step
        _call_id = getattr(self, '_current_call_id', 'quick_generate')

        def _on_progress(completed: int, total: int, batch_count: int):
            if _on_step:
                try:
                    display_count = min(batch_count, count)
                    _on_step({
                        "type": "step",
                        "call_id": _call_id,
                        "step": 0,
                        "status": "calling",
                        "name": "quick_generate",
                        "label": f"正在生成第 {completed}/{total} 批（已出 {display_count} 题）",
                    })
                except Exception:
                    pass

        try:
            result = run_single_generate_pipeline(
                kp_ids=kp_ids,
                count_per_kp=count_per_kp,
                target_difficulty=difficulty,
                institution=self.institution,
                on_progress=_on_progress,
                skip_review=True,
            )
            questions = result.get('questions', [])
        except Exception as e:
            logger.warning("quick_generate 失败: %s", e)
            return {"error": f"出题失败：{e}。请直接告知用户具体失败原因，不要再尝试生成。"}

        if not questions:
            return {"error": "题目生成失败。请直接告知用户，不要再尝试重复生成。"}

        # 截取到目标数量
        questions = questions[:count]
        self._last_generated = questions

        return {
            "count": len(questions),
            "questions": [
                {
                    "index": i,
                    "question": q.get('question', '')[:300],
                    "q_type": q.get('q_type', ''),
                    "difficulty_level": q.get('difficulty_level', 'normal'),
                    "kp_name": q.get('kp_name', ''),
                    "answer_preview": (q.get('answer', '') or '')[:100],
                }
                for i, q in enumerate(questions)
            ],
        }

    # ── ARC 管线 ────────────────────────────────────────────

    def _handle_launch_arc_pipeline(self, args: Dict) -> Dict:
        from quizzes.services.adversarial_pipeline import run_adversarial_pipeline

        kp_ids = args.get('kp_ids', [])
        if not kp_ids:
            return {"error": "请提供至少一个知识点 ID"}

        questions_per_kp = int(args.get('questions_per_kp', 3))
        difficulty = args.get('difficulty', 'normal')
        types = args.get('types')
        title = args.get('title', '')

        try:
            task_id = run_adversarial_pipeline(
                kp_ids=kp_ids,
                created_by=self.user,
                task_title=title,
                questions_per_kp=questions_per_kp,
                difficulty=difficulty,
                types=types,
                institution=self.institution,
            )
        except Exception as e:
            return {"error": str(e)}

        self._last_pipeline_task_id = task_id
        return {
            "task_id": task_id,
            "message": f"ARC 管线已启动（任务 #{task_id}），预计 2-5 分钟完成。你可以稍后问我进度。",
        }

    # ── 查询管线状态 ────────────────────────────────────────

    def _handle_check_pipeline_status(self, args: Dict) -> Dict:
        from quizzes.models import ContentPipelineTask

        task_id = int(args.get('task_id', 0))
        try:
            task = ContentPipelineTask.objects.get(id=task_id)
        except ContentPipelineTask.DoesNotExist:
            return {"error": f"任务 #{task_id} 不存在"}

        if not self.user.is_superuser and self.institution:
            if task.created_by and getattr(task.created_by, 'institution', None) != self.institution:
                return {"error": "无权查看该任务"}

        return {
            "task_id": task.id,
            "status": task.status,
            "progress": task.progress,
            "title": task.title,
            "current_stage": task.payload.get('current_stage', ''),
            "status_text": task.payload.get('status_text', ''),
        }

    # ── 题库统计 ────────────────────────────────────────────

    def _handle_get_workbench_stats(self, args: Dict) -> Dict:
        from django.db.models import Count
        from quizzes.models import Question

        scope = args.get('scope', 'summary')
        base_qs = Question.objects.all()
        if self.institution:
            base_qs = base_qs.filter(institution=self.institution)

        if scope == 'summary':
            total = base_qs.count()
            by_subject = list(
                base_qs.values('knowledge_point__subject')
                .annotate(count=Count('id'))
                .order_by('-count')[:10]
            )
            by_difficulty = list(
                base_qs.values('difficulty_level')
                .annotate(count=Count('id'))
                .order_by('-count')
            )
            by_type = list(
                base_qs.values('q_type')
                .annotate(count=Count('id'))
                .order_by('-count')
            )
            return {
                "total": total,
                "by_subject": [
                    {"subject": s['knowledge_point__subject'] or '未分类', "count": s['count']}
                    for s in by_subject
                ],
                "by_difficulty": [
                    {"difficulty": d['difficulty_level'] or 'normal', "count": d['count']}
                    for d in by_difficulty
                ],
                "by_type": [
                    {"type": t['q_type'] or 'unknown', "count": t['count']}
                    for t in by_type
                ],
            }

        elif scope == 'recent':
            recent = base_qs.order_by('-created_at')[:20]
            return {
                "questions": [
                    {
                        "id": q.id,
                        "text": (q.text or '')[:100],
                        "q_type": q.q_type,
                        "difficulty": q.difficulty_level,
                        "subject": getattr(q.knowledge_point, 'subject', '') if q.knowledge_point else '',
                        "created_at": q.created_at.isoformat() if q.created_at else '',
                    }
                    for q in recent
                ]
            }

        elif scope == 'insights':
            # 从 mem0 获取教师偏好
            try:
                from ai_assistant.services.memory_service import build_memory_context
                memory_text, _ = build_memory_context(self.user, bot_type='exam_generator')
                return {"insights": memory_text or "暂无足够数据生成教师偏好分析。"}
            except Exception:
                return {"insights": "暂无足够数据生成教师偏好分析。"}

        return {"error": f"未知 scope: {scope}，支持 summary/recent/insights"}

    # ── 新增数据类工具 ────────────────────────────────────────

    def _handle_get_student_detail(self, args: Dict) -> Dict:
        """获取指定学生的详细学习数据（仅教师/机构主可用）。"""
        from django.db.models import Avg, Count, Q
        from quizzes.models import Question, UserQuestionStatus

        if not self.institution or getattr(self.user, 'institution_role', '') not in ('teacher', 'owner'):
            return {"error": "仅教师/机构主可使用此功能"}

        student_name = (args.get('name') or args.get('student_name') or '').strip()
        student_id = args.get('student_id')
        if not student_name and not student_id:
            return {"error": "请提供学生姓名或 ID"}

        from users.models import User as UserModel
        student = None
        if student_id:
            try:
                student = UserModel.objects.get(id=int(student_id), institution=self.institution)
            except UserModel.DoesNotExist:
                return {"error": f"未找到学生 ID={student_id}"}
        else:
            matches = UserModel.objects.filter(
                institution=self.institution, institution_role='student',
            ).filter(Q(nickname__icontains=student_name) | Q(username__icontains=student_name))
            if matches.count() == 1:
                student = matches.first()
            elif matches.count() > 1:
                return {"students": [{"id": s.id, "name": s.nickname or s.username}
                                      for s in matches[:10]], "hint": "多个学生匹配，请指定 student_id"}
            else:
                return {"error": f"未找到学生 '{student_name}'"}

        # 答题统计
        status_qs = UserQuestionStatus.objects.filter(user=student)
        total_attempted = status_qs.count()
        correct = status_qs.filter(status__in=('correct', 'mastered')).count()
        accuracy = round(correct / total_attempted * 100, 1) if total_attempted else 0

        # 按知识点薄弱点
        from collections import Counter
        kp_errors = Counter()
        for st in status_qs.filter(status='wrong'):
            if st.knowledge_point:
                kp_errors[st.knowledge_point.name] += 1

        weak_kps = sorted(kp_errors.items(), key=lambda x: -x[1])[:5]

        # 最近活跃
        from django.utils import timezone
        week_ago = timezone.now() - timezone.timedelta(days=7)
        weekly_active = status_qs.filter(updated_at__gte=week_ago).count()
        weekly_exams = (
            __import__('quizzes.models', fromlist=['ExamResult'])
            .ExamResult.objects.filter(user=student, created_at__gte=week_ago).count()
        )

        return {
            "student_id": student.id,
            "name": student.nickname or student.username,
            "elo": student.elo,
            "total_questions_attempted": total_attempted,
            "accuracy": accuracy,
            "weak_points": [{"kp": kp, "errors": cnt} for kp, cnt in weak_kps],
            "weekly_active_days": min(7, weekly_active),
            "weekly_exams": weekly_exams,
            "_actions": [
                {"label": "查看学员详情", "route": f"/institution/students?student={student.id}"},
            ],
        }

    def _handle_get_assignment_progress(self, args: Dict) -> Dict:
        """查询指定作业的提交/批改进度（仅教师/机构主可用）。"""
        from quizzes.models import Assignment, AssignmentSubmission

        if not self.institution or getattr(self.user, 'institution_role', '') not in ('teacher', 'owner'):
            return {"error": "仅教师/机构主可使用此功能"}

        assignment_id = args.get('assignment_id')
        if not assignment_id:
            return {"error": "请提供作业 ID"}

        try:
            assignment = Assignment.objects.get(id=int(assignment_id), institution=self.institution)
        except Assignment.DoesNotExist:
            return {"error": f"作业 #{assignment_id} 不存在"}

        submissions = AssignmentSubmission.objects.filter(assignment=assignment)
        submitted_count = submissions.count()
        graded_count = submissions.filter(score__isnull=False).count()

        # 统计目标班级的学生总数
        total_students = assignment.target_classes.aggregate(
            total=Count('students')
        )['total'] or assignment.target_classes.values('students').distinct().count()

        return {
            "assignment_id": assignment.id,
            "title": assignment.title,
            "status": assignment.status,
            "due_date": assignment.due_date.isoformat() if assignment.due_date else None,
            "total_students": total_students,
            "submitted": submitted_count,
            "unsubmitted": max(0, total_students - submitted_count),
            "graded": graded_count,
            "pending_grade": submitted_count - graded_count,
        }

    # ── 新增行动类工具 ────────────────────────────────────────

    def _handle_assign_practice(self, args: Dict) -> Dict:
        """创建作业并布置给学生（仅教师/机构主可用）。"""
        from quizzes.models import Assignment, AssignmentQuestion, Question
        from notifications.models import Notification
        from users.models import Class as ClassModel

        if not self.institution or getattr(self.user, 'institution_role', '') not in ('teacher', 'owner'):
            return {"error": "仅教师/机构主可使用此功能"}

        title = args.get('title', '课后练习')
        question_ids = args.get('question_ids', [])
        class_names = args.get('class_names', [])
        due_date_str = args.get('due_date', '')

        if not question_ids:
            return {"error": "请提供 question_ids 题目列表"}

        questions = list(Question.objects.filter(
            id__in=question_ids, institution=self.institution,
        ))
        if not questions:
            return {"error": "未找到有效题目"}

        classes = []
        if class_names:
            classes = list(ClassModel.objects.filter(
                institution=self.institution, name__in=class_names,
            ))
            if not classes:
                return {"error": f"未找到班级: {class_names}"}

        due_date = None
        if due_date_str:
            from django.utils import timezone
            try:
                from datetime import datetime
                due_date = datetime.fromisoformat(due_date_str)
            except (ValueError, TypeError):
                return {"error": f"日期格式无效: {due_date_str}，请使用 ISO 格式（如 2026-06-20）"}

        assignment = Assignment.objects.create(
            title=title,
            institution=self.institution,
            created_by=self.user,
            status='published',
            due_date=due_date,
        )
        if classes:
            assignment.target_classes.set(classes)

        for idx, q in enumerate(questions):
            AssignmentQuestion.objects.create(
                assignment=assignment, question=q, order=idx + 1, points=args.get('points_per_question', 1),
            )

        # 通知目标班级学生
        notified = 0
        due_info = f"，截止 {due_date.strftime('%m/%d %H:%M')}" if due_date else ""
        for cls in classes:
            for student in cls.students.all():
                Notification.objects.create(
                    recipient=student,
                    title=f"新作业：{title}",
                    content=f"{self.user.nickname or self.user.username} 老师布置了作业「{title}」{due_info}",
                    n_type='system',
                    link='/tests',
                )
                notified += 1

        return {
            "assignment_id": assignment.id,
            "title": assignment.title,
            "question_count": len(questions),
            "class_count": len(classes),
            "class_names": [c.name for c in classes],
            "due_date": due_date.isoformat() if due_date else None,
            "notified_students": notified,
            "message": f"已发布作业「{title}」（{len(questions)} 题），已通知 {notified} 名学生。",
            "_actions": [
                {"label": "查看作业进度", "route": f"/institution/students"},
            ],
        }

    def _handle_send_notification(self, args: Dict) -> Dict:
        """向指定学生发送通知提醒（仅教师/机构主可用）。"""
        from notifications.models import Notification
        from users.models import User as UserModel

        if not self.institution or getattr(self.user, 'institution_role', '') not in ('teacher', 'owner'):
            return {"error": "仅教师/机构主可使用此功能"}

        student_name = args.get('student_name', '').strip()
        student_id = args.get('student_id')
        title = args.get('title', '学习提醒')
        content = args.get('content', '')

        if not content:
            return {"error": "请提供通知内容"}

        students = []
        if student_id:
            try:
                s = UserModel.objects.get(id=int(student_id), institution=self.institution)
                students = [s]
            except UserModel.DoesNotExist:
                return {"error": f"未找到学生 ID={student_id}"}
        elif student_name:
            students = list(UserModel.objects.filter(
                institution=self.institution, institution_role='student',
                nickname__icontains=student_name,
            )[:1])
            if not students:
                students = list(UserModel.objects.filter(
                    institution=self.institution, institution_role='student',
                    username__icontains=student_name,
                )[:1])

        if not students:
            return {"error": "未找到匹配的学生"}

        created = 0
        for s in students:
            Notification.objects.create(
                recipient=s, title=title, content=content,
                n_type='system', link='/xiaoyu',
            )
            created += 1

        return {"sent_to": [s.nickname or s.username for s in students],
                "count": created, "message": f"已向 {created} 名学生发送通知"}

    # ── 新增内容浏览类工具 ────────────────────────────────────

    def _handle_list_courses(self, args: Dict) -> Dict:
        """浏览课程库（教师视角，仅看到本机构课程）。"""
        from courses.models import Course

        subject = (args.get('subject') or '').strip()
        query = (args.get('query') or '').strip()
        limit = min(int(args.get('limit', 10)), 20)

        qs = Course.objects.all()
        if self.institution:
            qs = qs.filter(institution=self.institution)

        if subject:
            qs = qs.filter(knowledge_point__subject=subject)
        if query:
            from django.db.models import Q as _list_courses_Q
            qs = qs.filter(
                _list_courses_Q(title__icontains=query) |
                _list_courses_Q(description__icontains=query)
            )

        courses = qs.order_by('-created_at')[:limit]

        return {
            "total": qs.count(),
            "courses": [
                {"id": c.id, "title": c.title,
                 "description": (c.description or '')[:150],
                 "subject": c.knowledge_point.subject if c.knowledge_point else '',
                 "url": f"/course/{c.id}"}
                for c in courses
            ],
            "_actions": [
                {"label": f"查看全部 {qs.count()} 门课程", "route": "/courses"},
            ],
        }

    def _handle_list_questions(self, args: Dict) -> Dict:
        """浏览题库（教师视角，仅看到本机构题目）。"""
        from quizzes.models import Question

        kp_name = (args.get('kp_name') or '').strip()
        subject = (args.get('subject') or '').strip()
        q_type = (args.get('q_type') or '').strip()
        difficulty = (args.get('difficulty') or '').strip()
        limit = min(int(args.get('limit', 20)), 50)

        qs = Question.objects.all()
        if self.institution:
            qs = qs.filter(institution=self.institution)

        if kp_name:
            qs = qs.filter(knowledge_point__name__icontains=kp_name)
        if subject:
            qs = qs.filter(knowledge_point__subject=subject)
        if q_type:
            qs = qs.filter(q_type=q_type)
        if difficulty:
            qs = qs.filter(difficulty_level=difficulty)

        questions = qs.order_by('-created_at')[:limit]

        return {
            "total": qs.count(),
            "questions": [
                {"id": q.id, "text": (q.text or '')[:200],
                 "q_type": q.q_type, "difficulty": q.difficulty_level,
                 "kp_name": q.knowledge_point.name if q.knowledge_point else '',
                 "subject": q.knowledge_point.subject if q.knowledge_point else ''}
                for q in questions
            ],
            "_actions": [
                {"label": f"查看全部 {qs.count()} 道题", "route": "/questions"},
            ],
        }

    def _handle_list_articles(self, args: Dict) -> Dict:
        """浏览文章库（教师视角，仅看到本机构文章）。"""
        from articles.models import Article

        query = (args.get('query') or '').strip()
        limit = min(int(args.get('limit', 10)), 20)

        qs = Article.objects.all()
        if self.institution:
            qs = qs.filter(institution=self.institution)
        if query:
            from django.db.models import Q as _list_articles_Q
            qs = qs.filter(
                _list_articles_Q(title__icontains=query) |
                _list_articles_Q(content__icontains=query)
            )

        articles = qs.order_by('-created_at')[:limit]

        return {
            "total": qs.count(),
            "articles": [
                {"id": a.id, "title": a.title,
                 "author": a.author_display_name or (a.author.nickname if a.author else ''),
                 "tags": a.tags or [], "url": f"/article/{a.id}"}
                for a in articles
            ],
        }
