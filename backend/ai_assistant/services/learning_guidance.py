"""Cross-domain teaching suggestions from task evidence, not mastery declarations."""
from datetime import datetime


def _time(task):
    return str((task.get('summary') or {}).get('completed_at') or (task.get('summary') or {}).get('created_at') or task['created_at'])


def _supported(task):
    score = task.get('summary') or {}
    return bool(score.get('max_score') and score['total_score'] / score['max_score'] >= .6)


def _fingerprint(task):
    return tuple(''.join(question['text'].split()).casefold() for question in task.get('payload', {}).get('questions', []))


def teaching_guidance(state, tasks, *, progress_at=None):
    stage_ids = {stage['id'] for stage in state.plan.get('stages', [])}
    tasks = [task for task in tasks if task['stage_id'] in stage_ids]
    result = {'status': 'start', 'feedback': '', 'next_action': state.next_action,
              'task_id': None, 'stage_id': state.current_stage, 'reason': '', 'stalled': False}
    if state.status != 'active':
        return {**result, 'status': 'inactive', 'feedback': state.feedback,
                'next_action': '恢复学习后再根据实际情况继续。' if state.status == 'paused' else '与小宇核对当前目标和接下来的学习。',
                'reason': '保留用户当前安排，不因任务完成自动恢复或结束目标。'}
    if not tasks:
        return {**result, 'feedback': state.feedback, 'next_action': state.next_action or '先明确一段可开始的学习，并准备一个能了解起点的任务。',
                'reason': '还没有实际任务结果；可以先做起点检查，不要求先建知识地图。'}
    activities = [datetime.fromisoformat(_time(task)) for task in tasks if task.get('summary')]
    if progress_at and (not activities or progress_at > max(activities)) and state.feedback:
        return {**result, 'status': 'continue', 'feedback': state.feedback, 'next_action': state.next_action,
                'reason': '后续对话已有新的实际观察，沿最近教学反馈继续。'}
    processing = [task for task in tasks if task['status'] == 'processing']
    if processing:
        task = processing[-1]
        return {**result, 'status': 'awaiting', 'task_id': task['id'], 'stage_id': task['stage_id'],
                'next_action': '等待这次评价完成，再根据原作答继续；不用重复提交。',
                'reason': '评价尚未完成，不能当作学习成果。'}
    failed = [task for task in tasks if task['status'] in ('failed', 'partial')]
    if failed:
        task = failed[-1]
        return {**result, 'status': 'retry', 'task_id': task['id'], 'stage_id': task['stage_id'],
                'next_action': '先恢复这次未完成的评价，已成功的部分继续保留。',
                'reason': '评价失败或部分完成不代表答错，也不触发重复记分。'}
    completed = sorted((task for task in tasks if task['status'] == 'completed'), key=_time)
    ready = [task for task in tasks if task['status'] == 'ready']
    if not completed:
        task = next((task for task in ready if task.get('purpose') == 'diagnostic'), ready[0] if ready else None)
        return {**result, 'task_id': task['id'] if task else None, 'stage_id': task['stage_id'] if task else state.current_stage,
                'next_action': f"先完成“{task['title']}”，了解起点和需要哪些帮助。" if task else '现有任务内容不可用，先和小宇重新准备。',
                'reason': '尚无作答结果；安排起点检查，不预先判断掌握。'}
    latest = completed[-1]
    score = latest['summary']
    feedback = f"最近完成“{latest['title']}”，本次评价 {score['total_score']}/{score['max_score']}。"
    if score.get('label_source') == 'model_rubric_grade':
        feedback += '这是模型依据标准的评价，尚未独立复核。'
    result.update(feedback=feedback, stage_id=latest['stage_id'])
    by_id = {task['id']: task for task in tasks}
    def chain_root(task):
        while task.get('source_task_id') in by_id:
            task = by_id[task['source_task_id']]
        return task['id']
    same_stage = [task for task in completed if task['stage_id'] == latest['stage_id'] and (
        (task.get('node_id') == latest['node_id'] and task.get('mode') == latest.get('mode')) if latest.get('node_id') else chain_root(task) == chain_root(latest))]

    recent = same_stage[-2:]
    if not _supported(latest):
        stalled = len(recent) == 2 and all(not _supported(task) for task in recent)
        child = next((task for task in ready if task.get('source_task_id') == latest['id']), None)
        return {**result, 'status': 'remediate', 'task_id': child['id'] if child else None, 'stage_id': child['stage_id'] if child else latest['stage_id'], 'stalled': stalled,
                'next_action': '先询问最具体的卡点，换一种讲解方式并缩小任务，再准备一次检查。' if stalled else '先对照原作答和评价标准解释缺口，再准备更小的同类任务。',
                'reason': '连续两次任务出现缺口，优先改变教学策略。' if stalled else '当前成果存在缺口，不能用完成题数代替理解。'}
    if latest.get('purpose') == 'diagnostic':
        child = next((task for task in ready if task.get('source_task_id') == latest['id']), None)
        return {**result, 'status': 'continue', 'task_id': child['id'] if child else None,
                'stage_id': child['stage_id'] if child else latest['stage_id'],
                'next_action': f"根据起点继续“{child['title']}”，结合讲解与实际任务了解表现。" if child else '根据这次起点表现准备一段针对性讲解与任务，再检查能否独立运用。',
                'reason': '起点任务用于选择教学起点，单次结果不直接判定掌握。'}
    independent = [task for task in same_stage if _supported(task) and task['assistance'] == 'independent']
    distinct = {key for task in independent if (key := _fingerprint(task))}
    if latest['assistance'] != 'independent' or len(distinct) < 2:
        child = next((task for task in ready if task.get('source_task_id') == latest['id'] and task.get('purpose') == 'recheck'), None)
        return {**result, 'status': 'recheck', 'task_id': child['id'] if child else None,
                'next_action': '回顾必要讲解后，准备不同的任务再检查；如实记录作答时获得的帮助。',
                'reason': '有提示、逐步引导、帮助未知或只有一次支持观察，都不足以推断稳定独立表现。'}
    task = next((task for task in ready if task['stage_id'] != latest['stage_id']), ready[0] if ready else None)
    return {**result, 'status': 'continue' if task else 'review', 'task_id': task['id'] if task else None,
            'stage_id': task['stage_id'] if task else latest['stage_id'],
            'next_action': f"可以继续“{task['title']}”，保留之后的复习与换情境检查。" if task else '本轮已有不同任务的支持观察，和小宇约定延迟复测或下一阶段；整个目标仍需另行核对。',
            'reason': '同阶段已有不同任务的独立支持观察，只作为推进教学的建议，不自动标记掌握。'}
