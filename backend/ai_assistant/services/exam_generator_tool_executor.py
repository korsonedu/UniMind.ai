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
from users.permissions import is_institution_teacher

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
                    "kp_id": q.get('kp_id'),
                    "answer_preview": (q.get('answer', '') or '')[:100],
                }
                for i, q in enumerate(questions)
            ],
        }

    def _handle_save_questions_to_bank(self, args: Dict) -> Dict:
        """将最近生成的题目存入题库并返回 ID 列表。"""
        from quizzes.models import Question

        if not self._last_generated:
            return {"error": "没有待入库的题目，请先生成题目"}

        saved = []
        for q in self._last_generated:
            kp_id = q.get('kp_id')
            try:
                obj = Question.objects.create(
                    text=q.get('question', ''),
                    q_type=q.get('q_type', 'objective'),
                    subjective_type=q.get('subjective_type') or None,
                    difficulty_level=q.get('difficulty_level', 'normal'),
                    correct_answer=q.get('answer', ''),
                    grading_points=q.get('grading_points') or None,
                    options=q.get('options') or None,
                    rubric=q.get('rubric') or None,
                    knowledge_point_id=kp_id,
                    institution=self.institution,
                )
                saved.append({
                    'id': obj.id,
                    'question': obj.text[:200],
                    'q_type': obj.q_type,
                    'kp_name': q.get('kp_name', ''),
                })
            except Exception as e:
                logger.warning("save_questions_to_bank: 保存题目失败: %s", e)

        if not saved:
            return {"error": "题目入库失败，请重试"}

        # 清空 _last_generated 防止重复入库
        self._last_generated = []

        return {
            "saved_count": len(saved),
            "question_ids": [s['id'] for s in saved],
            "questions": saved,
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

        if not self.institution or not is_institution_teacher(self.user):
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
        }

    def _handle_get_assignment_progress(self, args: Dict) -> Dict:
        """查询指定作业的提交/批改进度（仅教师/机构主可用）。"""
        from quizzes.models import Assignment, AssignmentSubmission

        if not self.institution or not is_institution_teacher(self.user):
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
        logger.info("assign_practice args: title=%r question_ids=%r class_names=%r due_date=%r inst=%s inst_role=%s",
                     args.get('title'), args.get('question_ids'), args.get('class_names'), args.get('due_date'),
                     self.institution.id if self.institution else None,
                     getattr(self.user, 'institution_role', ''))

        from quizzes.models import Assignment, AssignmentQuestion, Question
        from notifications.models import Notification
        from users.models import Class as ClassModel

        if not self.institution or not is_institution_teacher(self.user):
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
        logger.info("assign_practice questions filter: ids=%s found=%d", question_ids, len(questions))
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
                    ntype='system',
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
            "message": f"已发布作业「{title}」（{len(questions)} 题），已通知 {notified} 名学生。可在「作业管理」页面查看提交进度。",
        }

    def _handle_send_notification(self, args: Dict) -> Dict:
        """向指定学生发送通知提醒（仅教师/机构主可用）。"""
        from notifications.models import Notification
        from users.models import User as UserModel

        if not self.institution or not is_institution_teacher(self.user):
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
                ntype='system', link='/xiaoyu',
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

        # 随机模式：从结果集中随机选取
        random_mode = str(args.get('random', '')).lower() in ('true', '1', 'yes')
        if random_mode and questions:
            import random as _random
            questions = list(questions)
            _random.shuffle(questions)
            questions = questions[:limit]

        return {
            "total": qs.count(),
            "returned": len(questions),
            "random": random_mode,
            "questions": [
                {"id": q.id, "text": (q.text or '')[:200],
                 "q_type": q.q_type, "difficulty": q.difficulty_level,
                 "kp_name": q.knowledge_point.name if q.knowledge_point else '',
                 "subject": q.knowledge_point.subject if q.knowledge_point else ''}
                for q in questions
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

    # ── 班级/课程管理工具 ───────────────────────────────────────

    def _handle_list_classes(self, args: Dict) -> Dict:
        """获取机构下的所有班级列表。可按名称筛选。"""
        from users.models import Class as ClassModel

        if not self.institution:
            return {"error": "仅机构成员可使用此功能"}

        classes = ClassModel.objects.filter(institution=self.institution)
        name_filter = (args.get('name') or '').strip()
        if name_filter:
            classes = classes.filter(name__icontains=name_filter)
        result = []
        for cls in classes:
            result.append({
                "id": cls.id,
                "name": cls.name,
                "student_count": cls.students.count(),
            })
        return {
            "classes": result,
            "total": len(result),
        }

    def _handle_assign_class_course(self, args: Dict) -> Dict:
        """将课程分配给班级（仅教师/机构主可用）。"""
        from users.models import Class as ClassModel, ClassCourse
        from courses.models import Course

        if not self.institution or not is_institution_teacher(self.user):
            return {"error": "仅教师/机构主可使用此功能"}

        class_id = args.get('class_id')
        course_id = args.get('course_id')
        if not class_id or not course_id:
            return {"error": "请提供 class_id 和 course_id"}

        try:
            class_obj = ClassModel.objects.get(id=int(class_id), institution=self.institution)
        except ClassModel.DoesNotExist:
            return {"error": f"班级 #{class_id} 不存在"}

        try:
            course = Course.objects.get(id=int(course_id), institution=self.institution)
        except Course.DoesNotExist:
            return {"error": f"课程 #{course_id} 不存在"}

        try:
            cc = ClassCourse.objects.create(
                class_obj=class_obj,
                course=course,
                institution=self.institution,
            )
        except Exception:
            return {"error": f"课程「{course.title}」已分配给班级「{class_obj.name}」"}

        return {
            "id": cc.id,
            "class_id": class_obj.id,
            "class_name": class_obj.name,
            "course_id": course.id,
            "course_title": course.title,
            "message": f"已将课程「{course.title}」分配给班级「{class_obj.name}」",
        }

    def _handle_get_class_gradebook(self, args: Dict) -> Dict:
        """获取班级成绩册（仅教师/机构主可用）。"""
        from users.models import Class as ClassModel
        from quizzes.models import Assignment, AssignmentSubmission

        if not self.institution or not is_institution_teacher(self.user):
            return {"error": "仅教师/机构主可使用此功能"}

        class_id = args.get('class_id')
        if not class_id:
            return {"error": "请提供 class_id"}

        try:
            class_obj = ClassModel.objects.get(id=int(class_id), institution=self.institution)
        except ClassModel.DoesNotExist:
            return {"error": f"班级 #{class_id} 不存在"}

        students = class_obj.students.all()
        assignments = Assignment.objects.filter(
            target_classes=class_obj, institution=self.institution,
        ).order_by('-created_at')

        # 预计算每份作业的满分
        assignment_max_scores = {}
        for a in assignments:
            pts = list(a.assignment_questions.values_list('points', flat=True))
            assignment_max_scores[a.id] = sum(pts) or a.assignment_questions.count()

        # 批量查询所有提交记录，避免 M×N 次查询
        all_subs = AssignmentSubmission.objects.filter(
            student__in=students, assignment__in=assignments,
        )
        sub_map = {(s.student_id, s.assignment_id): s for s in all_subs}

        students_data = []
        for student in students:
            student_scores = []
            for assignment in assignments:
                sub = sub_map.get((student.id, assignment.id))
                max_score = assignment_max_scores[assignment.id]
                if sub:
                    student_scores.append({
                        "assignment_id": assignment.id,
                        "assignment_title": assignment.title,
                        "score": sub.score,
                        "max_score": max_score,
                        "submitted": True,
                        "graded": sub.score is not None,
                    })
                else:
                    student_scores.append({
                        "assignment_id": assignment.id,
                        "assignment_title": assignment.title,
                        "score": None,
                        "max_score": max_score,
                        "submitted": False,
                        "graded": False,
                    })
            students_data.append({
                "id": student.id,
                "name": student.nickname or student.username,
                "scores": student_scores,
            })

        return {
            "class_name": class_obj.name,
            "student_count": len(students_data),
            "assignment_count": assignments.count(),
            "students": students_data,
        }

    def _handle_grade_submissions(self, args: Dict) -> Dict:
        """批改学生作业提交（仅教师/机构主可用）。"""
        from quizzes.models import AssignmentSubmission
        from django.utils import timezone

        if not self.institution or not is_institution_teacher(self.user):
            return {"error": "仅教师/机构主可使用此功能"}

        submission_id = args.get('submission_id')
        score = args.get('score')
        feedback = (args.get('feedback') or '').strip()

        if not submission_id or score is None:
            return {"error": "请提供 submission_id 和 score"}

        try:
            submission = AssignmentSubmission.objects.select_related(
                'assignment__institution', 'student',
            ).get(id=int(submission_id))
        except AssignmentSubmission.DoesNotExist:
            return {"error": f"提交 #{submission_id} 不存在"}

        if submission.assignment.institution_id != self.institution.id:
            return {"error": "无权批改此提交"}

        submission.score = float(score)
        submission.graded_by = self.user
        submission.graded_at = timezone.now()
        submission.save(update_fields=['score', 'graded_by', 'graded_at'])

        return {
            "submission_id": submission.id,
            "assignment_id": submission.assignment_id,
            "student_name": submission.student.nickname or submission.student.username,
            "score": submission.score,
            "feedback": feedback or None,
            "graded_by": self.user.nickname or self.user.username,
            "graded_at": submission.graded_at.isoformat(),
        }

    # ── 教学计划 ──

    def _handle_create_teaching_plan(self, args: Dict) -> Dict:
        """创建或更新教学计划。"""
        from courses.models import TeachingPlan
        from users.models import Class

        class_id = int(args.get('class_id', 0))
        if not class_id:
            return {"error": "缺少 class_id"}

        class_obj = Class.objects.filter(id=class_id, institution=self.institution).first()
        if not class_obj:
            return {"error": "班级不存在或无权操作"}

        title = args.get('title', f'{class_obj.name}教学计划')
        subject = args.get('subject', '')
        semester = args.get('semester', '')
        week_count = int(args.get('week_count', 18))
        goal = args.get('goal', '')
        deadline = None
        if args.get('deadline'):
            from django.utils.dateparse import parse_date
            deadline = parse_date(args['deadline'])
        target_score = args.get('target_score')
        current_level = args.get('current_level', '')

        plan, created = TeachingPlan.objects.update_or_create(
            class_obj=class_obj,
            subject=subject,
            semester=semester,
            defaults={
                'institution': self.institution,
                'title': title,
                'week_count': week_count,
                'goal': goal,
                'deadline': deadline,
                'target_score': target_score,
                'current_level': current_level,
                'created_by': self.user,
            },
        )
        return {
            'id': plan.id, 'title': plan.title, 'created': created,
            'goal': plan.goal or '',
            'deadline': plan.deadline.isoformat() if plan.deadline else None,
            'week_count': plan.week_count,
        }

    def _handle_get_teaching_plan_kps(self, args: Dict) -> Dict:
        """查询教学计划的知识点（按周筛选）。不传 teaching_plan_id 时返回列表。"""
        from courses.models import TeachingPlan

        teaching_plan_id = args.get('teaching_plan_id')
        week_number = args.get('week_number')

        # 无 teaching_plan_id → 返回机构下所有教学计划摘要
        if not teaching_plan_id:
            qs = TeachingPlan.objects.all()
            if self.institution:
                qs = qs.filter(institution=self.institution)
            plans = qs.select_related('class_obj').order_by('-created_at')[:20]
            return {
                "plans": [
                    {
                        "id": p.id, "title": p.title,
                        "subject": p.subject or '',
                        "semester": p.semester or '',
                        "class_name": p.class_obj.name if p.class_obj else '',
                        "week_count": p.week_count,
                        "goal": p.goal or '',
                    }
                    for p in plans
                ],
                "total": qs.count(),
                "hint": "选择一个教学计划 ID，传入 teaching_plan_id 查询具体周的知识点",
            }

        teaching_plan_id = int(teaching_plan_id)

        try:
            plan = TeachingPlan.objects.get(id=teaching_plan_id)
        except TeachingPlan.DoesNotExist:
            return {"error": f"教学计划 #{teaching_plan_id} 不存在"}

        if self.institution and plan.institution_id != self.institution.id:
            return {"error": "无权访问该教学计划"}

        weekly_plans = plan.weekly_plans or []

        if week_number is not None:
            week_number = int(week_number)
            weekly_plans = [w for w in weekly_plans if w.get('week') == week_number]
            if not weekly_plans:
                return {"error": f"第 {week_number} 周不在教学计划中（1-{plan.week_count}）"}

        from quizzes.models import KnowledgePoint
        weeks_data = []
        all_kp_ids = set()
        for wp in weekly_plans:
            kp_ids = wp.get('kp_ids') or []
            all_kp_ids.update(kp_ids)
            weeks_data.append({
                "week": wp.get('week'),
                "topic": wp.get('topic', ''),
                "kp_ids": kp_ids,
            })

        # 查知识点名称
        kp_map = {}
        if all_kp_ids:
            for kp in KnowledgePoint.objects.filter(id__in=list(all_kp_ids)).values('id', 'name', 'code'):
                kp_map[kp['id']] = {"name": kp['name'], "code": kp['code'] or ''}

        for wd in weeks_data:
            wd['knowledge_points'] = [{"id": kp_id, **kp_map.get(kp_id, {"name": f"KP#{kp_id}", "code": ""})}
                                       for kp_id in wd['kp_ids']]

        return {
            "teaching_plan_id": plan.id,
            "title": plan.title,
            "subject": plan.subject or '',
            "weeks": weeks_data,
            "total_kps": len(all_kp_ids),
        }

    # ── 学生学情报告 ────────────────────────────────────────────

    def _handle_generate_student_report(self, args: Dict) -> Dict:
        """按需生成学生学情报告（仅教师/机构主可用）。"""
        from users.models import User
        from users.views import _build_report_data
        from datetime import datetime, timedelta
        from django.utils import timezone
        from users.permissions import is_institution_teacher

        if not self.institution or not is_institution_teacher(self.user):
            return {"error": "仅教师/机构主可使用此功能"}

        # Resolve student
        student_id = args.get('student_id')
        student_name = args.get('student_name', '').strip()
        try:
            if student_id:
                student = User.objects.get(id=int(student_id), institution=self.institution)
            elif student_name:
                student = User.objects.filter(
                    institution=self.institution,
                    nickname__icontains=student_name
                ).first() or User.objects.filter(
                    institution=self.institution,
                    username__icontains=student_name
                ).first()
                if not student:
                    return {"error": f"未找到学生: {student_name}"}
            else:
                return {"error": "请提供 student_name 或 student_id"}
        except User.DoesNotExist:
            return {"error": "学生不存在"}

        # Parse date range (defensive against LLM malformed dates)
        date_from_str = args.get('date_from', '')
        date_to_str = args.get('date_to', '')
        now = timezone.now()
        try:
            date_from = datetime.fromisoformat(date_from_str) if date_from_str else (now - timedelta(days=30))
        except (ValueError, TypeError):
            date_from = now - timedelta(days=30)
        try:
            date_to = datetime.fromisoformat(date_to_str) if date_to_str else now
        except (ValueError, TypeError):
            date_to = now

        action = args.get('action', 'preview')

        # Build report data
        report = _build_report_data(student, date_from=date_from, date_to=date_to)
        report['date_from'] = date_from.isoformat() if hasattr(date_from, 'isoformat') else str(date_from)
        report['date_to'] = date_to.isoformat() if hasattr(date_to, 'isoformat') else str(date_to)
        report['student_name'] = student.nickname or student.username

        if action == 'preview':
            self.pending_visuals.append({
                'type': 'student_report',
                'payload': report,
            })
            return {"report": report, "action": "preview"}
        elif action == 'export_pdf':
            return {"report": report, "action": "export_pdf", "message": "PDF 导出功能即将上线"}
        elif action == 'send_to_student':
            from notifications.models import Notification
            Notification.objects.create(
                recipient=student,
                title='学情报告',
                content=f'你的学习报告已生成，包含 {report.get("stats", {}).get("total_attempted", 0)} 次答题记录。',
                ntype='system',
            )
            return {"action": "send_to_student", "message": f"报告已发送给 {student.nickname or student.username}"}
        else:
            return {"error": f"不支持的操作: {action}"}

    # ── F2: 批改助手 ────────────────────────────────────────────────

    def _apply_grade_edits(self, assignment_id: int, edits: list) -> int:
        """共享方法：批量写入评分。返回确认数量。"""
        from quizzes.models import AssignmentSubmission
        from django.utils import timezone

        confirmed = 0
        for edit in edits:
            sid = int(edit.get('submission_id', 0))
            score = float(edit.get('score', 0))
            feedback = (edit.get('feedback') or '').strip()
            try:
                sub = AssignmentSubmission.objects.get(
                    id=sid, assignment_id=assignment_id,
                    assignment__institution=self.institution,
                )
                sub.score = score
                sub.graded_by = self.user
                sub.graded_at = timezone.now()
                if feedback:
                    sub.feedback = feedback
                sub.save(update_fields=['score', 'graded_by', 'graded_at', 'feedback'])
                confirmed += 1
            except AssignmentSubmission.DoesNotExist:
                pass
        return confirmed

    def _handle_bulk_grade_submissions(self, args: Dict) -> Dict:
        """批量 AI 评分并渲染可编辑预览卡片（仅教师/机构主可用）。"""
        from quizzes.models import AssignmentSubmission, Assignment
        from ai_assistant.services.grading_engine import GradingEngine
        from ai_engine.config import AI_PROVIDER
        from django.utils import timezone
        from users.permissions import is_institution_teacher

        if not self.institution or not is_institution_teacher(self.user):
            return {"error": "仅教师/机构主可使用此功能"}

        assignment_id = int(args.get('assignment_id', 0))
        action = args.get('action', 'preview')

        try:
            assignment = Assignment.objects.get(id=assignment_id, institution=self.institution)
        except Assignment.DoesNotExist:
            return {"error": f"作业 #{assignment_id} 不存在"}

        if action == 'reject':
            return {'rejected': True, 'message': '已驳回全部 AI 评分，请重新批改或手动评分'}

        if action not in ('preview', 'confirm', 'reject'):
            return {"error": f"不支持的操作: {action}"}

        submissions = AssignmentSubmission.objects.filter(
            assignment_id=assignment_id, score__isnull=True
        ).select_related('student', 'question', 'question__knowledge_point')

        if not submissions.exists():
            return {"error": "该作业没有待批改的提交"}

        if action == 'preview':
            ai = AI_PROVIDER
            graded = []
            for sub in submissions:
                try:
                    question = sub.question
                    result = GradingEngine.grade(
                        ai=ai,
                        question_text=question.text or '',
                        user_answer=sub.answers or '',
                        correct_answer=getattr(question, 'answer', '') or '',
                        q_type=question.q_type or 'obj',
                        max_score=10,
                        user=self.user,
                    )
                    graded.append({
                        'submission_id': sub.id,
                        'student_name': sub.student.nickname or sub.student.username,
                        'question_preview': (question.text or '')[:200],
                        'ai_score': result.get('score', 0),
                        'ai_feedback': result.get('feedback', ''),
                        'q_type': question.q_type or '',
                    })
                except Exception:
                    graded.append({
                        'submission_id': sub.id,
                        'student_name': sub.student.nickname or sub.student.username,
                        'question_preview': (getattr(sub.question, 'text', '') or str(sub.id))[:200],
                        'ai_score': 0,
                        'ai_feedback': 'AI 评分失败，请手动批改',
                        'q_type': '',
                    })

            self.pending_visuals.append({
                'type': 'grading_preview',
                'payload': {
                    'assignment_id': assignment_id,
                    'title': assignment.title or f'作业 #{assignment_id}',
                    'submissions': graded,
                },
            })
            return {
                'assignment_id': assignment_id,
                'title': assignment.title,
                'graded_count': len(graded),
                'submissions': graded,
            }

        elif action == 'confirm':
            edits = args.get('edits', [])
            if not edits:
                return {"error": "请提供 edits 列表"}
            confirmed = self._apply_grade_edits(assignment_id, edits)
            return {'confirmed_count': confirmed, 'message': f'已确认 {confirmed} 份批改'}

    def _handle_confirm_grades(self, args: Dict) -> Dict:
        """确认 AI 评分并批量写入数据库（仅教师/机构主可用）。"""
        from users.permissions import is_institution_teacher

        if not self.institution or not is_institution_teacher(self.user):
            return {"error": "仅教师/机构主可使用此功能"}
        assignment_id = int(args.get('assignment_id', 0))
        edits = args.get('edits', [])
        if not edits:
            return {"error": "请提供 edits 列表"}
        confirmed = self._apply_grade_edits(assignment_id, edits)
        return {'confirmed_count': confirmed}
