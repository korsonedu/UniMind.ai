"""A small answer-time view of a validated memory packet; raw evidence stays stored."""

REALIZATION = {
    'layout': {
        'diagram': '用实际可见的图示帮助理解；适合函数时使用受控函数图，不能只声明已图解。',
        'worked_example': '呈现分步代入算例，可使用分步卡片；需要提示时只展开前半步骤，给学生留下待完成部分。',
    },
    'depth': {
        'hint': '给下一步引导。提示深度不自动等于禁止答案；当前明确要求独立作答时，文字和所有展示卡片均不得公布待求结果。',
        'full': '给出完整推导，答案披露仍遵守当前用户明确要求。',
    },
    'anchor': {
        'timestamp': '引用本轮授权材料中确切的片段时间；未提供时间时明确说明缺失，不猜测时间或链接。',
        'formula': '从当前任务已给的关系式展开，说明代入或变形与该关系式的联系。',
    },
}


def execution_view(packet):
    if not packet:
        return packet
    return {key: packet[key] for key in ('protocol', 'features', 'decision', 'relation_conflicts', 'learner_patterns', 'notice') if key in packet}


def realization_view(packet):
    """Research candidate; ordinary answer entries retain execution_view."""
    view = execution_view(packet)
    if not view:
        return view
    decision = packet.get('decision', {})
    readout = {key: REALIZATION[key][value] for key, value in decision.get('behavior', {}).items()
        if key in REALIZATION and value in REALIZATION[key]}
    if readout or decision.get('conflicts') or packet.get('relation_conflicts'):
        view['realization'] = {'behavior': readout,
            'precedence': '当前明确要求优先，保留用户事实的优先级；这里只解释尚未被覆盖的计划槽，不授予工具或资料权限。',
            'clarify': sorted(decision.get('conflicts', {})), 'encoding_conflicts': packet.get('relation_conflicts', []),
            'conflict_rule': '未被当前明确要求消解的同级冲突先澄清，不能靠历史或默认讲法任选一种。'}
    return view
