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

        # 始终返回机构学科列表，让 agent 知道当前机构有哪些学科
        if self.institution:
            inst_subjects = list(
                KnowledgePoint.objects.filter(
                    Q(institution=self.institution) | Q(institution__isnull=True),
                    level='kp',
                ).values_list('subject', flat=True).distinct()
            )
            result["institution_subjects"] = [s for s in inst_subjects if s]

        # mode=kp 或 auto：搜知识点
        if mode in ('kp', 'auto'):
            qs = KnowledgePoint.objects.filter(name__icontains=query, level='kp')
            if subject:
                qs = qs.filter(subject=subject)
            if self.institution:
                qs = qs.filter(Q(institution=self.institution) | Q(institution__isnull=True))

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
            if self.institution:
                tree_qs = tree_qs.filter(Q(institution=self.institution) | Q(institution__isnull=True))

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
        base_qs = KnowledgePoint.objects.filter(level='kp')
        if self.institution:
            base_qs = base_qs.filter(Q(institution=self.institution) | Q(institution__isnull=True))
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

        _on_step = self.on_step
        _call_id = getattr(self, '_current_call_id', 'quick_generate')

        def _on_progress(completed: int, total: int, batch_count: int):
            if _on_step:
                try:
                    _on_step({
                        "type": "step",
                        "call_id": _call_id,
                        "step": 0,
                        "status": "calling",
                        "name": "quick_generate",
                        "label": f"正在生成第 {completed}/{total} 批（已出 {batch_count} 题）",
                    })
                except Exception:
                    pass

        try:
            result = run_single_generate_pipeline(
                kp_ids=kp_ids,
                count_per_kp=count_per_kp,
                target_difficulty='normal',
                institution=self.institution,
                on_progress=_on_progress,
                skip_review=True,
            )
            questions = result.get('questions', [])
        except Exception as e:
            logger.warning("quick_generate 失败: %s", e)
            return {"error": f"出题失败：{e}。请换一个知识点或减少题量重试。"}

        if not questions:
            return {"error": "题目生成失败，请重试或换一个知识点"}

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
