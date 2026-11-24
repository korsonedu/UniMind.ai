"""Full knowledge build comparison using the installed DSH SDK and loopback models."""
import json
import os
import runpy
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from ai_assistant.services.dsh_runtime import DshUnavailable
from ai_engine import config
from knowledge_builder import pipeline
from knowledge_builder.models import BlockStepAtom, KnowledgeTreeBuild
from knowledge_builder.prompts import ask
from knowledge_builder.tasks import build_knowledge_tree
from knowledge_builder.tests.test_pipeline_e2e import SemanticFixture


@pytest.mark.django_db
@pytest.mark.skipif(not os.environ.get('ULR_COMPARE_DSH_PYTHON'), reason='optional DSH SDK loopback smoke')
def test_full_build_restart_and_resume_share_the_same_graph(auth_client, settings, tmp_path, monkeypatch):
    settings.DEBUG = True
    settings.UNIMIND_DSH_GENERATION_ENABLED = True
    settings.UNIMIND_DSH_PYTHON = os.environ['ULR_COMPARE_DSH_PYTHON']
    settings.UNIMIND_DSH_STATE_DIR = str(tmp_path)
    settings.UNIMIND_KB_ONLINE_AUTO_MOUNT = False
    fixture = SemanticFixture()
    inputs = {'legacy': [], 'ulr': []}
    embedding_calls = []
    paths = []
    emit_invalid = False

    def respond(engine, name, system, user):
        prefix = system.find('\n{')
        shared = json.JSONDecoder().raw_decode(system[prefix + 1:])[0] if prefix >= 0 else {}
        local = json.loads(user.split('\n', 1)[1])
        inputs[engine].append((name, shared, local))
        if emit_invalid and 'schema_error' not in local:
            return {'modules': []}
        return fixture.ai(tool_name=name, raise_on_error=True, system_prompt='\n' + json.dumps(shared),
                          user_prompt=user)

    def dsh_tools(request):
        name, = [tool['name'] for tool in request['tools']]
        message, = json.loads(request['messages'][0]['content'][0]['text'])
        return [(name, respond('legacy', name, request['system'], message['content']))]

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path == '/v1/embeddings':
                embedding_calls.append(payload['input'])
                output = fixture.http(config.EMBEDDING_BASE_URL + '/embeddings', json=payload).json()
            else:
                tool, = payload['tools']
                name = tool['function']['name']
                system, user = payload['messages']
                result = respond('ulr', name, system['content'], user['content'])
                output = {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [{
                    'id': name, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(result)}
                }]}}]}
            body = json.dumps(output).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def create():
        reply = auth_client.post('/api/knowledge-builder/', {'subject': '合成微积分',
            'requirements': {'learning_goal': '把极限与连续性连起来'}}, format='json')
        assert reply.status_code == 202, reply.data
        return KnowledgeTreeBuild.objects.get(pk=reply.data['id'])

    def stop(*_args):
        raise RuntimeError('synthetic interruption at stage six')

    def graph(build):
        return (
            list(build.modules.order_by('code').values('code', 'parent__code', 'title', 'path', 'depth', 'order')),
            list(build.atoms.order_by('code').values('code', 'module__code', 'name', 'goal_statement',
                'goal_type', 'key_elements', 'granularity_minutes')),
            list(build.atom_edges.order_by('from_atom__code', 'to_atom__code').values('from_atom__code', 'to_atom__code',
                'edge_strength', 'confidence', 'similarity', 'rationale')),
            list(build.blocks.order_by('code').values('code', 'short_title', 'is_entry_block', 'layer', 'node_shape',
                                                      'narrative_summary', 'contraction_group')),
            list(build.block_edges.order_by('from_block__code', 'to_block__code').values('from_block__code',
                'to_block__code', 'is_retained', 'edge_kind', 'directness_score', 'rationale')),
            list(BlockStepAtom.objects.filter(step__block__build=build)
                 .order_by('step__block__code', 'step__step_index', 'position').values('step__block__code',
                     'step__step_index', 'step__step_title', 'step__step_role', 'atom__code', 'membership_type')),
            list(build.cross_block_interfaces.order_by('from_atom__code', 'to_atom__code').values('from_atom__code',
                'to_atom__code', 'interface_role', 'bridge_explanation')),
        )

    with ExitStack() as services:
        dsh, dsh_requests = runpy.run_path(str(Path(settings.BASE_DIR).parent / 'dsh' / 'smoke.py'))['model_fixture']()
        services.callback(dsh.server_close)
        services.callback(dsh.shutdown)
        dsh.tool_response = dsh_tools
        settings.UNIMIND_DSH_FIXTURE_URL = f'http://127.0.0.1:{dsh.server_port}/v1/messages'
        provider = services.enter_context(ThreadingHTTPServer(('127.0.0.1', 0), Provider))
        Thread(target=provider.serve_forever, daemon=True).start()
        services.callback(provider.shutdown)
        url = f'http://127.0.0.1:{provider.server_port}/v1'
        monkeypatch.setenv('LLM_BASE_URL', url + '/chat/completions')
        monkeypatch.setenv('LLM_API_KEY', 'loopback-model')
        monkeypatch.setattr(config, 'EMBEDDING_BASE_URL', url)
        monkeypatch.setattr(config, 'EMBEDDING_API_KEY', 'loopback-embedding')
        monkeypatch.setattr(config, 'EMBEDDING_DIMENSIONS', 24)
        monkeypatch.setattr('knowledge_builder.views.build_knowledge_tree.delay', paths.append)

        graphs = []
        for engine in ('legacy', 'ulr'):
            settings.UNIMIND_LEARNING_RUNTIME = engine
            original = create()
            before = len(embedding_calls)
            with monkeypatch.context() as failure:
                failure.setattr(pipeline, '_plan_blocks', stop)
                with pytest.raises(RuntimeError, match='interruption'):
                    build_knowledge_tree(str(original.pk))
            original.refresh_from_db()
            assert original.status == 'FAILED' and not original.blocks.exists() and not original.atoms.exists()
            assert len(inputs[engine]) == 7 and len(embedding_calls) - before == 3
            queued = auth_client.post(f'/api/knowledge-builder/{original.pk}/resume/')
            assert queued.status_code == (202 if engine == 'ulr' else 409)
            retry = original if engine == 'ulr' else create()
            before = len(embedding_calls)
            assert build_knowledge_tree(str(retry.pk)) == str(retry.pk)
            assert len(embedding_calls) - before == (0 if engine == 'ulr' else 3)
            retry.refresh_from_db()
            assert retry.status == 'COMPLETED'
            graphs.append(graph(retry))
            assert paths[-1] == str(retry.pk)

        assert inputs['legacy'][:7] == inputs['ulr'][:7]
        assert inputs['legacy'][7:] == inputs['ulr']
        assert len(dsh_requests) == 17 and len(inputs['ulr']) == 10
        assert graphs[0] == graphs[1] and tuple(map(len, graphs[0])) == (4, 6, 5, 2, 1, 6, 1)

        settings.UNIMIND_LEARNING_RUNTIME = 'legacy'
        emit_invalid = True
        with pytest.raises(DshUnavailable):
            ask('outline_decompose', {'subject': '合成微积分'})
        assert len(dsh_requests) == 18 and dsh_requests[-1]['tools'][0]['name'] == 'outline_decompose'
        settings.UNIMIND_LEARNING_RUNTIME = 'ulr'
        assert ask('outline_decompose', {'subject': '合成微积分'}) == {'modules': fixture.modules()}
        assert len(inputs['ulr']) == 12
        assert 'minItems' in inputs['ulr'][-1][2]['schema_error']
