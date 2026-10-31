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
global.fetch = async () => ({ ok: true, json: async () => ({
  system_prompt: '', student: {}, memory: {version:'test'},
  tools: [{function:{name:'get_practice_questions',description:'practice',parameters:{type:'object'}}}],tool_groups:{},
}) });
(async () => {
  await plugin.apply({ systemPrompt: {section(){},context(){}}, tools: {register(tool){tools.push(tool);return()=>{};}}, on(){} });
  const tool = tools.find(tool => tool.name === 'get_practice_questions');
  const question = {id:1, kp_name:'合成知识点', difficulty_level:2, is_review:false, content:'SYNTHETIC_QUESTION_TEXT', options:['SYNTHETIC_OPTION']};
  const result = {questions:[question], visual:{type:'practice_quiz',payload:{questions:[question]}}};
  const snapshot = JSON.stringify(result);
  const model = JSON.parse(tool.output.render({},result)[0].text);
  assert.equal(JSON.stringify(model).includes('SYNTHETIC_QUESTION_TEXT'),false);
  assert.equal(JSON.stringify(model).includes('SYNTHETIC_OPTION'),false);
  assert.equal(model.question_count,1);
  assert.equal(model.questions[0].id,1);
  assert.equal(tool.output.presentationMeta({},result).unimindCard.payload.questions[0].content,'SYNTHETIC_QUESTION_TEXT');
  assert.equal(JSON.stringify(result),snapshot,'card and original result must remain intact');
  console.log('practice model summary and full card smoke passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
