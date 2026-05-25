"""
出题 Agent 工具执行器。

继承 AssistantToolExecutor，提供出题专用工具：
- search_knowledge_points: 搜索知识点
- generate_questions: 快速管线出题
- launch_arc_pipeline: 启动 ARC 精修管线
- check_pipeline_status: 查询管线进度
- save_questions_to_library: 存入题库
"""

import json
from typing import Any, Dict, List

from ai_assistant.services.tool_executor import AssistantToolExecutor


class ExamGeneratorToolExecutor(AssistantToolExecutor):
    """出题 Agent 工具执行器。继承助教基础工具。"""

    def __init__(self, user, institution=None):
        super().__init__(user, institution)
        self._last_generated: List[Dict[str, Any]] = []
        self._last_pipeline_task_id: int | None = None

    # ── 搜索知识点 ──────────────────────────────────────────

    def _handle_search_knowledge_points(self, args: Dict) -> Dict:
        from django.db.models import Q
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
            qs = qs.filter(Q(institution=self.institution) | Q(institution__isnull=True))

        kps = qs.values('id', 'code', 'name', 'subject', 'description')[:15]
        return {
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

    # ── 快速出题 ────────────────────────────────────────────

    def _handle_generate_questions(self, args: Dict) -> Dict:
        from quizzes.services.single_generate_pipeline import run_single_generate_pipeline

        kp_ids = args.get('kp_ids', [])
        if not kp_ids:
            return {"error": "请提供至少一个知识点 ID"}

        count_per_kp = int(args.get('count_per_kp', 3))
        difficulty = args.get('difficulty', 'normal')
        types = args.get('types')

        # 主路径：管线生成
        try:
            result = run_single_generate_pipeline(
                kp_ids=kp_ids,
                count_per_kp=count_per_kp,
                target_types=types,
                target_difficulty=difficulty,
            )
            questions = result.get('questions', [])
        except Exception:
            # fallback：直接用 AI 生成
            questions = self._fallback_generate(kp_ids, count_per_kp, difficulty, types)

        if not questions:
            return {"error": "题目生成失败，请重试或换一个知识点"}

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

    def _fallback_generate(self, kp_ids, count_per_kp, difficulty, types):
        """管线失败时的 fallback：直接调 AI 生成题目。"""
        import json as _json
        from quizzes.models import KnowledgePoint
        from ai_service import AIService

        kps = list(KnowledgePoint.objects.filter(id__in=kp_ids, level='kp').values('id', 'code', 'name', 'subject'))
        if not kps:
            return []

        kp_desc = ', '.join(f"{k['name']}(id={k['id']})" for k in kps[:5])
        type_str = '客观题和主观题' if not types else '、'.join(types)
        total = count_per_kp * len(kps)

        prompt = (
            f"请为以下知识点生成 {total} 道题目：{kp_desc}\n"
            f"题型：{type_str}，难度：{difficulty}\n\n"
            "请以 JSON 数组格式输出，每道题包含以下字段：\n"
            '{"question": "题干", "q_type": "objective或subjective", '
            '"subjective_type": "名词解释/简答/论述/计算 或 null", '
            '"options": ["A.xx", "B.xx", "C.xx", "D.xx"] 或 null, '
            '"answer": "正确答案", "grading_points": ["得分点1"] 或 null, '
            '"difficulty_level": "entry/easy/normal/hard/extreme", '
            '"related_knowledge_id": "知识点编码"}\n\n'
            "只输出 JSON 数组，不要其他文字。"
        )

        raw = AIService.simple_chat_text(
            system_prompt='你是专业命题专家。只输出 JSON 数组。',
            user_prompt=prompt,
            temperature=0.4,
            max_tokens=4000,
            operation='exam_generator.fallback',
        )

        if not raw:
            return []

        data = AIService.extract_json(raw)
        if not isinstance(data, list):
            return []

        # 填充 kp_id
        kp_by_code = {k['code']: k['id'] for k in kps if k.get('code')}
        fallback_kp_id = kps[0]['id']
        for item in data:
            if not item.get('kp_id'):
                code = (item.get('related_knowledge_id') or '').strip()
                item['kp_id'] = kp_by_code.get(code, fallback_kp_id)
            if not item.get('kp_name'):
                kp_match = next((k for k in kps if k['id'] == item.get('kp_id')), None)
                if kp_match:
                    item['kp_name'] = kp_match['name']

        return data

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

        # 机构隔离
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

    # ── 存入题库 ────────────────────────────────────────────

    def _handle_save_questions_to_library(self, args: Dict) -> Dict:
        from quizzes.models import Question, KnowledgePoint

        if not self._last_generated:
            return {"error": "没有可保存的题目。请先调用 generate_questions 生成题目。"}

        indices = args.get('question_indices')
        if indices:
            to_save = [self._last_generated[i] for i in indices if i < len(self._last_generated)]
        else:
            to_save = self._last_generated

        if not to_save:
            return {"error": "未选择有效题目"}

        saved_count = 0
        errors = []
        for q in to_save:
            try:
                kp = None
                kp_id = q.get('kp_id')
                if kp_id:
                    kp = KnowledgePoint.objects.filter(id=kp_id).first()

                question = Question(
                    text=q.get('question', ''),
                    q_type=q.get('q_type', 'objective'),
                    subjective_type=q.get('subjective_type'),
                    difficulty_level=q.get('difficulty_level', 'normal'),
                    options=q.get('options'),
                    correct_answer=q.get('answer', ''),
                    grading_points='\n'.join(q.get('grading_points', []) or []) if q.get('grading_points') else None,
                    knowledge_point=kp,
                    institution=self.institution,
                )
                question.save()
                saved_count += 1
            except Exception as e:
                errors.append(str(e))

        return {
            "saved": saved_count,
            "total": len(to_save),
            "errors": errors[:3] if errors else [],
        }
