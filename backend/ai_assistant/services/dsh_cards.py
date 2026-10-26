"""User-visible cards derived from authorized business results, never model HTML."""
import time


def data_card(title, items, cta=None, note=''):
    payload = {'title': title, 'items': items, 'note': note}
    if cta:
        payload['cta'] = {'label': cta[0], 'link': cta[1]}
    return {'type': 'data_card', 'payload': payload}


def item(label, value, link=None):
    row = {'label': str(label or ''), 'value': str(value)}
    if link:
        row['action_link'] = link
    return row


def build_tool_card(name, result):
    if name in {'get_learning_stats', 'get_knowledge_mastery_map', 'get_due_reviews', 'get_recent_practice_result', 'get_practice_questions'}:
        return result.get('visual')
    if name == 'search_courses':
        return data_card('相关课程', [item(c['title'], '打开课程', f"/course/{int(c['id'])}")
            for c in result.get('courses', [])[:10]], ('课程中心', '/courses'),
            '' if result.get('courses') else '没有找到匹配课程。')
    if name == 'search_asr':
        return data_card('课程讲稿来源', [item(f"{s['course_title']} · {s['start_time']}～{s['end_time']}",
            s['text'], f"/course/{int(s['course_id'])}") for s in result.get('segments', [])[:10]],
            note='' if result.get('segments') else '没有找到匹配片段。')
    if name in {'lookup_question', 'get_user_wrong_questions', 'search_similar_questions'}:
        rows = [result] if name == 'lookup_question' else result.get('questions', [])
        questions = []
        for row in rows[:10]:
            question = {k: row[k] for k in ('id', 'q_type', 'kp_name', 'options') if k in row}
            question['text'] = row.get('text', row.get('question_preview', ''))
            if name in {'lookup_question', 'get_user_wrong_questions'}:
                question['answer'] = row.get('correct_answer', row.get('answer', ''))
            questions.append(question)
        titles = {'lookup_question': '题目与参考答案', 'get_user_wrong_questions': '我的错题',
                  'search_similar_questions': '同类题预览'}
        return {'type': 'question_preview', 'payload': {'title': titles[name], 'questions': questions}}
    if name == 'get_study_status':
        current = result.get('current_session') or {}
        expired = (current.get('status') == 'active' and current.get('timer_end_ts')
                   and current['timer_end_ts'] <= time.time())
        if expired:
            return data_card('自习专注状态', [item('当前状态', '本次自习计时已到期'),
                item('今日专注', f"{result.get('today_total_focus_minutes', 0)} 分钟"),
                item('昨日专注', f"{result.get('yesterday_total_focus_minutes', 0)} 分钟")],
                ('进入自习室', '/study'), '已到期任务计入今日汇总；仅统计自习室计时。')
        return data_card('自习专注状态', [item('当前任务', current.get('task_name') or '暂无进行中的自习'),
            item('本次已专注', f"{result.get('current_elapsed_minutes', 0)} 分钟"),
            item('今日专注', f"{result.get('today_total_focus_minutes', 0)} 分钟"),
            item('昨日专注', f"{result.get('yesterday_total_focus_minutes', 0)} 分钟")],
            ('进入自习室', '/study'), '仅统计自习室计时，不包含听课、做题记录或线下学习。')
    if name == 'get_focus_history':
        return data_card('自习专注历史', [item(row['date'], f"{row['focus_minutes']} 分钟 · {row['sessions_count']} 次")
            for row in result.get('history', [])[-30:]], ('进入自习室', '/study'),
            '仅汇总已结束的自习计时；当前进行中的任务请查看自习专注状态。')
    if name == 'get_learning_sessions':
        return data_card('实际学习记录', [item(f"{s['started_at'][:16]} · {'听课' if s['kind'] == 'video' else '做题'}",
            f"{round(s['active_seconds'] / 60, 1)} 分钟") for s in result.get('sessions', [])[:10]],
            ('学习记录', '/report-card'), result.get('notes', ''))
    if name == 'get_exam_history':
        return data_card('我的考试记录', [item(e['created_at'][:10], f"{e['total_score']}/{e['max_score']}",
            f"/tests/results/{int(e['id'])}") for e in result.get('exams', [])[:10]],
            ('习题训练', '/tests'), '' if result.get('exams') else '暂无考试记录。')
    if name == 'get_user_weak_points':
        return data_card('薄弱知识点', [item(p['kp_name'], f"错答 {p['total_wrong']} 次")
            for p in result.get('weak_points', [])[:10]], ('查看学习报告', '/report-card'),
            '' if result.get('weak_points') else '暂无可供分析的错题记录。')
    if name == 'search_knowledge_tree':
        return data_card('知识点查询', [item(p['name'], p.get('subject') or '未分类')
            for p in result.get('results', [])[:15]], note='' if result.get('results') else '没有找到匹配知识点。')
    if name == 'get_knowledge_difficulty_analysis':
        return data_card('Memorix 复习分析', [item(p['name'], f"难度 {p['avg_difficulty']} · 稳定性 {p['avg_stability']} 天")
            for p in result.get('knowledge_points', [])[:10]], note=result.get('summary', ''))
    if name == 'get_report_card':
        accuracy = result.get('last_accuracy')
        return data_card('学习报告', [item('已练题目', result.get('attempted_questions', 0)),
            item('最近正确率', f'{accuracy}%' if accuracy is not None else '暂无数据'),
            item('已掌握题目', result.get('mastered_count', 0))], ('查看完整报告', '/report-card'))
    if name == 'get_my_achievements':
        return data_card('我的成就', [item(a['name'], a.get('description', '已解锁'))
            for a in result.get('unlocked', [])[:8]], ('查看成就', '/achievements'),
            '' if result.get('unlocked') else '尚未解锁成就。')
    return None
