"""Public, provisional stream fields; never forward raw provider/SDK events."""
def text_delta(event):
    delta = event.get('delta', {})
    if event.get('type') == 'content_block_delta' and delta.get('type') == 'text_delta' and isinstance(delta.get('text'), str):
        return {'type': 'text_delta', 'text': delta['text'][:4096]}
    return None


def tool_status(event, allowed, calls):
    data = event.get('data', {})
    if event.get('type') == 'tool/call' and data.get('name') in allowed:
        calls[data['callId']] = data['name']
        return {'type': 'tool_status', 'name': data['name'], 'status': 'running'}
    if event.get('type') == 'tool/result':
        name = calls.pop(data.get('message', {}).get('toolCallId'), None)
        if name:
            return {'type': 'tool_status', 'name': name, 'status': 'finished'}
    return None
