const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('./node_modules/typescript');
const compiled = ts.transpileModule(fs.readFileSync(__dirname + '/plugin.ts', 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const plugin = {};
new Function('exports', 'require', compiled)(plugin, require);
const tools = [];
process.env.UNIMIND_API_URL = 'http://localhost:1';
process.env.UNIMIND_AUTH_TOKEN = 'synthetic-only';
// Scale real deadlines so the slow callback smoke finishes in milliseconds.
const timeout = AbortSignal.timeout.bind(AbortSignal);
AbortSignal.timeout = ms => timeout(ms / 100);
global.fetch = async (url, options) => {
  if (url.pathname.endsWith('/context/')) return { ok: true, json: async () => ({
    system_prompt: '', student: {}, memory: {version:'test'}, tool_groups:{},
    tools: ['build_learning_experiment', 'get_practice_questions'].map(name => ({function:{name, description:name, parameters:{type:'object'}}})),
  }) };
  await new Promise((resolve, reject) => {
    options.signal.throwIfAborted();
    const timer = setTimeout(resolve, 200);
    options.signal.addEventListener('abort', () => {clearTimeout(timer);reject(options.signal.reason);}, {once:true});
  });
  return {ok:true, json:async () => ({preview:{visual_review:{status:'passed'}}})};
};
(async () => {
  await plugin.apply({systemPrompt:{section(){},context(){}}, tools:{register(tool){tools.push(tool);return()=>{};}}, on(){}});
  const build = tools.find(tool => tool.name === 'build_learning_experiment');
  const result = await build.execute({}, {signal:new AbortController().signal});
  assert.equal(result.preview.visual_review.status, 'passed');
  assert.ok(build.timeoutMs >= 40000);
  const ordinary = tools.find(tool => tool.name === 'get_practice_questions');
  assert.equal(ordinary.timeoutMs, 15000);
  await assert.rejects(ordinary.execute({}, {signal:new AbortController().signal}), {name:'TimeoutError'});
  const cancelled = new AbortController();cancelled.abort();
  await assert.rejects(build.execute({}, {signal:cancelled.signal}), {name:'AbortError'});
  console.log('slow visual callback, ordinary deadline and cancellation smoke passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
