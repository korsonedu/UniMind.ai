"""The small, published checkpoint between two XiaoYu turns."""
import re
import unicodedata


SHORT_ACCEPTANCES = frozenset({
    '默认', '按默认来', '就按你说的', '好', '好的', '行', '可以', '就这样',
    'ok', 'okay', 'yes', 'sure', 'sounds good', 'default', 'use defaults',
})
ACKNOWLEDGEMENTS = frozenset({'好', '好的', '明白了', 'ok', 'okay', 'got it'})
OPTION_NUMBER = re.compile(r'(?:选\s*|第\s*)?([0-9]{1,3})(?:\s*项)?')
DEFAULT_REPLIES = frozenset({'默认', '按默认来', 'default', 'use defaults'})
STEP_COUNT = re.compile(r'分\s*([0-9]{1,2}|[一二三四五六七八九十]{1,3})\s*(?:步|次|轮)|(?:in|over)\s+([0-9]{1,2})\s+(?:steps|turns)', re.I)
CONTINUATION_NAME = 'save_learning_continuation'

CONTINUATION_TOOL = {'type': 'function', 'function': {
    'name': CONTINUATION_NAME,
    'description': ('单独调用，用本次调用的正文结束本轮，并保存一个尚未完成的当前学习任务。若确实缺少阻止开工的信息，填写一个具体问题，'
                    '可附互斥选项。学生已提供的信息和可自行选用的默认设置直接使用。正式确认走原流程。'
                    '若已完成当前请求或只是问候、闲聊，直接回复。'),
    'parameters': {'type': 'object', 'additionalProperties': False, 'required': ['goal', 'next_step'], 'properties': {
        'goal': {'type': 'string', 'maxLength': 220, 'pattern': r'\S'},
        'known': {'type': 'array', 'maxItems': 12, 'items': {'type': 'string', 'maxLength': 200, 'pattern': r'\S'},
                  'description': '保留所有仍适用的已确认信息，更新学生本轮明确更正的内容。'},
        'next_step': {'type': 'string', 'maxLength': 320, 'pattern': r'\S'},
        'reply': {'type': 'string', 'maxLength': 3000, 'description': '显示给学生的实际进展或可用结果。'},
        'question': {'type': 'string', 'maxLength': 300, 'pattern': r'\S'},
        'question_reason': {'enum': ['missing_requirement', 'student_requested_choice'],
                            'description': '有问题时填写。缺少必要信息，或学生明确要求自己选择。'},
        'options': {'type': 'array', 'minItems': 2, 'maxItems': 4,
                    'items': {'type': 'string', 'maxLength': 140, 'pattern': r'\S'}},
        'default_choice': {'type': 'integer', 'minimum': 1, 'maximum': 4,
                           'description': '只有学生明确要求先看选项并由其决定时，才可以建议默认项。用从 1 开始的编号。'},
    }},
}}


def short_reply(message):
    return unicodedata.normalize('NFKC', message).strip().rstrip('。.!').strip().casefold()


def resolve_reply(checkpoint, message):
    reply = short_reply(message)
    if not checkpoint.get('question'):
        return {'continue': True} if reply in {'继续', '接着来', 'continue', 'go on'} else None
    options = checkpoint.get('options', [])
    if options and (match := OPTION_NUMBER.fullmatch(reply)):
        number = int(match[1])
        return {'choice': options[number - 1]} if 1 <= number <= len(options) else {'missing_choice': True}
    for option in options:
        if reply == short_reply(option):
            return {'choice': option}
    if reply in SHORT_ACCEPTANCES:
        if default := checkpoint.get('default_choice'):
            return {'choice': options[default - 1]}
        return {'use_defaults': True} if reply in DEFAULT_REPLIES else {'missing_choice': True}
    return None


def paced_step(message, previous, resolution):
    if resolution and resolution.get('continue') and previous.get('pace'):
        return {**previous['pace'], 'step': previous['pace']['step'] + 1}
    if not re.search(r'每(?:次|轮)(?:只|仅|讲一|做一|完成一)|(?:我说|回复|等我).{0,12}继续|one (?:step|part) at a time', message, re.I):
        return None
    match = STEP_COUNT.search(unicodedata.normalize('NFKC', message))
    if not match:
        return None
    digits = '零一二三四五六七八九'
    number = match[1] or match[2]
    if number.isascii():
        total = int(number)
    elif '十' in number:
        tens, ones = number.split('十', 1)
        if len(tens) > 1 or len(ones) > 1 or '十' in ones:
            return None
        total = 10 * (digits.index(tens) if tens else 1) + (digits.index(ones) if ones else 0)
    elif len(number) == 1:
        total = digits.index(number)
    else:
        return None
    if total >= 2:
        return {'step': 1, 'total': total, 'request': message[:1500]}


def checkpoint_question(checkpoint, english):
    question = checkpoint['question']
    if options := checkpoint.get('options'):
        question += '\n\n' + '\n'.join(f'{index}. {option}' for index, option in enumerate(options, 1))
    if default := checkpoint.get('default_choice'):
        question += f'\n\nReply “default” to choose {default}.' if english else f'\n\n回复「默认」会选择第 {default} 项。'
    return question


def prepare_checkpoint(arguments, previous, resolution, english, message_id, pace=None):
    question = arguments.get('question', '').strip()
    options = [option.strip() for option in arguments.get('options', [])]
    default = arguments.get('default_choice')
    reply = arguments.get('reply', '').strip()
    reason = arguments.get('question_reason')
    if pace and (question or not reply):
        return {'error': '请直接给出本轮约定的这一步，沿用已确认条件。'}
    if (not (reply or question) or bool(question) != bool(reason) or (options and not question)
            or (default is not None and (default > len(options) or reason != 'student_requested_choice'))
            or len({short_reply(option) for option in options}) != len(options)):
        return {'error': '请提供已完成的正文，或一个确实需要的问题及原因。可用的默认设置应直接使用。'}
    if resolution and question and (not reply or short_reply(question) == short_reply(previous.get('question', ''))):
        return {'error': '学生已给出决定，请先执行并交付当前约定的下一步。'}
    goal = arguments['goal'].strip()
    same_goal = previous and (resolution or short_reply(goal) == short_reply(previous['goal']))
    known = [value.strip() for value in arguments.get('known', [])]
    if resolution:
        known = [*previous.get('known', []), *known]
        if choice := resolution.get('choice'):
            known.append(choice)
    checkpoint = {'goal': previous['goal'] if same_goal else goal, 'known': list(dict.fromkeys(known))[-12:],
                  'next_step': arguments['next_step'].strip(),
                  'origin_message_id': previous['origin_message_id'] if same_goal else message_id}
    if pace:
        if pace['step'] == pace['total']:
            return {'checkpoint': None, 'reply': reply}
        checkpoint['pace'] = pace
    if question:
        checkpoint.update(question=question, question_reason=reason, options=options, default_choice=default)
        reply = '\n\n'.join(filter(None, (reply, checkpoint_question(checkpoint, english))))
    return {'checkpoint': checkpoint, 'reply': reply}
