"""
对抗性 AI 出题管线 (Adversarial Question Generation Pipeline)

三 AI Agent 迭代博弈：
  Author    — 根据知识点资料生成候选题目
  Reviewer  — 从难度、区分度、歧义性、知识覆盖四个维度打分
  Classifier — 打知识标签、难度标签、题型标签

每个题目质量分 < 0.7 会退给 Author 修改，最多 3 轮迭代。
管线追踪写入 ContentPipelineTask，前端实时查看进度。
"""

import json
import logging
from typing import Any, Dict, List, Optional

from django.utils import timezone

from ai_service import AIService
from core.prompt_manager import PromptManager
from quizzes.models import ContentPipelineTask, KnowledgePoint

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 3
QUALITY_THRESHOLD = 0.7
QUESTIONS_PER_KP = 3


def run_adversarial_pipeline(
    kp_ids: List[int],
    created_by,
    task_title: str = "",
    questions_per_kp: int = QUESTIONS_PER_KP,
    types: Optional[List[str]] = None,
) -> int:
    """启动对抗性出题管线，返回 pipeline_task_id。"""
    kps = list(KnowledgePoint.objects.filter(id__in=kp_ids))
    if not kps:
        raise ValueError("未找到有效知识点")

    types_list = types or []

    task = ContentPipelineTask.objects.create(
        task_type="ai_generate",
        status="running",
        title=task_title or "对抗性出题管线",
        description=f"知识点: {', '.join(k.name for k in kps[:5])}",
        payload={
            "kp_ids": kp_ids,
            "questions_per_kp": questions_per_kp,
            "max_iterations": MAX_ITERATIONS,
            "quality_threshold": QUALITY_THRESHOLD,
            "types": types_list,
            "stages": [],
        },
        progress=0,
        created_by=created_by,
        started_at=timezone.now(),
    )

    # 异步执行（通过 Celery）
    from quizzes.tasks import run_adversarial_pipeline_task
    run_adversarial_pipeline_task.delay(
        task_id=task.id,
        kp_ids=[k.id for k in kps],
        questions_per_kp=questions_per_kp,
        types=types_list,
    )
    return task.id


def _execute_pipeline(task: ContentPipelineTask, kps: List[KnowledgePoint], q_per_kp: int, types: Optional[List[str]] = None):
    """执行对抗性出题管线。"""
    all_questions = []
    stage_log = []

    # ── Stage 1: Author 批量生成 ──
    _update_task(task, 5, "Author 正在生成候选题目...", stage_log, "author_start")
    drafts = _author_generate(kps, q_per_kp, types=types)
    stage_log.append({"stage": "author_generated", "count": len(drafts), "timestamp": str(timezone.now())})
    _update_task(task, 30, f"Author 生成了 {len(drafts)} 道候选题目", stage_log, "author_done")

    # ── Stage 2: Reviewer 评分 + 迭代 ──
    _update_task(task, 40, "Reviewer 正在评审...", stage_log, "review_start")
    reviewed = []
    iteration_stats = {i: 0 for i in range(1, MAX_ITERATIONS + 1)}

    for draft in drafts:
        for iteration in range(1, MAX_ITERATIONS + 1):
            review_result = _reviewer_evaluate(draft)
            draft["review_score"] = review_result["score"]
            draft["review_feedback"] = review_result["feedback"]
            draft["review_dimensions"] = review_result.get("dimensions", {})
            draft["iteration"] = iteration

            if review_result["score"] >= QUALITY_THRESHOLD:
                reviewed.append(draft)
                iteration_stats[iteration] = iteration_stats.get(iteration, 0) + 1
                break
            elif iteration < MAX_ITERATIONS:
                # 退回 Author 修改
                draft = _author_revise(draft, review_result["feedback"])
            else:
                # 超过最大轮次，仍保留（标记为低质量）
                draft["quality_warning"] = True
                reviewed.append(draft)
                iteration_stats[iteration] = iteration_stats.get(iteration, 0) + 1

    stage_log.append({
        "stage": "review_done",
        "total": len(reviewed),
        "iteration_distribution": iteration_stats,
        "avg_score": round(sum(q.get("review_score", 0) for q in reviewed) / max(len(reviewed), 1), 3),
        "timestamp": str(timezone.now()),
    })
    _update_task(task, 70, f"Reviewer 完成，{len(reviewed)} 道题通过 ({iteration_stats} 轮分布)", stage_log, "review_done")

    # ── Stage 3: Classifier 打标 ──
    _update_task(task, 80, "Classifier 正在打标签...", stage_log, "classify_start")
    for q in reviewed:
        classification = _classifier_tag(q, kps)
        q["difficulty_level"] = classification.get("difficulty_level", "normal")
        q["knowledge_tags"] = classification.get("knowledge_tags", [])
        q["question_type"] = classification.get("question_type", "objective")
    stage_log.append({"stage": "classify_done", "count": len(reviewed), "timestamp": str(timezone.now())})
    _update_task(task, 95, "打标完成", stage_log, "classify_done")

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
2. 难度分层：entry=概念识记，easy=简单应用，normal=综合分析，hard=跨知识点综合，extreme=前沿/超纲。
3. 题型规范：
   - objective（客观选择）：4 个选项（A/B/C/D），只有一个正确答案，干扰项要有迷惑性但非明显错误。
   - subjective:noun（名词解释）：要求解释核心概念，答案需包含定义+特征+学科意义。
   - subjective:short（简答）：要求分点作答，答案需包含关键论点+简要论证。
   - subjective:essay（论述）：要求综合分析，答案需包含背景+分析框架+核心论点+结论。
   - subjective:calculate（计算）：给出实际数据，要求计算并解释结果含义。
4. LaTeX 规范：所有数学公式使用 $...$ 包裹，如 $E(R_i) = R_f + \\beta_i[E(R_m) - R_f]$。
5. 答案完整：客观题给出正确答案字母并附简要解析，主观题给出完整参考答案和判分要点。
6. 避免重复：每个知识点下各题应在不同角度或不同难度层次考察，拒绝同义反复。

输出纯 JSON 数组（不要 markdown 代码块包裹）：
[{"question": "题干", "q_type": "objective|subjective", "subjective_type": "noun|short|essay|calculate|null", "options": ["A. ...", "B. ...", "C. ...", "D. ..."]|null, "answer": "正确答案", "grading_points": ["判分点1", "判分点2"]|null, "difficulty_level": "entry|easy|normal|hard|extreme"}]"""

def _author_generate(kps: List[KnowledgePoint], q_per_kp: int, types: Optional[List[str]] = None) -> List[Dict]:
    """Author Agent：从知识点资料生成候选题目。"""
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

    questions = []
    for kp in kps:
        prompt = (
            f"【目标知识点】\n"
            f"名称：{kp.name}\n"
            f"描述：{kp.description or '（请根据学科大纲理解该知识点的标准内容）'}\n"
            f"编码：{kp.code}\n\n"
            f"【出题要求】\n"
            f"请为该知识点生成 {q_per_kp} 道题目，尽量覆盖不同难度。{type_hint}\n"
            f"严格遵守输出 JSON 格式，不要输出任何 JSON 之外的说明文字。"
        )
        try:
            content = AIService.simple_chat_text(
                system_prompt=system_prompt,
                user_prompt=prompt,
                temperature=0.7,
                max_tokens=3000,
                operation="pipeline.author",
            )
            parsed = AIService.extract_json(content) or []
            if isinstance(parsed, list):
                for q in parsed:
                    q["kp_code"] = kp.code
                    q["kp_name"] = kp.name
                    q["kp_id"] = kp.id
                questions.extend(parsed)
        except Exception as exc:
            logger.warning("Author generation failed for kp=%s: %s", kp.code, exc)

    return questions


REVIEWER_SYSTEM_PROMPT = """\
你是学科命题审核专家，负责对每道题进行严格的对抗性质控审查。
你的职责是：找出题目的漏洞、不严谨之处、与学科大纲的偏差，并给出可操作的修改建议。

【审查维度】（每项 0.0-1.0 分）
1. difficulty（难度合理性）：题目实际难度是否匹配声明的 difficulty_level？过难或过易都要指出。
2. discrimination（区分度）：题目是否能有效区分掌握者和未掌握者？
   高分 = 需要真正理解概念才能答对，而非依靠排除法或常识猜测。
3. clarity（表述清晰度）：题干是否无歧义？选项是否互斥？主观题是否明确了作答范围和字数？
   扣分项：题干含混、选项重叠、主观题指示不清、LaTeX 语法错误。
4. coverage（知识覆盖度）：题目是否准确命中目标知识点的核心内容？
   扣分项：偏题、考查边缘细节而非核心概念、与学科大纲无关。

【综合评分规则】
- score = (difficulty + discrimination + clarity + coverage) / 4
- 任一维度低于 0.4 时，score 不得超过 0.5（硬性不通过）
- 存在 LaTeX 语法错误扣 0.2 分（从 score 中直接扣除）
- 客观题答案不在选项中，score 直接为 0

【feedback 要求】
必须给出具体的、可操作的修改建议。格式如下：
- 如果通过（score >= 0.7）：指出题目亮点和微小优化建议
- 如果不通过（score < 0.7）：明确指出哪几个维度不达标、具体问题是什么、如何修改

输出纯 JSON（不要 markdown 包裹）：
{"score": 0.XX, "feedback": "具体修改建议", "dimensions": {"difficulty": 0.XX, "discrimination": 0.XX, "clarity": 0.XX, "coverage": 0.XX}}"""

def _reviewer_evaluate(question: Dict) -> Dict:
    """Reviewer Agent：从四个维度评估题目质量。"""
    system_prompt = PromptManager.get_prompt("AI_QUESTION_REVIEWER", REVIEWER_SYSTEM_PROMPT)

    # 构建选项文本（客观题必须有选项）
    options = question.get('options')
    options_text = ""
    if options:
        if isinstance(options, list):
            options_text = "\n".join(options)
        elif isinstance(options, dict):
            options_text = "\n".join(f"{k}. {v}" for k, v in sorted(options.items()))

    prompt = (
        f"【待审题目】\n"
        f"题干：{question.get('question')}\n"
        f"题型：{question.get('q_type')}/{question.get('subjective_type', '')}\n"
        f"声明难度：{question.get('difficulty_level', 'normal')}\n"
        f"{f'选项：\n{options_text}\n' if options_text else ''}"
        f"参考答案：{question.get('answer')}\n"
        f"判分点：{question.get('grading_points', '无')}\n"
        f"目标知识点：{question.get('kp_name')} ({question.get('kp_code', '')})\n\n"
        f"请逐维度审查并输出评分 JSON。"
    )

    try:
        content = AIService.simple_chat_text(
            system_prompt=system_prompt,
            user_prompt=prompt,
            temperature=0.2,
            max_tokens=1500,
            operation="pipeline.reviewer",
        )
        result = AIService.extract_json(content) or {}
        return {
            "score": float(result.get("score", 0.5)),
            "feedback": str(result.get("feedback", "")),
            "dimensions": result.get("dimensions", {}),
        }
    except Exception as exc:
        logger.warning("Reviewer failed: %s", exc)
        return {"score": 0.6, "feedback": "", "dimensions": {}}


def _author_revise(question: Dict, feedback: str) -> Dict:
    """Author 根据 Reviewer 反馈修改题目。"""
    system_prompt = PromptManager.get_prompt("AI_QUESTION_AUTHOR", (
        "你是学科命题专家。Reviewer 已审出题目中的问题，现在请根据反馈逐条修改。\n\n"
        "【修改原则】\n"
        "1. 逐条响应 Reviewer 的每一条反馈，不得遗漏或敷衍。\n"
        "2. 如果 Reviewer 指出难度不匹配：调整题目深度或 complexity 使其匹配声明难度。\n"
        "3. 如果 Reviewer 指出表述不清：重写题目使其无歧义，确保选项互斥、主观题指令明确。\n"
        "4. 如果 Reviewer 指出偏离知识点：重新设计题目使其聚焦于目标知识点的核心概念。\n"
        "5. 保持题目原有的题型、知识点归属和基本结构，只做质量改进。\n"
        "6. 修改后自行检查一次：是否满足命题规范、LaTeX 是否正确、答案是否完整。\n\n"
        "输出纯 JSON 对象（不要 markdown 包裹），包含修改后的完整题目的所有字段。"
    ))
    prompt = (
        f"【原题目】\n{json.dumps(question, ensure_ascii=False)}\n\n"
        f"【Reviewer 反馈】\n{feedback}\n\n"
        f"请逐条修改上述问题，输出修改后的完整题目 JSON。"
    )
    try:
        content = AIService.simple_chat_text(
            system_prompt=system_prompt,
            user_prompt=prompt,
            temperature=0.6,
            max_tokens=2000,
            operation="pipeline.author_revise",
        )
        revised = AIService.extract_json(content) or {}
        if isinstance(revised, dict):
            for k in ("kp_code", "kp_name", "kp_id", "review_score", "review_feedback", "iteration"):
                if k in question:
                    revised[k] = question[k]
            return revised
    except Exception as exc:
        logger.warning("Author revise failed: %s", exc)
    return question


CLASSIFIER_SYSTEM_PROMPT = """\
你是学科题目分类专家，负责为每道已通过审查的题目精确标注元数据。

【标注规范】
1. difficulty_level（难度等级）：
   - entry：概念识记，纯记忆型（如什么是货币乘数）
   - easy：简单应用，单步推导或单一概念（如计算简单存款乘数）
   - normal：综合分析，需结合多个概念（如分析货币政策对利率的影响）
   - hard：跨知识点综合，需建立分析框架（如用 IS-LM 分析财政政策效果）
   - extreme：前沿或超纲内容，需要深度洞察（如对比不同汇率制度下的货币政策有效性）
2. knowledge_tags（知识标签）：
   - 从给定知识点列表中选择最匹配的 1-3 个标签（使用知识点编码）
   - 如果题目涉及多个知识点，按相关度排序
3. question_type（题型分类）：
   - objective：客观选择题
   - subjective：主观题（需进一步指定 subjective_type）
4. subjective_type（主观题子类型，仅 question_type=subjective 时填写）：
   - noun：名词解释  short：简答题  essay：论述题  calculate：计算题

输出纯 JSON（不要 markdown 包裹）：
{"difficulty_level": "normal", "knowledge_tags": ["ch01_sec02_kp03"], "question_type": "objective", "subjective_type": null}"""

def _classifier_tag(question: Dict, kps: List[KnowledgePoint]) -> Dict:
    """Classifier Agent：打知识点标签、难度标签、题型标签。"""
    system_prompt = PromptManager.get_prompt("AI_QUESTION_CLASSIFIER", CLASSIFIER_SYSTEM_PROMPT)
    kp_list = ", ".join(f"{k.code or '?'}:{k.name}" for k in kps)
    prompt = (
        f"【可用知识点】\n{kp_list}\n\n"
        f"【待标注题目】\n"
        f"题干：{question.get('question')}\n"
        f"题型：{question.get('q_type')}\n"
        f"答案：{question.get('answer')}\n"
        f"当前难度标注：{question.get('difficulty_level', 'normal')}\n\n"
        f"请输出标注 JSON（以当前难度标注为参考，如有偏差请纠正）。"
    )
    try:
        content = AIService.simple_chat_text(
            system_prompt=system_prompt,
            user_prompt=prompt,
            temperature=0.1,
            max_tokens=800,
            operation="pipeline.classifier",
        )
        return AIService.extract_json(content) or {}
    except Exception as exc:
        logger.warning("Classifier failed: %s", exc)
        return {"difficulty_level": "normal", "knowledge_tags": [], "question_type": "objective"}
