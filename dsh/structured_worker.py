"""One temporary DSH structured task, no persistent student session or callbacks."""
from contextlib import ExitStack
import json
from pathlib import Path
import sys

from deepseek_harness import DeepSeekHarness
from gateway import task_gateway
from worker import reserve_slot


ROOT = Path(__file__).resolve().parent


class RetryableTask(Exception):
    """Provider stream was malformed; the caller may retry once."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def turn_error(result):
    for event in reversed(result.events):
        if event.get('type') != 'turn/end':
            continue
        reason = (event.get('data') or {}).get('reason') or {}
        error = reason.get('error') or {}
        if reason.get('kind') == 'error' and isinstance(error.get('code'), str):
            return error['code']
    return None


def execute(payload):
    context, model = payload['context'], payload['model']
    tool = context['tools'][0]['function']
    with ExitStack() as stack:
        if not reserve_slot(stack, payload['state_dir']):
            raise RuntimeError('Runtime capacity exhausted')
        audit = None
        if model['mode'] == 'deepseek-official':
            directory = Path(payload['state_dir']).parent / 'usage'
            directory.mkdir(mode=0o700, exist_ok=True)
            audit = directory / 'gateway-usage.jsonl'
        with task_gateway(context, model['url'], model['key'], model['mode'], audit) as gateway:
            with DeepSeekHarness(dsh_home=payload['home'], cwd=payload['home'],
                patches=(str(ROOT / 'profile.patch.yml'), str(ROOT / 'structured.patch.yml')),
                provider='deepseek-official', model=context['model_policy']['model'],
                base_url=gateway['url'], api_key=gateway['credential'], max_tokens=context['model_policy']['max_tokens'],
                request_timeout_seconds=90, initialize_timeout_seconds=20,
                reasoning_effort=context['model_policy'].get('thinking'),
                env={'UNIMIND_DSH_TASK_INSTRUCTION': context['task_instruction'], 'UNIMIND_DSH_STRUCTURED_TOOL': json.dumps(tool, ensure_ascii=False),
                     'UNIMIND_DSH_RESEARCH': json.dumps({key: context.get(key) for key in ('research_tools', 'research_groups', 'bridge')}, ensure_ascii=False)}) as harness:
                result = harness.run(payload['prompt'])
        if result.finish_reason != 'completed' or not gateway['requests'] or any(request['status'] != 'completed' for request in gateway['requests']):
            if result.finish_reason == 'error' and turn_error(result) == 'MALFORMED_RESPONSE':
                raise RetryableTask('MALFORMED_RESPONSE')
            raise RuntimeError('Incomplete structured task')
        calls, outputs = set(), []
        for event in result.events:
            data = event.get('data', {})
            if event.get('type') == 'tool/call' and data.get('name') == tool['name']:
                calls.add(data['callId'])
            if event.get('type') == 'tool/result' and data.get('message', {}).get('toolCallId') in calls:
                if data['message'].get('isError'):
                    raise RuntimeError('Collector failed')
                outputs.append(data.get('meta', {}).get('unimindStructured'))
        if len(outputs) != 1 or len(calls) != 1 or not isinstance(outputs[0], dict):
            raise RuntimeError('Expected one successful collector')
        return outputs[0]


if __name__ == '__main__':
    try:
        response = {'status': 200, 'result': execute(json.load(sys.stdin))}
    except RetryableTask as exc:
        response = {'status': 503, 'error': 'DSH 结构化任务未完成。', 'code': exc.code, 'retryable': True}
    except Exception:
        response = {'status': 503, 'error': 'DSH 结构化任务未完成。'}
    print(json.dumps(response, ensure_ascii=False, allow_nan=False))
