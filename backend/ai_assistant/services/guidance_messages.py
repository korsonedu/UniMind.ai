"""Translations of fixed teaching suggestions; learner content is passed as values."""

EN = {
    "该复习“{0}”了。回顾本次学习记录，再做一次简短复测。": "Time to review “{0}”. Revisit your work and try a short reassessment.",
    "恢复学习后再根据实际情况继续。": "Resume learning, then continue based on your current situation.",
    "与小宇核对当前目标和接下来的学习。": "Review your current goal and next steps with XiaoYu.",
    "保留用户当前安排，不因任务完成自动恢复或结束目标。": "Keep your current plan. Completing a task does not automatically resume or finish the goal.",
    "先明确一段可开始的学习，并准备一个能了解起点的任务。": "Choose an activity you can start and prepare a task to assess your starting point.",
    "还没有实际任务结果；可以先做起点检查，不要求先建知识地图。": "There are no actual task results yet. Start with an initial check; a knowledge map is not required first.",
    "后续对话已有新的实际观察，沿最近教学反馈继续。": "The conversation contains newer observations. Continue from the latest teaching feedback.",
    "等待这次评价完成，再根据原作答继续；不用重复提交。": "Wait for this evaluation, then continue from your original answer. No need to submit again.",
    "评价尚未完成，不能当作学习成果。": "The evaluation is unfinished and cannot be treated as a learning outcome.",
    "先恢复这次未完成的评价，已成功的部分继续保留。": "Retry the unfinished evaluation. Completed results will be kept.",
    "评价失败或部分完成不代表答错，也不触发重复记分。": "Failed or partial evaluation does not mean an incorrect answer and does not trigger duplicate scoring.",
    "先完成“{0}”，了解起点和需要哪些帮助。": "Complete “{0}” first to assess your starting point and the help you need.",
    "现有任务内容不可用，先和小宇重新准备。": "The current task is unavailable. Prepare a new one with XiaoYu.",
    "尚无作答结果；安排起点检查，不预先判断掌握。": "There are no answer results yet. Arrange an initial check without assuming mastery.",
    "最近完成“{0}”，本次评价 {1}/{2}。": "Recently completed “{0}”, evaluated at {1}/{2}.",
    "这是模型依据标准的评价，尚未独立复核。": " This model evaluation follows the criteria and has not been independently reviewed.",
    "先询问最具体的卡点，换一种讲解方式并缩小任务，再准备一次检查。": "Identify the specific difficulty, change the explanation, and narrow the task before checking again.",
    "先对照原作答和评价标准解释缺口，再准备更小的同类任务。": "Explain the gap against the original answer and criteria, then prepare a smaller task of the same kind.",
    "连续两次任务出现缺口，优先改变教学策略。": "Two consecutive tasks show a gap. Adjust the teaching approach first.",
    "当前成果存在缺口，不能用完成题数代替理解。": "The current work shows a gap. The number of completed questions does not establish understanding.",
    "根据起点继续“{0}”，结合讲解与实际任务了解表现。": "Continue with “{0}” from your starting point, using explanations and actual tasks to assess progress.",
    "根据这次起点表现准备一段针对性讲解与任务，再检查能否独立运用。": "Use the initial results to prepare a focused explanation and task, then check independent application.",
    "起点任务用于选择教学起点，单次结果不直接判定掌握。": "An initial task helps choose where to begin teaching. One result does not establish mastery.",
    "回顾必要讲解后，准备不同的任务再检查；如实记录作答时获得的帮助。": "Review the necessary explanation, then check with a different task. Record any help received accurately.",
    "有提示、逐步引导、帮助未知或只有一次支持观察，都不足以推断稳定独立表现。": "Hints, step-by-step guidance, unknown assistance, or a single supporting observation do not establish consistent independent performance.",
    "可以继续“{0}”，保留之后的复习与换情境检查。": "Continue with “{0}”, keeping later reviews and checks in new contexts.",
    "本轮已有不同任务的支持观察，和小宇约定延迟复测或下一阶段；整个目标仍需另行核对。": "Different tasks have provided supporting observations. Plan a delayed reassessment or the next stage with XiaoYu; the overall goal still needs a separate check.",
    "同阶段已有不同任务的独立支持观察，只作为推进教学的建议，不自动标记掌握。": "Different tasks in this stage provide independent supporting observations. This suggests moving teaching forward and does not automatically mark mastery.",
    "最近完成“{0}”，得分 {1}/{2}。": "Recently completed “{0}”, scored {1}/{2}.",
    "先复盘错误与解析，再继续：": "Review mistakes and explanations first, then continue: ",
    "接下来：": "Next: ",
    "本轮任务已完成，按复习时间重新检查，并和小宇核对下一阶段。": "This round of tasks is complete. Recheck at the review time and discuss the next stage with XiaoYu.",
    "有任务内容当前不可用，请和小宇重新安排，已有成绩继续保留。": "Some tasks are unavailable. Replan with XiaoYu; existing scores will be kept."
}


def guidance_text(source, language, *values):
    text = EN.get(source, source) if language == 'en' else source
    return text.format(*values)
