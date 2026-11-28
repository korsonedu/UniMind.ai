import crypto from 'node:crypto';
import readline from 'node:readline';

export const DEFAULT_MCP_URL = 'https://unimind-ai.com/api/ai/learning-memory/mcp/';
export const DEFAULT_PROTOCOL_VERSION = '2025-11-25';
export const DEFAULT_TIMEOUT_MS = 30_000;

export function parseArgs(argv, env = process.env) {
  const options = {
    url: env.UNIMIND_MCP_URL || DEFAULT_MCP_URL,
    token: env.UNIMIND_LEARNING_MEMORY_TOKEN || '',
    timeoutMs: Number(env.UNIMIND_MCP_TIMEOUT_MS || DEFAULT_TIMEOUT_MS),
    tracePrefix: env.UNIMIND_MCP_TRACE_PREFIX || 'mcp-proxy',
    help: false,
    version: false,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--help' || arg === '-h') {
      options.help = true;
    } else if (arg === '--version' || arg === '-v') {
      options.version = true;
    } else if (arg === '--url' && argv[i + 1]) {
      options.url = argv[++i];
    } else if (arg.startsWith('--url=')) {
      options.url = arg.slice('--url='.length);
    } else if (arg === '--token' && argv[i + 1]) {
      options.token = argv[++i];
    } else if (arg.startsWith('--token=')) {
      options.token = arg.slice('--token='.length);
    } else if (arg === '--timeout-ms' && argv[i + 1]) {
      options.timeoutMs = Number(argv[++i]);
    } else if (arg.startsWith('--timeout-ms=')) {
      options.timeoutMs = Number(arg.slice('--timeout-ms='.length));
    } else if (arg === '--trace-prefix' && argv[i + 1]) {
      options.tracePrefix = argv[++i];
    } else if (arg.startsWith('--trace-prefix=')) {
      options.tracePrefix = arg.slice('--trace-prefix='.length);
    }
  }

  if (!Number.isFinite(options.timeoutMs) || options.timeoutMs < 1000) {
    options.timeoutMs = DEFAULT_TIMEOUT_MS;
  }
  return options;
}

function makeError(id, code, message, data) {
  const error = { code, message };
  if (data !== undefined) {
    error.data = data;
  }
  return { jsonrpc: '2.0', id: id ?? null, error };
}

export function createStdioHttpBridge({
  url,
  token,
  timeoutMs = DEFAULT_TIMEOUT_MS,
  tracePrefix = 'mcp-proxy',
  fetchImpl = globalThis.fetch,
  logger = console.error,
}) {
  if (!url) {
    throw new Error('MCP URL is required (--url or UNIMIND_MCP_URL).');
  }
  if (!token) {
    throw new Error('Bearer token is required (--token or UNIMIND_LEARNING_MEMORY_TOKEN).');
  }

  let protocolVersion = DEFAULT_PROTOCOL_VERSION;
  let sessionId = null;

  async function forwardMessage(message) {
    const isNotification = message && typeof message === 'object' && !('id' in message);
    const requestId = message && typeof message === 'object' ? message.id : null;

    if (message?.method === 'initialize' && typeof message?.params?.protocolVersion === 'string') {
      protocolVersion = message.params.protocolVersion;
    }

    const headers = {
      'Content-Type': 'application/json',
      Accept: 'application/json, text/event-stream',
      Authorization: `Bearer ${token}`,
      'MCP-Protocol-Version': protocolVersion,
      'X-Trace-Id': `${tracePrefix}-${crypto.randomUUID().slice(0, 12)}`,
    };
    if (sessionId) {
      headers['Mcp-Session-Id'] = sessionId;
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetchImpl(url, {
        method: 'POST',
        headers,
        body: JSON.stringify(message),
        signal: controller.signal,
      });

      const incomingSession = response.headers?.get?.('mcp-session-id');
      if (incomingSession) {
        sessionId = incomingSession;
      }

      if (response.status === 202 || response.status === 204) {
        return null;
      }

      const contentType = (response.headers?.get?.('content-type') || '').toLowerCase();
      const rawText = await response.text();

      if (!response.ok) {
        if (isNotification) {
          logger(`[unimind-mcp-proxy] Notification rejected (${response.status})`);
          return null;
        }
        try {
          const parsed = JSON.parse(rawText);
          if (parsed && typeof parsed === 'object' && parsed.jsonrpc === '2.0' && parsed.error) {
            return parsed;
          }
        } catch {
          // Non-JSON HTTP error body
        }
        const code = response.status === 401 || response.status === 403 ? -32001 : -32002;
        const msg = response.status === 401
          ? 'UniMind MCP authentication failed (401). Check your Bearer token.'
          : `UniMind MCP HTTP error (${response.status}).`;
        return makeError(requestId, code, msg, { status: response.status });
      }

      if (!rawText.trim()) {
        return null;
      }

      if (contentType.includes('text/event-stream')) {
        const events = [];
        for (const line of rawText.split(/\r?\n/)) {
          if (line.startsWith('data:')) {
            const data = line.slice(5).trim();
            if (data && data !== '[DONE]') {
              events.push(JSON.parse(data));
            }
          }
        }
        return events.length ? events[events.length - 1] : null;
      }

      const payload = JSON.parse(rawText);
      if (message?.method === 'initialize' && typeof payload?.result?.protocolVersion === 'string') {
        protocolVersion = payload.result.protocolVersion;
      }
      return payload;
    } catch (error) {
      if (isNotification) {
        logger(`[unimind-mcp-proxy] Notification transport error: ${error.message}`);
        return null;
      }
      const isAbort = error?.name === 'AbortError';
      return makeError(
        requestId,
        -32002,
        isAbort ? `UniMind MCP request timed out after ${timeoutMs}ms.` : `UniMind MCP transport error: ${error.message}`,
      );
    } finally {
      clearTimeout(timer);
    }
  }

  function attachStdio(input = process.stdin, output = process.stdout) {
    const rl = readline.createInterface({ input, crlfDelay: Infinity });
    const pending = new Set();

    rl.on('line', (line) => {
      const trimmed = line.trim();
      if (!trimmed) {
        return;
      }
      let message;
      try {
        message = JSON.parse(trimmed);
      } catch (error) {
        output.write(`${JSON.stringify(makeError(null, -32700, `Parse error: ${error.message}`))}\n`);
        return;
      }
      const task = forwardMessage(message)
        .then((reply) => {
          if (reply !== null && reply !== undefined) {
            output.write(`${JSON.stringify(reply)}\n`);
          }
        })
        .catch((error) => {
          logger(`[unimind-mcp-proxy] Unexpected error: ${error.message}`);
        })
        .finally(() => {
          pending.delete(task);
        });
      pending.add(task);
    });

    return {
      close: async () => {
        rl.close();
        await Promise.allSettled(pending);
      },
    };
  }

  return { forwardMessage, attachStdio, getProtocolVersion: () => protocolVersion };
}
