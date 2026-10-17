"""小宇数据工具的直出卡片。

工具在返回数据的同时生成一张卡片，省去模型再调用 render_visual 的一轮。
"""


def _percent(value) -> str:
    return f"{value}%" if value is not None else '—'


def build_learning_stats_visual(stats: dict) -> dict:
    items = []
    if stats.get('has_attempts'):
        items.extend([
            {'label': '已练题目', 'value': f"{stats.get('attempted_questions', 0)} 道"},
            {'label': '最近正确率', 'value': _percent(stats.get('last_accuracy')), 'emphasis': True},
        ])
        if stats.get('lifetime_accuracy') is not None:
            items.append({
                'label': '累计正确率（近似）',
                'value': _percent(stats.get('lifetime_accuracy')),
            })
        items.append({'label': '连续学习', 'value': f"{stats.get('study_streak_days', 0)} 天"})
    else:
        items.append({'label': '练习状态', 'value': '尚未开始'})

    mastery = stats.get('mastery') or {}
    if mastery.get('kp_count'):
        items.append({
            'label': '诊断掌握',
            'value': f"{mastery.get('mastered_kp_count', 0)}/{mastery.get('kp_count')} 个知识点",
        })
    else:
        items.append({'label': '诊断掌握', 'value': '尚未诊断', 'action_link': '/diagnostic'})

    payload = {
        'title': '学习概览',
        'subtitle': '仅统计已作答题目',
        'items': items,
        'note': '累计正确率按复习次数与错误次数估算；掌握度基于最近一次诊断。',
        'cta': (
            {'label': '查看成绩报告', 'link': '/report-card'}
            if stats.get('has_attempts')
            else {'label': '开始诊断', 'link': '/diagnostic'}
        ),
    }
    return {'type': 'data_card', 'payload': payload, 'priority': 'normal'}


def build_mastery_map_visual(mastery_map: dict, mastery: dict, subject: str = '') -> dict:
    kp_count = (mastery or {}).get('kp_count', 0)
    if not kp_count or not mastery_map:
        payload = {
            'title': '知识点掌握图谱',
            'subtitle': '基于诊断',
            'items': [
                {'label': '诊断状态', 'value': '尚未完成'},
                {'label': '掌握度来源', 'value': '最近一次诊断'},
            ],
            'note': '完成诊断后可按学科查看知识点掌握度。',
            'cta': {'label': '开始诊断', 'link': '/diagnostic'},
        }
        return {'type': 'data_card', 'payload': payload, 'priority': 'normal'}

    nodes = []
    seen = set()
    for kp_list in mastery_map.values():
        for kp in kp_list:
            kp_id = str(kp.get('kp_id') or '')
            if not kp_id or kp_id in seen:
                continue
            seen.add(kp_id)
            score = max(0.0, min(1.0, float(kp.get('mastery_score') or 0) / 100))
            nodes.append({
                'id': kp_id,
                'label': kp.get('kp_name') or kp_id,
                'mastery': round(score, 2),
            })
            if len(nodes) >= 24:
                break
        if len(nodes) >= 24:
            break

    highlights = [node['id'] for node in sorted(nodes, key=lambda item: item['mastery'])[:3]]
    payload = {
        'title': f'{subject} · 掌握图谱' if subject else '知识点掌握图谱',
        'nodes': nodes,
        'edges': [],
        'highlights': highlights,
        'note': '基于最近一次诊断；练习暂不更新掌握度。',
    }
    return {'type': 'knowledge_map', 'payload': payload, 'priority': 'normal'}


def build_due_reviews_visual(due: dict) -> dict:
    reviews = due.get('reviews') or []
    due_count = int(due.get('due_count') or 0)
    high_priority = sum(
        1 for review in reviews
        if (review.get('memorix_priority') or review.get('priority')) in ('critical', 'high')
    )

    if due_count:
        items = [
            {'label': '待复习题目', 'value': f'{due_count} 道', 'emphasis': True},
            {'label': '高优先级', 'value': f'{high_priority} 道'},
            {
                'label': '调度策略',
                'value': '自适应' if due.get('interval_policy') == 'memorix' else '固定间隔',
            },
        ]
        note = '根据间隔重复调度计算。'
        if len(reviews) < due_count:
            note += f'优先级统计基于本次返回的 {len(reviews)} 条。'
        cta = {
            'label': '开始复习',
            'link': '/tests/session?source=xiaoyu&preference=review_first',
        }
    else:
        items = [
            {'label': '待复习题目', 'value': '0 道'},
            {'label': '今日状态', 'value': '没有到期题目'},
        ]
        note = '根据间隔重复调度计算。'
        cta = {'label': '去练习', 'link': '/tests'}

    payload = {'title': '今日复习', 'items': items, 'note': note, 'cta': cta}
    return {'type': 'data_card', 'payload': payload, 'priority': 'normal'}
