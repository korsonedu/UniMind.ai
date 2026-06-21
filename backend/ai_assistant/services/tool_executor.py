"""
Agent 工具执行器。

每个工具方法返回 JSON 字符串，供模型在多轮工具调用中消费。
"""

import json
import logging
from typing import Any, Dict, List
from django.db import models

logger = logging.getLogger(__name__)


def _inject_kp_chain_experiences(kp_ids: list, user, institution=None) -> list[str]:
    """
    搜索知识树后，检查是否有 kp_chain 经验匹配这些 KP，
    返回经验指引文本列表供追加到工具结果中。

    用于 Phase 3 kp_chain 二次注入：初次对话时还没确定 KP，
    等到搜索知识树返回 KP 后再检查经验。
    """
    from .experience_applicator import get_applicable_experiences, record_trigger

    hints = []
    for kp_id in kp_ids:
        context = {
            'event': '讲解',
            'kp_id': kp_id,
            'student_id': user.id if user else None,
            'institution_id': institution.id if institution else None,
        }
        applicable = get_applicable_experiences(context, limit=3)
        if applicable:
            for exp in applicable:
                if exp.dimension in ('prompt', 'workflow'):
                    instruction = (exp.effect or {}).get('instruction', exp.title)
                    hints.append(f'[{exp.get_dimension_display()}] {instruction}')
            record_trigger(applicable)

    return hints


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
        'run_diagnostic': lambda a: "生成诊断题目" if a.get('mode') == 'generate' else "提交诊断答案",
        'quick_generate': lambda a: f"快速生成{a.get('count', 5)}道题",
        'render_visual': lambda a: f"渲染{a.get('type', '可视化')}",
        'launch_arc_pipeline': lambda a: "启动 ARC 精修管线",
        'check_pipeline_status': lambda a: "检查管线执行进度",
        'get_workbench_stats': lambda a: "获取题库统计",
        'get_student_detail': lambda a: f"查看「{a.get('student_name', a.get('student_id', '学生'))}」学习数据",
        'get_assignment_progress': lambda a: f"查询作业 #{a.get('assignment_id', '')} 进度",
        'assign_practice': lambda a: f"布置作业「{a.get('title', '课后练习')}」",
        'send_notification': lambda a: f"发送提醒给「{a.get('student_name', a.get('student_id', '学生'))}」",
        'list_courses': lambda a: "浏览课程库" + (f"（{a.get('subject', '')}）" if a.get('subject') else ""),
        'list_questions': lambda a: "浏览题库" + (f"（{a.get('kp_name', '')}）" if a.get('kp_name') else ""),
        'list_articles': lambda a: "浏览文章库" + (f"（搜索: {a.get('query', '')}）" if a.get('query') else ""),
        'list_lesson_plans': lambda a: "浏览教案库" + (f"（{a.get('subject', '')}）" if a.get('subject') else ""),
        'get_report_card': lambda a: "生成学习报告",
        'get_my_courses': lambda a: "查询我的课程",
        'get_my_achievements': lambda a: "查看我的成就",
    }
    generator = labels.get(tool_name)
    if generator:
        try:
            return generator(args)
        except Exception:
            pass
    return f"执行 {tool_name}"


def extract_step_actions(result) -> list | None:
    """从工具结果 JSON 中提取 _actions 数组，用于前端渲染操作链接。"""
    import json as _json
    if isinstance(result, str):
        try:
            result = _json.loads(result)
        except Exception:
            return None
    if isinstance(result, dict):
        actions = result.get('_actions')
        if isinstance(actions, list) and len(actions) > 0:
            return actions
    return None


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
        'render_visual': lambda r: (
            f"渲染失败: {r.get('error', '')}" if r.get('error')
            else f"渲染可视化: {(r.get('visual', {}) if isinstance(r.get('visual'), dict) else {}).get('type', r.get('type', ''))}"
        ),
        'get_user_wrong_questions': lambda r: f"找到 {r.get('total_found', 0)} 道错题",
        'search_asr': lambda r: f"找到 {r.get('total_found', 0)} 个视频片段",
        'get_practice_questions': lambda r: f"抽取 {len(r.get('questions', []))} 道练习题",
        'grade_student_answer': lambda r: f"得分 {r.get('score', 0)}/{r.get('max_score', 0)}" + (
            ' · ' + {'concept_error':'概念错误','calculation_error':'计算失误','careless_mistake':'审题失误'}.get(
                r.get('error_analysis', {}).get('type', ''), ''
            ) if r.get('error_analysis', {}).get('type') else ''
        ) + (f" · 推荐{len(r.get('remediation_questions', []))}道变式题" if r.get('remediation_questions') else ''),
        'update_plan_task': lambda r: f"任务已更新为 {r.get('new_status', 'unknown')}",
        'run_diagnostic': lambda r: f"诊断完成，答对 {r.get('total_correct', 0)}/{r.get('total_questions', 0)}" if 'total_correct' in r else f"已生成 {len(r.get('questions', []))} 道诊断题",
        'get_student_detail': lambda r: f"{r.get('name', '')} 正确率 {r.get('accuracy', 0)}%" + (
            f"，{len(r.get('weak_points', []))} 个薄弱点" if r.get('weak_points') else ""),
        'get_assignment_progress': lambda r: f"「{r.get('title', '')}」提交 {r.get('submitted', 0)}/{r.get('total_students', 0)}" + (
            f"，{r.get('pending_grade', 0)} 份待批改" if r.get('pending_grade', 0) else "，全部已批改"),
        'assign_practice': lambda r: f"已发布「{r.get('title', '')}」{r.get('question_count', 0)} 题给 {r.get('class_count', 0)} 个班",
        'send_notification': lambda r: f"已发送提醒给 {r.get('count', 0)} 人",
        'list_courses': lambda r: f"共 {r.get('total', 0)} 门课程",
        'list_questions': lambda r: f"共 {r.get('total', 0)} 道题",
        'list_articles': lambda r: f"共 {r.get('total', 0)} 篇文章",
        'list_lesson_plans': lambda r: f"共 {r.get('total', 0)} 份教案",
        'get_report_card': lambda r: f"正确率 {r.get('accuracy', 0)}%，掌握 {r.get('mastered_count', 0)} 个知识点",
        'get_my_courses': lambda r: f"共 {len(r.get('courses', []))} 门课程",
        'get_my_achievements': lambda r: f"已解锁 {r.get('unlocked_count', len(r.get('unlocked', [])))} 个成就",
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

    # 工具名别名：LLM 跨 bot 误调用时自动纠正
    TOOL_ALIASES: Dict[str, str] = {
        "search_knowledge": "search_knowledge_tree",
    }

    def __init__(self, user, institution=None):
        self.user = user
        self._allowed_tool_names = None
        self.institution = institution or getattr(user, 'institution', None)
        self.class_id: int | None = None  # 由 chat_dispatch 注入，当前选中的班级 ID
        self.on_step = None  # 由 views 注入，用于工具内部发进度事件
        self._current_call_id: str | None = None  # 由 service.py 注入，用于进度事件携带正确 call_id
        self.tool_call_log: list = []     # MUTAR 轨迹：工具调用序列
        self.tool_output_log: list = []   # MUTAR 轨迹：工具返回结果
        self.pending_visuals: list = []   # render_visual 输出收集，供 SSE done 事件持久化

    def __call__(self, tool_name: str, args: Dict[str, Any]) -> str:
        # 别名修正：LLM 可能跨 bot 误调用不同命名规范的工具
        original_name = tool_name
        tool_name = self.TOOL_ALIASES.get(tool_name, tool_name)
        if tool_name != original_name:
            logger.info("Tool alias: %s → %s", original_name, tool_name)

        # 软白名单：路由预测的工具集是引导而非硬限制。
        # LLM 在多轮工具调用中意图会漂移——路由时没预测到的工具，
        # 只要本 bot 确实有 handler，就自动放行并加入白名单。
        allowed = getattr(self, '_allowed_tool_names', None)
        if allowed is not None and tool_name not in allowed:
            handler = getattr(self, f'_handle_{tool_name}', None)
            if handler is not None:
                # 合法工具，仅路由时未预选 → 自愈放行
                allowed.add(tool_name)
                logger.info(
                    "Tool '%s' not in initial route, auto-allowed (handler exists)",
                    tool_name,
                )
            else:
                return json.dumps(
                    {"error": f"Tool not allowed: {tool_name}"},
                    ensure_ascii=False,
                )

        handler = getattr(self, f'_handle_{tool_name}', None)
        if handler is None:
            return json.dumps({"error": f"Unknown tool: {tool_name}"}, ensure_ascii=False)
        try:
            result = handler(args)
            output = json.dumps(result, ensure_ascii=False, default=str)
        except Exception as exc:
            output = json.dumps({"error": str(exc)}, ensure_ascii=False)

        # 记录轨迹日志
        self.tool_call_log.append({"name": tool_name, "args": args})
        self.tool_output_log.append(output)
        return output

    # ── Tool handlers ──────────────────────────────────────────

    def _handle_render_visual(self, args: Dict) -> Dict:
        """将可视化数据返回给前端，同时缓存到实例供消息持久化。

        对 DeepSeek 常见小偏差做宽容修正（缺 title 用 description 补等），
        但不可恢复的输入错误必须返回 error——返回 ok 会导致 LLM 自激循环。
        """
        visual_type = (args.get('type') or '').strip()
        payload = args.get('payload', {})
        priority = args.get('priority', 'normal')

        valid_types = {'data_card', 'latex_derivation', 'step_solution', 'knowledge_map', 'action_cards', 'function_graph'}
        if visual_type not in valid_types:
            valid_list = ', '.join(sorted(valid_types))
            return {"error": f"可视化类型无效: '{visual_type}'。支持: {valid_list}"}

        # DeepSeek 有时把 payload 作为 JSON 字符串传入
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, TypeError):
                return {"error": "payload 必须是 JSON 对象，收到无法解析的字符串"}

        if not isinstance(payload, dict):
            return {"error": "payload 必须是 JSON 对象"}

        # action_cards：修正小偏差，但全无效时返回 error 而非空卡片
        if visual_type == 'action_cards':
            raw_cards = payload.get('cards', [])
            if not isinstance(raw_cards, list):
                return {"error": "action_cards 的 cards 字段必须是数组"}
            fixed_cards = []
            for c in raw_cards:
                if not isinstance(c, dict):
                    continue
                if not c.get('title'):
                    fallback = (
                        c.get('description') or
                        (c.get('action', {}).get('label') if isinstance(c.get('action'), dict) else None) or
                        ''
                    )
                    if fallback:
                        c = {**c, 'title': fallback}
                    else:
                        continue
                if 'action' not in c or not isinstance(c.get('action'), dict):
                    c = {**c, 'action': {'type': 'reply', 'url': c.get('title', ''), 'label': c.get('title', '')}}
                fixed_cards.append(c)
            if not fixed_cards:
                return {"error": "action_cards 必须包含至少一张有效卡片（每张需要 title 或 description）"}
            payload = {**payload, 'cards': fixed_cards}

        visual = {"type": visual_type, "payload": payload, "priority": priority}
        self.pending_visuals.append(visual)
        return {"status": "ok", "visual": visual}

    def _handle_search_knowledge_tree(self, args: Dict) -> Dict:
        from ai_assistant.services.memory_system import MemorySystem
        query = (args.get('query') or '').strip()
        subject = (args.get('subject') or '').strip()
        result = MemorySystem.query_knowledge_tree(query, subject, self.user, self.institution)

        # 经验路由器 Phase 3：kp_chain 二次注入
        # 搜索到 KP 后，检查是否有针对这些 KP 的 kp_chain 经验
        results = result.get('results', [])
        if results:
            kp_ids = [r['id'] for r in results if r.get('id')]
            if kp_ids:
                kp_hints = _inject_kp_chain_experiences(kp_ids, self.user, self.institution)
                if kp_hints:
                    hint_text = '\n'.join(f'  • {h}' for h in kp_hints)
                    result['_experience_guidance'] = (
                        f'\n\n📋 教学经验指引（针对找到的知识点）：\n{hint_text}'
                    )

        return result

    def _handle_get_user_weak_points(self, args: Dict) -> Dict:
        from ai_assistant.services.memory_system import MemorySystem
        return MemorySystem.query_weak_points(self.user, self.institution)

    def _handle_get_user_wrong_questions(self, args: Dict) -> Dict:
        from ai_assistant.services.memory_system import MemorySystem
        limit = min(int(args.get('limit', 5)), 10)
        return MemorySystem.query_user_wrong_questions(self.user, limit, self.institution)

    def _handle_get_class_weak_points(self, args: Dict) -> Dict:
        """获取班级最薄弱的知识点（仅 teacher/owner 可用）。"""
        if not self.institution or getattr(self.user, 'institution_role', '') not in ('teacher', 'owner'):
            return {"error": "仅教师/机构主可使用班级分析功能"}

        from ai_assistant.services.memory_system import MemorySystem
        limit = min(int(args.get('limit', 5)), 10)
        return MemorySystem.query_class_weak_points(self.institution, limit)

    def _handle_get_class_performance_summary(self, args: Dict) -> Dict:
        """获取班级整体学习数据概览（仅 teacher/owner 可用）。"""
        if not self.institution or getattr(self.user, 'institution_role', '') not in ('teacher', 'owner'):
            return {"error": "仅教师/机构主可使用班级分析功能"}

        from ai_assistant.services.memory_system import MemorySystem
        return MemorySystem.query_class_performance(self.institution)

    def _handle_lookup_question(self, args: Dict) -> Dict:
        from ai_assistant.services.memory_system import MemorySystem
        qid = int(args.get('question_id', 0))
        result = MemorySystem.query_question(qid, self.institution)
        if "error" in result:
            return result
        # 兼容旧字段名
        result["answer"] = result.get("correct_answer", "")
        return result

    # ── 成绩报告 ──

    def _handle_get_report_card(self, args: Dict) -> Dict:
        """获取学生成绩单/学习报告。"""
        try:
            from users.views import _build_report_data
            data = _build_report_data(self.user)
            stats = data.get('stats', {})
            return {
                'checkin_streak': stats.get('checkin_streak', 0),
                'total_attempted': stats.get('total_attempted', 0),
                'accuracy': stats.get('accuracy', 0),
                'mastered_count': stats.get('mastered_count', 0),
                'elo_score': data.get('student', {}).get('elo_score', 0),
                'subjects': [r['subject'] for r in data.get('radar', [])],
                'recent_exams': [
                    {'score': e['total_score'], 'max': e['max_score'], 'date': e['created_at'][:10]}
                    for e in data.get('exams', [])[:5]
                ],
                'achievements': [
                    {'name': a['name'], 'icon': a['icon'], 'date': a['unlocked_at'][:10]}
                    for a in data.get('achievements', [])[:5]
                ],
            }
        except Exception as e:
            logger.exception("get_report_card failed")
            return {"error": f"获取报告失败: {str(e)}"}

    def _handle_get_my_courses(self, args: Dict) -> Dict:
        """获取学生当前班级分配的课程列表。"""
        from courses.models import Course
        from users.models import Class, ClassCourse

        member_class = None
        class_id = None
        if self.user.institution:
            member_class = Class.objects.filter(
                students=self.user, institution=self.user.institution
            ).first()
            if member_class:
                class_id = member_class.id

        if not class_id:
            return {"courses": [], "message": "你尚未加入任何班级，请联系老师"}

        course_ids = ClassCourse.objects.filter(
            class_obj_id=class_id,
        ).values_list('course_id', flat=True)

        courses = Course.objects.filter(
            id__in=course_ids,
        ).order_by('title')[:20]

        return {
            'courses': [
                {'id': c.id, 'title': c.title, 'subject': c.subject or ''}
                for c in courses
            ],
            'class_name': member_class.name if member_class else '',
        }

    def _handle_get_my_achievements(self, args: Dict) -> Dict:
        """获取学生已解锁的成就列表。"""
        from users.models import UserAchievement
        qs = UserAchievement.objects.filter(
            user=self.user,
        ).select_related('achievement').order_by('-unlocked_at')

        unlocked = [
            {
                'name': ua.achievement.name,
                'description': ua.achievement.description,
                'icon': ua.achievement.icon,
                'category': ua.achievement.category,
                'unlocked_at': ua.unlocked_at.isoformat() if ua.unlocked_at else '',
            }
            for ua in qs
        ]

        # Also get all achievements with progress
        from users.models import Achievement, DailyCheckIn
        all_achs = Achievement.objects.filter(is_active=True).order_by('category', 'threshold')
        all_list = []
        unlocked_keys = {ua.achievement.key for ua in qs}
        checkin = DailyCheckIn.objects.filter(user=self.user).order_by('-date').first()
        streak_val = checkin.streak if checkin else 0

        for a in all_achs:
            entry = {
                'name': a.name,
                'description': a.description,
                'icon': a.icon,
                'category': a.category,
                'unlocked': a.key in unlocked_keys,
            }
            all_list.append(entry)

        return {
            'unlocked_count': len(unlocked),
            'unlocked': unlocked[:8],
            'all': all_list,
        }


class PlannerToolExecutor(BaseToolExecutor):
    """扩展基础工具执行器，增加规划相关工具。继承全部基础工具。"""

    def __init__(self, user, institution=None):
        super().__init__(user, institution)

    def _handle_get_learning_stats(self, args: Dict) -> Dict:
        from ai_assistant.services.memory_system import MemorySystem
        return MemorySystem.query_learning_stats(self.user)

    def _handle_get_knowledge_mastery_map(self, args: Dict) -> Dict:
        from ai_assistant.services.memory_system import MemorySystem
        return MemorySystem.query_mastery_map(self.user, args.get('subject'), self.institution)

    def _handle_get_due_reviews(self, args: Dict) -> Dict:
        from ai_assistant.services.memory_system import MemorySystem
        limit = min(int(args.get('limit', 20)), 50)
        return MemorySystem.query_due_reviews(self.user, limit, self.institution)

    def _handle_get_practice_questions(self, args: Dict) -> Dict:
        """根据知识点或薄弱点从题库中抽取题目供学生练习。"""
        from ai_assistant.services.memory_system import MemorySystem
        return MemorySystem.query_practice_questions(
            user=self.user,
            kp_name=(args.get('kp_name') or '').strip(),
            subject=(args.get('subject') or '').strip(),
            difficulty=(args.get('difficulty') or '').strip(),
            limit=min(int(args.get('limit', 5)), 10),
            exclude_mastered=args.get('exclude_mastered', True),
            institution=self.institution,
        )

    def _handle_get_exam_history(self, args: Dict) -> Dict:
        from ai_assistant.services.memory_system import MemorySystem
        limit = min(int(args.get('limit', 10)), 20)
        return MemorySystem.query_exam_history(self.user, limit, self.institution)

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
        from ai_assistant.services.memory_system import MemorySystem
        return MemorySystem.query_difficulty_analysis(self.user, args.get('subject'), self.institution)

    def _handle_grade_student_answer(self, args: Dict) -> Dict:
        """批改学生的回答。查找题目→调用判分服务→返回评分反馈+变式题+知识点掌握度。"""
        from ai_assistant.services.memory_system import MemorySystem
        from ai_assistant.services.grading_engine import GradingEngine
        from ai_engine.ai_service import AIService
        from django.utils import timezone

        question_id = int(args.get('question_id', 0))
        user_answer = str(args.get('user_answer', '')).strip()

        if not question_id:
            return {"error": "请提供 question_id"}
        if not user_answer:
            return {"error": "请提供学生的回答内容", "score": 0, "max_score": 0,
                    "feedback": "学生未作答", "is_correct": False}

        # 通过 MemorySystem 获取题目
        question_dict = MemorySystem.query_question(question_id, self.institution)
        if "error" in question_dict:
            return question_dict

        ai = AIService()
        result = GradingEngine.grade(
            ai=ai,
            question_text=question_dict['text'],
            user_answer=user_answer,
            correct_answer=question_dict['correct_answer'],
            q_type=question_dict['q_type'],
            max_score=10.0,
            grading_points=question_dict['grading_points'],
            options=question_dict['options'],
            subjective_type=question_dict['subjective_type'] or '主观题',
            user=self.user,
        )

        error_analysis = result.get('error_analysis')
        if error_analysis and error_analysis.get('type'):
            MemorySystem.write_question_status_error(
                self.user, question_id,
                error_analysis['type'],
                {
                    'reasoning': error_analysis.get('reasoning', ''),
                    'suggested_focus': error_analysis.get('suggested_focus', ''),
                    'graded_at': timezone.now().isoformat(),
                },
            )

        MemorySystem.write_grading_record(
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

        # 构造返回
        response = {
            "question_id": question_id,
            "kp_name": question_dict.get('kp_name', ''),
            "score": result.get('score', 0),
            "max_score": 10.0,
            "is_correct": result.get('score', 0) >= 10.0 * 0.6,
            "feedback": result.get('feedback', ''),
            "analysis": result.get('analysis', ''),
            "error_analysis": error_analysis,
        }

        # remediation_questions: 同知识点 + 相近难度的变式题
        kp_id = question_dict.get('knowledge_point_id')
        if kp_id:
            similar = MemorySystem.query_similar_questions(
                kp_id, question_dict.get('difficulty_level', 'normal'), question_id
            )
            response['remediation_questions'] = similar.get('questions', [])

            # kp_breakdown: 该知识点的掌握度
            breakdown = MemorySystem.query_kp_breakdown(self.user, [kp_id])
            response['kp_breakdown'] = breakdown.get('kp_breakdown', [])

        # IRT 参数（如已估计，机构隔离）
        try:
            from quizzes.models import ItemParameter, UserAbility
            item_param = ItemParameter.objects.filter(
                question_id=question_id,
                institution=self.institution,
            ).first()
            if item_param and item_param.responses_count >= 50:
                response['irt_item'] = {
                    'discrimination': item_param.discrimination,
                    'difficulty': item_param.difficulty,
                    'guessing': item_param.guessing,
                }
                if kp_id:
                    ability = UserAbility.objects.filter(
                        user=self.user, knowledge_point_id=kp_id,
                        institution=self.institution,
                    ).first()
                    if ability:
                        p = item_param.guessing + (1 - item_param.guessing) / (
                            1 + 2.71828 ** (-item_param.discrimination * (ability.theta - item_param.difficulty))
                        )
                        response['irt_ability'] = {
                            'theta': ability.theta,
                            'p_correct': round(p, 3),
                        }
        except Exception:
            pass  # IRT 参数可选，失败不影响判分

        return response

    def _handle_run_diagnostic(self, args: Dict) -> Dict:
        """启动诊断测试。generate 模式返回题目，submit 模式评分并初始化 Memorix。"""
        mode = args.get('mode', 'generate')

        if mode == 'generate':
            from quizzes.services.diagnostic_service import (
                generate_diagnostic_questions, DIAGNOSTIC_TIME_LIMIT_SECONDS,
            )
            inst = self.institution
            if not inst:
                return {"error": "请先加入机构才能进行诊断测试"}
            questions = generate_diagnostic_questions(inst)
            if not questions:
                return {"error": "暂无可用题目，请联系管理员"}
            return {
                "questions": questions,
                "time_limit_seconds": DIAGNOSTIC_TIME_LIMIT_SECONDS,
                "message": f"已生成 {len(questions)} 道诊断题目，限时 {DIAGNOSTIC_TIME_LIMIT_SECONDS} 秒",
            }

        elif mode == 'submit':
            answers = args.get('answers', [])
            if not answers:
                return {"error": "请提供答案列表"}

            from quizzes.services.diagnostic_service import (
                grade_diagnostic_answers, initialize_memorix_from_diagnostic,
                build_study_plan,
            )
            from ai_assistant.services.memory_system import MemorySystem
            from django.db import transaction

            # 将 tool 参数格式转换为 diagnostic_service 期望的格式
            formatted_answers = []
            for item in answers:
                qid = item.get('question_id')
                q_dict = MemorySystem.query_question(qid, self.institution)
                if "error" in q_dict:
                    continue
                formatted_answers.append({
                    'question': {
                        'question_text': q_dict['text'],
                        'q_type': q_dict['q_type'],
                        'answer': q_dict['correct_answer'],
                        'knowledge_point_id': q_dict['knowledge_point_id'],
                        '_kp_name': q_dict['kp_name'],
                    },
                    'answer': item.get('answer', ''),
                    'knowledge_point_id': q_dict['knowledge_point_id'],
                    '_kp_name': q_dict['kp_name'],
                })

            if not formatted_answers:
                return {"error": "未找到有效题目"}

            with transaction.atomic():
                results, kp_scores = grade_diagnostic_answers(self.user, formatted_answers)
                initialize_memorix_from_diagnostic(self.user, kp_scores)
                study_plan = build_study_plan(kp_scores)

                self.user.has_completed_initial_assessment = True
                self.user.save(update_fields=['has_completed_initial_assessment'])

            total_correct = sum(1 for r in results if r['is_correct'])
            return {
                "total_correct": total_correct,
                "total_questions": len(results),
                "accuracy": round(total_correct / len(results) * 100, 1) if results else 0,
                "study_plan": study_plan,
                "message": f"诊断完成！答对 {total_correct}/{len(results)} 题",
            }

        return {"error": f"未知模式: {mode}，支持 generate 或 submit"}


