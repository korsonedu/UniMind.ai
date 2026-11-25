"""Memory collectors retry once only for explicit transport failures."""
import json
import sys
from unittest.mock import patch

import pytest

from ai_assistant.services.dsh_runtime import DshUnavailable
from ai_assistant.services.dsh_tasks import run_structured


@pytest.mark.parametrize('operation', ['assistant.prism_observe','assistant.prism_complete'])
def test_memory_retry_is_bounded_and_does_not_retry_invalid_business_schema(settings,tmp_path,operation):
    settings.DEBUG=True
    settings.UNIMIND_DSH_PYTHON=sys.executable
    settings.UNIMIND_DSH_STATE_DIR=str(tmp_path)
    settings.UNIMIND_DSH_FIXTURE_URL='http://127.0.0.1:8912/v1/messages'
    valid={'features':[],'behavior':[]}
    if operation.endswith('complete'):valid['memories']=[]
    retry={'status':503,'code':'INCOMPLETE_TASK','retryable':True}
    for responses,expected_count,success in [([retry,{'status':200,'result':valid}],2,True),
            ([retry,retry],2,False),([{'status':503,'code':'COLLECTOR_FAILED'}],1,False),
            ([{'status':200,'result':{'invalid':True}}],1,False)]:
        with patch('ai_assistant.services.dsh_tasks.subprocess.Popen') as popen:
            process=popen.return_value.__enter__.return_value
            process.returncode=0
            process.communicate.side_effect=[(json.dumps(body).encode(),b'') for body in responses]
            if success:assert run_structured(operation,'合成观察')==valid
            else:
                with pytest.raises(DshUnavailable):run_structured(operation,'合成观察')
            assert popen.call_count==expected_count
            for call in process.communicate.call_args_list:
                policy=json.loads(call.args[0])['context']['model_policy']
                assert policy['max_requests']==1 and policy['operation']==operation


def test_prepared_completion_has_a_smaller_validated_output_contract(settings,tmp_path):
    settings.DEBUG=True
    settings.UNIMIND_DSH_PYTHON=sys.executable
    settings.UNIMIND_DSH_STATE_DIR=str(tmp_path)
    settings.UNIMIND_DSH_FIXTURE_URL='http://127.0.0.1:8912/v1/messages'
    sizes=[]
    for prepared in (False,True):
        result={'behavior':[],'memories':[]}
        if not prepared:result['features']=[]
        with patch('ai_assistant.services.dsh_tasks.subprocess.Popen') as popen:
            process=popen.return_value.__enter__.return_value
            process.returncode=0
            process.communicate.return_value=(json.dumps({'status':200,'result':result}).encode(),b'')
            assert run_structured('assistant.prism_complete','合成完成观察',reuse_prepared=prepared)==result
            context=json.loads(process.communicate.call_args.args[0])['context']
            schema=context['tools'][0]['function']['parameters']
            assert ('features' in schema['properties']) is not prepared
            assert ('bindings' in schema['properties']) is not prepared
            assert context['model_policy']['max_requests']==1
            sizes.append(len(json.dumps(context,ensure_ascii=False)))
            if prepared:
                process.communicate.return_value=(json.dumps({'status':200,'result':{**result,'features':[]}}).encode(),b'')
                with pytest.raises(DshUnavailable):
                    run_structured('assistant.prism_complete','合成完成观察',reuse_prepared=True)
    assert sizes[1]<sizes[0]
