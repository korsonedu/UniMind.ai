"""Adapt verified SDK tool events into a bounded set of UniMind cards."""
import json
import re


CARD_TYPES = {'data_card', 'knowledge_map', 'practice_result', 'question_preview', 'practice_quiz', 'diagnostic_quiz', 'faq_draft', 'latex_derivation', 'step_solution', 'function_graph', 'action_cards'}
INTERNAL_PATH = re.compile(r'/(?:courses|course/[1-9][0-9]*|tests(?:/results/[1-9][0-9]*|/session\?source=xiaoyu&preference=review_first)?|report-card|achievements|diagnostic|study|qa)')


def safe_links(value):
    if isinstance(value, list):
        return all(safe_links(item) for item in value)
    if isinstance(value, dict):
        action = value.get('action')
        if isinstance(action, dict):
            if action.get('type') == 'navigate':
                if not isinstance(action.get('url'), str) or not INTERNAL_PATH.fullmatch(action['url']):
                    return False
            elif action.get('type') != 'reply':
                return False
        return all((isinstance(item, str) and bool(INTERNAL_PATH.fullmatch(item)))
                   if key in {'link', 'href', 'action_link'} else safe_links(item)
                   for key, item in value.items())
    return True


def tool_cards(events, context):
    allowed = {t['function']['name'] for t in context.get('available_tools', context['tools'])}
    calls, cards = {}, []
    for event in events:
        data = event.get('data', {})
        if event.get('type') == 'tool/call' and data.get('name') in allowed:
            calls[data['callId']] = data['name']
        if event.get('type') != 'tool/result':
            continue
        message = data.get('message', {})
        name = calls.pop(message.get('toolCallId'), None)
        if not name or message.get('role') != 'tool' or message.get('isError'):
            continue
        failed = False
        for block in message.get('content', []):
            if block.get('type') != 'text':
                continue
            try:
                result = json.loads(block['text'])
            except (ValueError, KeyError):
                continue
            if isinstance(result, dict) and result.get('error'):
                failed = True
        meta = data.get('meta')
        visual = meta.get('unimindCard') if isinstance(meta, dict) else None
        if (not failed and isinstance(visual, dict) and visual.get('type') in CARD_TYPES
                and isinstance(visual.get('payload'), dict) and safe_links(visual)
                and (visual['type'] not in {'latex_derivation', 'step_solution', 'function_graph', 'action_cards'}
                     or name == 'present_learning_visual')):
            cards.append({'tool': name, 'type': visual['type'], 'payload': visual['payload']})
    return cards[:12]
