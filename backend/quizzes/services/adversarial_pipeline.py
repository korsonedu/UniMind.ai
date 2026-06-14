"""
对抗性 AI 出题管线 (Adversarial Question Generation Pipeline)

四 AI Agent 迭代博弈：
  Author      — 根据知识点资料 + 人工指定难度/题型 生成候选题目
  Reviewer    — 从区分度、清晰度、知识覆盖三个维度打分 (v4-pro + thinking + agentic)
  AuthorRevise — 根据 Reviewer 反馈逐条修改题目（最多 3 轮）
  Classifier  — 审计员：检测实际难度是否匹配目标、打知识标签、确认题型

难度由人工外生指定，AI 不得自行决定。Classifier 只审计不修改。
每个题目质量分 < 0.7 会退给 Author 修改，最多 3 轮迭代。
管线追踪写入 ContentPipelineTask，前端实时查看进度。
"""

import json
import logging
from typing import Any, Dict, List, Optional

from django.utils import timezone

from ai_service import AIService
from ai_engine.tools import (
    AUTHOR_OUTPUT_SCHEMA, REVIEWER_OUTPUT_SCHEMA,
    AUTHOR_REVISE_OUTPUT_SCHEMA, CLASSIFIER_OUTPUT_SCHEMA,
    BATCH_DIVERSITY_REPORT_SCHEMA,
)
from core.prompt_manager import PromptManager
from quizzes.models import ContentPipelineTask, KnowledgePoint

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 3
QUALITY_THRESHOLD = 0.7
QUESTIONS_PER_KP = 3

DIFFICULTY_DEFINITIONS = {
    "entry":   "概念识记，纯记忆型，单步结论",
    "easy":    "基础理解 + 1-2 步直接推理，干扰项较弱",
    "normal":  "概念+情境结合，2-3 步推理，干扰项有迷惑性",
    "hard":    "跨章节或多模型联动，至少 3 步严谨推理，干扰项高相似",
    "extreme": "高压综合题，模型选择/条件变化/现实约束，需严密论证与批判性分析",
}

BLOOM_LEVELS = {
    "remember":  "识记：回忆事实、术语、基本概念",
    "understand": "理解：解释、归纳、比较、推断",
    "apply":     "应用：用已知方法/公式解决新问题",
    "analyze":   "分析：拆解结构、识别关系、区分因果",
    "evaluate":  "评价：基于标准做出判断、论证观点",
    "create":    "创造：综合信息产生新方案、设计新模型",
}


def run_adversarial_pipeline(
    kp_ids: List[int],
    created_by,
    task_title: str = "",
    questions_per_kp: int = QUESTIONS_PER_KP,
    difficulty: str = "normal",
    types: Optional[List[str]] = None,
    institution=None,
) -> int:
    """启动对抗性出题管线，返回 pipeline_task_id。

    difficulty: 人工指定的目标难度 (entry/easy/normal/hard/extreme)，AI 不得自行偏离。
    """
    kps = list(KnowledgePoint.objects.filter(id__in=kp_ids))
    if not kps:
        raise ValueError("未找到有效知识点")

    types_list = types or []
    difficulty = difficulty or "normal"

    task = ContentPipelineTask.objects.create(
        task_type="ai_generate",
        status="running",
        title=task_title or "对抗性出题管线",
        description=f"知识点: {', '.join(k.name for k in kps[:5])}",
        payload={
            "kp_ids": kp_ids,
            "questions_per_kp": questions_per_kp,
            "difficulty": difficulty,
            "max_iterations": MAX_ITERATIONS,
            "quality_threshold": QUALITY_THRESHOLD,
            "types": types_list,
            "stages": [],
        },
        progress=0,
        created_by=created_by,
        institution=institution,
        started_at=timezone.now(),
    )

    # 异步执行（通过 Celery）
    from quizzes.tasks import run_adversarial_pipeline_task
    run_adversarial_pipeline_task.delay(
        task_id=task.id,
        kp_ids=[k.id for k in kps],
        questions_per_kp=questions_per_kp,
        difficulty=difficulty,
        types=types_list,
    )
    return task.id


def _execute_pipeline(task: ContentPipelineTask, kps: List[KnowledgePoint], q_per_kp: int, difficulty: str = "normal", types: Optional[List[str]] = None, institution=None):
    """执行对抗性出题管线。"""
    all_questions = []
    stage_log = []

    # ── Stage 1: Author 批量生成 ──
    _update_task(task, 5, f"Author 正在按 {_difficulty_label(difficulty)} 难度生成候选题目...", stage_log, "author_start")
    drafts = _author_generate(kps, q_per_kp, difficulty=difficulty, types=types)
    stage_log.append({"stage": "author_generated", "count": len(drafts), "difficulty": difficulty, "timestamp": str(timezone.now())})
    _update_task(task, 30, f"Author 生成了 {len(drafts)} 道候选题目", stage_log, "author_done")

    # ── Stage 2: Reviewer 评分 + 迭代 ──
    _update_task(task, 40, "Reviewer 正在评审...", stage_log, "review_start")
    reviewed = []
    iteration_stats = {i: 0 for i in range(1, MAX_ITERATIONS + 1)}

    for i, draft in enumerate(drafts):
        try:
            for iteration in range(1, MAX_ITERATIONS + 1):
                review_result = _reviewer_evaluate(draft, institution=institution)
                draft["review_score"] = review_result["score"]
                draft["review_feedback"] = review_result["feedback"]
                draft["review_dimensions"] = review_result.get("dimensions", {})
                draft["iteration"] = iteration

                logger.info(
                    "Reviewer kp=%s iteration=%s score=%.2f feedback=%s",
                    draft.get("kp_code", "?"), iteration,
                    review_result["score"],
                    str(review_result.get("feedback", ""))[:200],
                )

                if review_result["score"] >= QUALITY_THRESHOLD:
                    reviewed.append(draft)
                    iteration_stats[iteration] = iteration_stats.get(iteration, 0) + 1
                    break
                elif iteration < MAX_ITERATIONS:
                    prev_question = draft.get("question", "")[:120]
                    prev_answer = draft.get("answer", "")[:120]
                    draft = _author_revise(draft, review_result["feedback"])
                    logger.info(
                        "AuthorRevise kp=%s iteration=%s | before: q=%s answer=%s | after: q=%s answer=%s | feedback=%s",
                        draft.get("kp_code", "?"), iteration,
                        prev_question, prev_answer,
                        draft.get("question", "")[:120], draft.get("answer", "")[:120],
                        str(review_result.get("feedback", ""))[:200],
                    )
                else:
                    # 超过最大轮次，仍保留（标记为低质量）
                    draft["quality_warning"] = True
                    reviewed.append(draft)
                    iteration_stats[iteration] = iteration_stats.get(iteration, 0) + 1
        except Exception as e:
            logger.error(f"Pipeline draft {i} failed: {e}")
            continue

    stage_log.append({
        "stage": "review_done",
        "total": len(reviewed),
        "iteration_distribution": iteration_stats,
        "avg_score": round(sum(q.get("review_score", 0) for q in reviewed) / max(len(reviewed), 1), 3),
        "timestamp": str(timezone.now()),
    })
    _update_task(task, 70, f"Reviewer 完成，{len(reviewed)} 道题通过 ({iteration_stats} 轮分布)", stage_log, "review_done")

    # ── Stage 3: Classifier 三层审计 ──
    subject_kps = _get_subject_knowledge_points(kps, institution=institution)
    _update_task(task, 75, f"Classifier 正在逐题审计（知识标签候选: {len(subject_kps)} 个）...", stage_log, "classify_start")
    difficulty_mismatches = 0
    answer_errors = 0
    for idx, q in enumerate(reviewed):
        classification = _classifier_tag(q, subject_kps, target_difficulty=difficulty)
        q["detected_difficulty"] = classification.get("detected_difficulty", difficulty)
        q["difficulty_match"] = classification.get("difficulty_match", True)
        q["difficulty_mismatch_reason"] = classification.get("difficulty_mismatch_reason", "")
        q["knowledge_tags"] = classification.get("knowledge_tags", [])
        q["question_type"] = classification.get("question_type", q.get("q_type", "objective"))
        q["subjective_type"] = classification.get("subjective_type", q.get("subjective_type"))
        q["answer_correct"] = classification.get("answer_correct", True)
        q["answer_accuracy_note"] = classification.get("answer_accuracy_note", "")
        q["bloom_level"] = classification.get("bloom_level", "understand")
        # difficulty_level 锁定为人工指定的目标难度，不被 Classifier 修改
        q["difficulty_level"] = difficulty
        if not q["difficulty_match"]:
            difficulty_mismatches += 1
            logger.warning(
                "Classifier difficulty mismatch kp=%s detected=%s target=%s reason=%s",
                q.get("kp_code", "?"), q["detected_difficulty"], difficulty,
                q.get("difficulty_mismatch_reason", "")[:200],
            )
        if not q["answer_correct"]:
            answer_errors += 1
            logger.warning(
                "Classifier answer error kp=%s note=%s",
                q.get("kp_code", "?"), q.get("answer_accuracy_note", "")[:200],
            )

    # ── 批次多样性报告 ──
    _update_task(task, 85, "Classifier 正在生成批次多样性报告...", stage_log, "classify_batch")
    diversity_report = _classifier_batch_report(reviewed, subject_kps, difficulty)
    stage_log.append({
        "stage": "classify_done",
        "count": len(reviewed),
        "difficulty_mismatches": difficulty_mismatches,
        "answer_errors": answer_errors,
        "diversity_report": diversity_report,
        "timestamp": str(timezone.now()),
    })
    _update_task(task, 95, f"审计完成：{difficulty_mismatches} 难度不匹配, {answer_errors} 答案存疑", stage_log, "classify_done")

    # ── 写入结果 ──
    task.result = {
        "questions": reviewed,
        "stages": stage_log,
        "summary": {
            "total_generated": len(reviewed),
            "avg_quality_score": round(sum(q.get("review_score", 0) for q in reviewed) / max(len(reviewed), 1), 3),
            "iteration_distribution": iteration_stats,
            "knowledge_points": [k.name for k in kps],
        },
    }
    task.status = "completed"
    task.progress = 100
    task.finished_at = timezone.now()
    task.save()

    all_questions.extend(reviewed)

    # ── 创建审核任务 ──
    ContentPipelineTask.objects.create(
        task_type="ai_generate",
        status="review",
        title=f"[待审核] {task.title}",
        description=f"对抗性出题完成，{len(reviewed)} 道题待管理员审核入库",
        payload={"source_task_id": task.id, "questions_preview": reviewed[:5]},
        result={
            "questions": reviewed,
            "stages": stage_log,
            "summary": {
                "total_generated": len(reviewed),
                "avg_quality_score": round(sum(q.get("review_score", 0) for q in reviewed) / max(len(reviewed), 1), 3),
                "iteration_distribution": iteration_stats,
                "knowledge_points": [k.name for k in kps],
            },
        },
        progress=100,
        created_by=task.created_by,
    )


def _classifier_batch_report(questions: List[Dict], kps: List[KnowledgePoint], difficulty: str) -> Dict:
    """Classifier 批次多样性报告：跨题去重 + 整体评价。"""
    if len(questions) <= 1:
        return {"similar_pairs": [], "overall_assessment": "仅 1 道题，无需批次分析。"}

    system_prompt = (
        "你是学科题目质量评估专家。对一批已生成的题目进行批次级别分析。\n\n"
        "【分析维度】\n"
        "1. 相似题目检测：找出高度相似或重复的题目对。相似指考察相同概念、仅换了数字/名称/措辞。\n"
        "2. 整体评价：100 字以内总结本批次题目的优缺点。\n\n"
        "调用 submit_diversity_report 提交报告。"
    )
    questions_summary = []
    for i, q in enumerate(questions):
        questions_summary.append(
            f"[{i}] {q.get('kp_code', '?')} | {q.get('question', '')[:120]} | "
            f"bloom={q.get('bloom_level', '?')} | detected_diff={q.get('detected_difficulty', '?')}"
        )
    prompt = (
        f"【目标难度】{difficulty}\n\n"
        f"【全部题目】\n" + "\n".join(questions_summary) + "\n\n"
        f"请完成批次分析：检测相似题目对、给出整体评价。"
    )
    try:
        result = AIService.structured_output(
            system_prompt=system_prompt,
            user_prompt=prompt,
            schema=BATCH_DIVERSITY_REPORT_SCHEMA,
            tool_name="submit_diversity_report",
            tool_description="提交批次多样性报告",
            temperature=0.2,
            max_tokens=2048,
            operation="pipeline.classifier",
        )
        return result or {"similar_pairs": [], "overall_assessment": ""}
    except Exception as exc:
        logger.warning("Batch diversity report failed: %s", exc)
        return {"similar_pairs": [], "overall_assessment": ""}


def _update_task(task, progress, status_text, stage_log, stage_name):
    task.progress = progress
    payload = task.payload or {}
    payload["stages"] = stage_log
    payload["current_stage"] = stage_name
    payload["status_text"] = status_text
    task.payload = payload
    task.save(update_fields=["progress", "payload", "updated_at"])


# ── AI Agent 函数 ────────────────────────────────────────────────

AUTHOR_SYSTEM_PROMPT = """\
你是学科命题专家。根据知识点核心概念和学科标准命题。

【命题准则】
1. 知识点精准：每道题必须紧扣目标知识点的核心概念，不得偏题或泛化到无关领域。
2. 难度定义（所有题目必须严格遵守目标难度）：
   - entry：概念识记，纯记忆型，单步结论
   - easy：基础理解 + 1-2 步直接推理，干扰项较弱
   - normal：概念+情境结合，2-3 步推理，干扰项有迷惑性
   - hard：跨章节或多模型联动，至少 3 步严谨推理，干扰项高相似
   - extreme：高压综合题，模型选择/条件变化/现实约束，需严密论证与批判性分析
3. 题型规范：
   - objective（客观选择）：4 个选项（A/B/C/D），只有一个正确答案，干扰项要有迷惑性但非明显错误。
   - subjective:noun（名词解释）：要求解释核心概念，答案需包含定义+特征+学科意义。
   - subjective:short（简答）：要求分点作答，答案需包含关键论点+简要论证。
   - subjective:essay（论述）：要求综合分析，答案需包含背景+分析框架+核心论点+结论。
   - subjective:calculate（计算）：给出实际数据，要求计算并解释结果含义。
4. LaTeX 规范：所有数学公式使用 $...$ 包裹，如 $E(R_i) = R_f + \\beta_i[E(R_m) - R_f]$。
5. 答案完整：客观题给出正确答案字母并附简要解析，主观题给出完整参考答案和判分要点。
6. 难度锁定：所有题目的 difficulty_level 必须严格等于目标难度，不得自行偏离。同一知识点可从不同角度考察，但难度一致。

调用 submit_questions 提交题目列表，每道题为一个 JSON 对象包含 question/q_type/subjective_type/options/answer/grading_points/difficulty_level 字段。"""


def _get_subject_knowledge_points(kps: List[KnowledgePoint], institution=None) -> List[KnowledgePoint]:
    """获取与已选 KP 同科目的所有知识点，作为 Classifier 知识标签候选。"""
    subjects = set(k.subject for k in kps if k.subject)
    if not subjects:
        return kps
    qs = KnowledgePoint.objects.filter(subject__in=subjects)
    if institution:
        from django.db.models import Q
        qs = qs.filter(Q(institution=institution) | Q(institution__isnull=True))
    return list(qs.order_by('subject', 'code'))


def _difficulty_label(d: str) -> str:
    return {"entry": "入门", "easy": "简单", "normal": "适中", "hard": "困难", "extreme": "极限"}.get(d, d)


def _author_generate(kps: List[KnowledgePoint], q_per_kp: int, difficulty: str = "normal", types: Optional[List[str]] = None) -> List[Dict]:
    """Author Agent：按人工指定的难度和题型从知识点资料生成候选题目。"""
    system_prompt = PromptManager.get_prompt("AI_QUESTION_AUTHOR", AUTHOR_SYSTEM_PROMPT)

    types_list = types or []
    type_hint = ""
    if types_list:
        type_labels = []
        for t in types_list:
            if t == 'objective':
                type_labels.append('客观选择题')
            elif t == 'subjective:noun':
                type_labels.append('名词解释')
            elif t == 'subjective:short':
                type_labels.append('简答题')
            elif t == 'subjective:essay':
                type_labels.append('论述题')
            elif t == 'subjective:calculate':
                type_labels.append('计算题')
        if type_labels:
            type_hint = f"\n题型限制：只生成以下题型：{'、'.join(type_labels)}。\n"

    difficulty_label = _difficulty_label(difficulty)

    questions = []
    for kp in kps:
        prompt = (
            f"【目标知识点】\n"
            f"名称：{kp.name}\n"
            f"描述：{kp.description or '（请根据学科大纲理解该知识点的标准内容）'}\n"
            f"编码：{kp.code}\n\n"
            f"【出题要求】\n"
            f"目标难度：{difficulty_label}（{difficulty}）\n"
            f"所有 {q_per_kp} 道题目的 difficulty_level 必须严格为 {difficulty}，不得自行偏离。{type_hint}\n"
            f"调用 submit_questions 提交题目。"
        )
        try:
            result = AIService.structured_output(
                system_prompt=system_prompt,
                user_prompt=prompt,
                schema=AUTHOR_OUTPUT_SCHEMA,
                tool_name="submit_questions",
                tool_description="提交生成的题目列表",
                temperature=0.7,
                max_tokens=8192,
                operation="pipeline.author",
            )
            if result is None:
                logger.warning("Author structured_output returned None for kp=%s", kp.code)
            q_list = (result or {}).get("questions", [])
            if isinstance(q_list, list):
                for q in q_list:
                    q["kp_code"] = kp.code
                    q["kp_name"] = kp.name
                    q["kp_id"] = kp.id
                questions.extend(q_list)
        except Exception as exc:
            logger.warning("Author generation failed for kp=%s: %s", kp.code, exc)

    return questions


REVIEWER_SYSTEM_PROMPT = """\
你是学科命题审核专家，负责对每道题进行严格的对抗性质控审查。
你的职责是：找出题目的漏洞、不严谨之处、与学科大纲的偏差，并给出可操作的修改建议。

注意：你只关注题目的教学质量，不审计难度——难度合规由后续的 Classifier 专门负责。

【审查维度】（每项 0.0-1.0 分）
1. discrimination（区分度）：题目是否能有效区分掌握者和未掌握者？
   高分 = 需要真正理解概念才能答对，而非依靠排除法或常识猜测。
2. clarity（表述清晰度）：题干是否无歧义？选项是否互斥？主观题是否明确了作答范围和字数？
   扣分项：题干含混、选项重叠、主观题指示不清、LaTeX 语法错误。
3. coverage（知识覆盖度）：题目是否准确命中目标知识点的核心内容？
   扣分项：偏题、考查边缘细节而非核心概念、与学科大纲无关。

【综合评分规则】
- score = (discrimination + clarity + coverage) / 3
- 任一维度低于 0.4 时，score 不得超过 0.5（硬性不通过）
- 存在 LaTeX 语法错误扣 0.2 分（从 score 中直接扣除）
- 客观题答案不在选项中，score 直接为 0

【feedback 要求】
必须给出具体的、可操作的修改建议。格式如下：
- 如果通过（score >= 0.7）：指出题目亮点和微小优化建议
- 如果不通过（score < 0.7）：明确指出哪几个维度不达标、具体问题是什么、如何修改

【研究工具】
在评审前，你可以调用以下工具获取额外信息来辅助判断：
- lookup_knowledge_point_definition: 查询目标知识点的标准定义和范围，用于验证 coverage 维度。
- search_similar_questions: 搜索同知识点下已有题目，检查是否与现有题目雷同或重复。
不需要研究时可直接评审。评审完成后，调用 submit_review 提交评审结果。"""

def _get_reviewer_tool_executor(institution=None):
    """Reviewer research tool executor: lookup KP definition + search similar questions."""
    import json
    from quizzes.models import KnowledgePoint, Question

    def execute(tool_name: str, args: dict) -> str:
        try:
            if tool_name == "lookup_knowledge_point_definition":
                code = (args.get('code') or '').strip()
                qs = KnowledgePoint.objects.filter(code=code)
                if institution:
                    from django.db.models import Q
                    qs = qs.filter(Q(institution=institution) | Q(institution__isnull=True))
                kp = qs.first()
                if kp:
                    return json.dumps({
                        "code": kp.code, "name": kp.name,
                        "subject": kp.subject or '',
                        "description": (kp.description or '')[:500],
                        "level": kp.level,
                    }, ensure_ascii=False)
                return json.dumps({"error": f"KnowledgePoint code={code} not found"}, ensure_ascii=False)
            elif tool_name == "search_similar_questions":
                kp_code = (args.get('kp_code') or '').strip()
                limit = min(int(args.get('limit', 5)), 10)
                qs = Question.objects.filter(
                    knowledge_point__code=kp_code,
                )
                if institution:
                    qs = qs.filter(institution=institution)
                questions = [
                    {"id": q['id'], "text": (q['text'] or '')[:300],
                     "q_type": q['q_type'], "answer": (q['correct_answer'] or '')[:200]}
                    for q in qs.values('id', 'text', 'q_type', 'correct_answer')[:limit]
                ]
                return json.dumps({"found": len(questions), "questions": questions}, ensure_ascii=False)
            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)
    return execute


def _reviewer_evaluate(question: Dict, institution=None) -> Dict:
    """Reviewer Agent: from 3 dimensions (v4-pro + thinking + agentic)."""
    from ai_engine.tools import get_reviewer_research_tools

    system_prompt = PromptManager.get_prompt("AI_QUESTION_REVIEWER", REVIEWER_SYSTEM_PROMPT)

    # 构建选项文本（客观题必须有选项）
    options = question.get('options')
    options_text = ""
    if options:
        if isinstance(options, list):
            options_text = "\n".join(options)
        elif isinstance(options, dict):
            options_text = "\n".join(f"{k}. {v}" for k, v in sorted(options.items()))

    grading_points = question.get('grading_points') or '无'
    if isinstance(grading_points, list):
        grading_points = '\n'.join(grading_points)
    prompt = (
        f"【待审题目】\n"
        f"题干：{question.get('question') or '（未填写）'}\n"
        f"题型：{question.get('q_type') or '？'}/{question.get('subjective_type') or ''}\n"
        f"{f'选项：\n{options_text}\n' if options_text else ''}"
        f"参考答案：{question.get('answer') or '（未填写）'}\n"
        f"判分点：{grading_points}\n"
        f"目标知识点：{question.get('kp_name')} ({question.get('kp_code', '')})\n\n"
        f"先判断是否需要查知识点定义或已有题目，再调用 submit_review 提交评审结果。"
    )

    try:
        research_tools = get_reviewer_research_tools()
        tool_executor = _get_reviewer_tool_executor(institution=institution)
        result = AIService.agentic_structured_output(
            system_prompt=system_prompt,
            user_prompt=prompt,
            schema=REVIEWER_OUTPUT_SCHEMA,
            tool_name="submit_review",
            tool_description="Submit review result with 3-dimension scores and feedback",
            research_tools=research_tools,
            tool_executor=tool_executor,
            temperature=0.2,
            max_tokens=4096,
            operation="pipeline.reviewer",
            max_tool_rounds=5,
        )
        if result is None:
            logger.warning("Reviewer agentic_structured_output returned None")
            return {"score": 0.0, "feedback": "[System Error] Reviewer returned empty", "dimensions": {}}
        return {
            "score": float(result.get("score", 0.5)),
            "feedback": str(result.get("feedback", "")),
            "dimensions": result.get("dimensions", {}),
        }
    except Exception as exc:
        logger.warning("Reviewer failed: %s", exc)
        return {"score": 0.0, "feedback": f"[System Error] Reviewer failed: {exc}", "dimensions": {}}


def _author_revise(question: Dict, feedback: str) -> Dict:
    """Author 根据 Reviewer 反馈修改题目。"""
    system_prompt = PromptManager.get_prompt("AI_QUESTION_AUTHOR", (
        "你是学科命题专家。Reviewer 已审出题目中的问题，现在请根据反馈逐条修改。\n\n"
        "【修改原则】\n"
        "1. 逐条响应 Reviewer 的每一条反馈，不得遗漏或敷衍。\n"
        "2. 如果 Reviewer 指出表述不清：重写题目使其无歧义，确保选项互斥、主观题指令明确。\n"
        "3. 如果 Reviewer 指出偏离知识点：重新设计题目使其聚焦于目标知识点的核心概念。\n"
        "4. 保持题目原有的题型、知识点归属、难度等级和基本结构，只做质量改进。\n"
        "5. 修改后自行检查一次：是否满足命题规范、LaTeX 是否正确、答案是否完整。\n\n"
        "调用 submit_revised_question 提交修改后的题目。"
    ))
    prompt = (
        f"【原题目】\n{json.dumps(question, ensure_ascii=False)}\n\n"
        f"【Reviewer 反馈】\n{feedback}\n\n"
        f"请逐条修改上述问题，调用 submit_revised_question 提交修改后的完整题目。"
    )
    try:
        result = AIService.structured_output(
            system_prompt=system_prompt,
            user_prompt=prompt,
            schema=AUTHOR_REVISE_OUTPUT_SCHEMA,
            tool_name="submit_revised_question",
            tool_description="提交修改后的完整题目",
            temperature=0.6,
            max_tokens=8192,
            operation="pipeline.author_revise",
        )
        if result is None:
            logger.warning("Author revise structured_output returned None")
        revised = (result or {}).get("revised_question", {})
        if isinstance(revised, dict) and (revised.get("question") or revised.get("answer")):
            for k in ("kp_code", "kp_name", "kp_id", "review_score", "review_feedback", "iteration"):
                if k in question:
                    revised[k] = question[k]
            return revised
        logger.warning("Author revise returned empty question for kp=%s, keeping original", question.get("kp_code"))
    except Exception as exc:
        logger.warning("Author revise failed: %s", exc)
    return question


CLASSIFIER_SYSTEM_PROMPT = """\
你是学科题目审计专家。对每道已通过 Reviewer 质量审查的题目，完成三层审计：

【第一层：答案正确性审计】
- 客观题：检查正确答案字母对应的选项是否确实是该题的唯一正确答案。干扰项是否确实错误（而非模棱两可）。
- 主观题：检查参考答案是否覆盖了核心要点、是否存在事实性错误或遗漏关键论据。
- answer_correct=true 表示答案无事实错误；false 表示存在事实错误或严重遗漏。
- answer_accuracy_note 仅在 answer_correct=false 时填写，说明具体问题。

【第二层：认知层级与难度审计】
- 难度定义：
  - entry：概念识记，纯记忆型，单步结论
  - easy：基础理解 + 1-2 步直接推理，干扰项较弱
  - normal：概念+情境结合，2-3 步推理，干扰项有迷惑性
  - hard：跨章节或多模型联动，至少 3 步严谨推理，干扰项高相似
  - extreme：高压综合题，模型选择/条件变化/现实约束，需严密论证与批判性分析
- 你会被告知目标难度。根据题目内容判断实际难度 → detected_difficulty。
- 实际难度与目标一致 → difficulty_match=true；偏离 → difficulty_match=false 并在 difficulty_mismatch_reason 中说明。
- 不得修改题目的 difficulty_level，只记录检测结果。
- Bloom 认知层级（独立于难度）：
  - remember：识记——回忆事实、术语、基本概念
  - understand：理解——解释、归纳、比较、推断
  - apply：应用——用已知方法/公式解决新问题
  - analyze：分析——拆解结构、识别关系、区分因果
  - evaluate：评价——基于标准做出判断、论证观点
  - create：创造——综合信息产生新方案、设计新模型
- 标注题目实际要求的最高认知层级 → bloom_level。

【第三层：知识标签与题型分类】
- knowledge_tags：从全学科知识点列表中选出题目实际涉及的知识点（1-5 个编码），按相关度排序。
  题目可能跨知识点——这是你存在的核心价值，不限于题目归属的单个 KP。
- question_type：objective（客观选择）或 subjective（主观题）。
- subjective_type：noun/short/essay/calculate，仅主观题填写（客观题为 null）。

调用 submit_classification 提交审计结果。"""

def _classifier_tag(question: Dict, kps: List[KnowledgePoint], target_difficulty: str = "normal") -> Dict:
    """Classifier Agent：三层审计——答案正确性 + 认知层级/难度合规 + 知识标签/题型分类。"""
    system_prompt = PromptManager.get_prompt("AI_QUESTION_CLASSIFIER", CLASSIFIER_SYSTEM_PROMPT)
    kp_list = ", ".join(f"{k.code or '?'}:{k.name}" for k in kps)
    prompt = (
        f"【全学科知识点标签候选】\n{kp_list}\n\n"
        f"【目标难度】{target_difficulty}（{_difficulty_label(target_difficulty)}）\n\n"
        f"【待审计题目】\n"
        f"题干：{question.get('question')}\n"
        f"题型：{question.get('q_type')}\n"
        f"答案：{question.get('answer')}\n"
        f"判分点：{question.get('grading_points', '无')}\n"
        f"声明难度：{question.get('difficulty_level', target_difficulty)}\n\n"
        f"请完成三层审计：\n"
        f"1. 答案是否事实正确？\n"
        f"2. 实际难度是否匹配目标难度 {target_difficulty}？Bloom 认知层级是？\n"
        f"3. 从全学科标签候选集中找出题目实际涉及的知识点，确认题型分类。\n"
        f"调用 submit_classification 提交审计结果。"
    )
    try:
        result = AIService.structured_output(
            system_prompt=system_prompt,
            user_prompt=prompt,
            schema=CLASSIFIER_OUTPUT_SCHEMA,
            tool_name="submit_classification",
            tool_description="提交题目审计结果（答案正确性+难度审计+Bloom层级+知识标签+题型分类）",
            temperature=0.1,
            max_tokens=2048,
            operation="pipeline.classifier",
        )
        if result is None:
            logger.warning("Classifier structured_output returned None")
        return result or {}
    except Exception as exc:
        logger.warning("Classifier failed: %s", exc)
        return {
            "detected_difficulty": target_difficulty, "difficulty_match": False,
            "difficulty_mismatch_reason": f"[系统错误] Classifier 审计失败: {exc}",
            "knowledge_tags": [],
            "question_type": "objective", "subjective_type": None,
            "answer_correct": False, "answer_accuracy_note": f"[系统错误] Classifier 审计失败，无法验证答案正确性",
            "bloom_level": "understand",
        }
