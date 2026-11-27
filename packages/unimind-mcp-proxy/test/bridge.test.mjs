import test from 'node:test';
import assert from 'node:assert/strict';
import { PassThrough } from 'node:stream';
import { createStdioHttpBridge, parseArgs } from '../src/bridge.mjs';

test('parseArgs reads flags and environment defaults', () => {
  const opts = parseArgs(
    ['--url', 'https://example.com/mcp/', '--timeout-ms=5000'],
    { UNIMIND_LEARNING_MEMORY_TOKEN: 'umlm_test_token' },
  );
  assert.equal(opts.url, 'https://example.com/mcp/');
  assert.equal(opts.token, 'umlm_test_token');
  assert.equal(opts.timeoutMs, 5000);
});

test('stdio-to-http bridge forwards initialize, notifications, tools/list, SSE and handles 401', async () => {
  const seen = [];
  const mockFetch = async (_url, init) => {
    const payload = JSON.parse(init.body);
    seen.push({
      auth: init.headers.Authorization,
      protocol: init.headers['MCP-Protocol-Version'],
      session: init.headers['Mcp-Session-Id'],
      payload,
    });
    if (init.headers.Authorization !== 'Bearer umlm_secret') {
      return {
        ok: false,
        status: 401,
        headers: new Headers({ 'content-type': 'application/json' }),
        text: async () => JSON.stringify({ detail: 'Unauthorized' }),
      };
    }
    if (!('id' in payload)) {
      return { ok: true, status: 202, headers: new Headers(), text: async () => '' };
    }
    if (payload.method === 'initialize') {
      return {
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json', 'mcp-session-id': 'sess-42' }),
        text: async () => JSON.stringify({
          jsonrpc: '2.0',
          id: payload.id,
          result: { protocolVersion: '2025-06-18', capabilities: { tools: {} } },
        }),
      };
    }
    if (payload.method === 'tools/call') {
      return {
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'text/event-stream' }),
        text: async () => `event: message\ndata: ${JSON.stringify({ jsonrpc: '2.0', id: payload.id, result: { content: [{ type: 'text', text: 'ok' }] } })}\n\n`,
      };
    }
    return {
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      text: async () => JSON.stringify({
        jsonrpc: '2.0',
        id: payload.id,
        result: { tools: [{ name: 'recall_learning' }] },
      }),
    };
  };

  const url = 'https://unimind-ai.com/api/ai/learning-memory/mcp/';
  const bridge = createStdioHttpBridge({ url, token: 'umlm_secret', fetchImpl: mockFetch, logger: () => {} });
  const input = new PassThrough();
  const output = new PassThrough();
  const lines = [];
  output.on('data', (chunk) => {
    for (const line of chunk.toString('utf8').split('\n')) {
      if (line.trim()) lines.push(JSON.parse(line));
    }
  });

  const handle = bridge.attachStdio(input, output);
  input.write(`${JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'initialize', params: { protocolVersion: '2025-11-25' } })}\n`);
  await new Promise((r) => setTimeout(r, 30));
  input.write(`${JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized', params: {} })}\n`);
  input.write(`${JSON.stringify({ jsonrpc: '2.0', id: 2, method: 'tools/list', params: {} })}\n`);
  input.write(`${JSON.stringify({ jsonrpc: '2.0', id: 3, method: 'tools/call', params: { name: 'recall_learning', arguments: {} } })}\n`);
  await new Promise((r) => setTimeout(r, 40));
  await handle.close();

  assert.equal(lines.length, 3);
  assert.equal(lines[0].result.protocolVersion, '2025-06-18');
  assert.equal(lines[1].result.tools[0].name, 'recall_learning');
  assert.equal(lines[2].result.content[0].text, 'ok');
  assert.equal(bridge.getProtocolVersion(), '2025-06-18');
  assert.equal(seen.length, 4);
  assert.equal(seen[2].protocol, '2025-06-18');
  assert.equal(seen[2].session, 'sess-42');

  const badBridge = createStdioHttpBridge({ url, token: 'umlm_wrong', fetchImpl: mockFetch, logger: () => {} });
  const denied = await badBridge.forwardMessage({ jsonrpc: '2.0', id: 9, method: 'tools/list', params: {} });
  assert.equal(denied.error.code, -32001);
});
