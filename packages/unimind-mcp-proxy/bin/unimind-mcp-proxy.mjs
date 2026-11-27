#!/usr/bin/env node
import { createStdioHttpBridge, DEFAULT_MCP_URL, parseArgs } from '../src/bridge.mjs';

const HELP = `Usage: npx @unimind/mcp-proxy [options]

Bridge local stdio MCP clients (Claude Desktop, Raycast, Obsidian, etc.)
to a remote UniMind.ai Learning Memory Streamable HTTP MCP endpoint.

Options:
  --url <url>           MCP endpoint URL (env: UNIMIND_MCP_URL, default: ${DEFAULT_MCP_URL})
  --token <token>       Bearer credential (env: UNIMIND_LEARNING_MEMORY_TOKEN)
  --timeout-ms <ms>     Per-request HTTP timeout in ms (default: 30000)
  --trace-prefix <str>  Prefix for X-Trace-Id headers (default: mcp-proxy)
  -v, --version         Print version
  -h, --help            Show this help message
`;

const options = parseArgs(process.argv.slice(2));
if (options.help) {
  process.stdout.write(HELP);
  process.exit(0);
}
if (options.version) {
  process.stdout.write('1.0.0\n');
  process.exit(0);
}

try {
  const bridge = createStdioHttpBridge(options);
  const handle = bridge.attachStdio(process.stdin, process.stdout);
  const shutdown = async () => {
    await handle.close();
    process.exit(0);
  };
  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
} catch (error) {
  process.stderr.write(`[unimind-mcp-proxy] ${error.message}\n`);
  process.exit(1);
}
