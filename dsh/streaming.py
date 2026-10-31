"""Public, provisional stream fields; never forward raw provider/SDK events."""
import json


def text_delta(event):
    delta = event.get('delta', {})
    if event.get('type') == 'content_block_delta' and delta.get('type') == 'text_delta' and isinstance(delta.get('text'), str):
        return {'type': 'text_delta', 'text': delta['text'][:4096]}
    return None


def tool_status(event, allowed, calls):
    data = event.get('data', {})
    call_id = data.get('callId')
    if event.get('type') == 'tool/call' and data.get('name') in allowed and isinstance(call_id, str) and call_id:
        calls[call_id] = data['name']
        return {'type': 'tool_status', 'call_id': call_id, 'name': data['name'], 'status': 'running'}
    if event.get('type') == 'tool/result':
        message = data.get('message', {})
        call_id = message.get('toolCallId')
        name = calls.pop(call_id, None)
        if name:
            failed = bool(message.get('isError'))
            for block in message.get('content', []):
                if block.get('type') != 'text':
                    continue
                try:
                    result = json.loads(block.get('text', ''))
                except (ValueError, TypeError):
                    continue
                failed = failed or (isinstance(result, dict) and bool(result.get('error')))
            status = {'type': 'tool_status', 'call_id': call_id, 'name': name,
                      'status': 'failed' if failed else 'succeeded'}
            if failed:
                status['error'] = {'code': 'tool_failed', 'message': '学习工具执行失败，请稍后重试。'}
            return status
    return None
