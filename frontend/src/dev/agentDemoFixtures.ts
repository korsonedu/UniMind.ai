import type { Message } from '@/hooks/useAgentConversation';
import type { VisualData } from '@/pages/xiaoyu/visuals';

// These scenes use the production Agent's tool names and visual payload contracts.
// Imported only by the development preview; no generated answer calls a backend.
interface DemoTool { name: string; label: string; summary: string; visual?: VisualData }
interface DemoScene { id: string; title: string; prompt: string; answer: string; tools: DemoTool[] }
const action = (title: string, description: string, icon: string, url: string, label: string, type = 'navigate') => ({ title, description, icon, action: { type, url, label } });
const price = (yieldPercent: number, years: number) => Array.from({ length: years }, (_, i) => 40 / (1 + yieldPercent / 100) ** (i + 1)).reduce((sum, value) => sum + value, 0) + 1000 / (1 + yieldPercent / 100) ** years;

export const agentDemoScenes: DemoScene[] = [
  {
    id: 'demo-plan', title: '今天的学习安排',
    prompt: '小宇，我今天有 45 分钟。结合最近的学习情况，帮我安排一下。',
    answer: '你最近的练习正确率是 82%，但「债券定价」和「货币政策传导」还不稳定。我建议先处理 8 道到期复习，再用图像理解利率与价格的关系，最后做一组短练习。\n\n这 45 分钟，我们把一个薄弱点真正解决。',
    tools: [
      { name: 'get_learning_stats', label: '读取学习记录', summary: '已分析 2,460 次练习与近 180 天学习记录', visual: { type: 'data_card', payload: { title: '你的学习状态', subtitle: '最近 7 天', items: [{ label: '练习正确率', value: '82% · ↑ 11%', trend: 'up' }, { label: '连续学习', value: '18 天' }, { label: '本周练习', value: '179 题' }], note: '根据演示账号的学习记录生成。' } } },
      { name: 'get_user_weak_points', label: '定位薄弱知识', summary: '债券定价 48% · 货币政策传导 56%' },
      { name: 'get_due_reviews', label: '检查到期复习', summary: '找到 8 道到期题目，预计 10 分钟' },
      { name: 'render_visual', label: '安排今天的学习', summary: '已生成 45 分钟学习路径', visual: { type: 'action_cards', payload: { title: '今天的 45 分钟', cards: [action('01 先把到期知识稳住 · 10 分钟', '8 道 Memorix 到期复习，先回忆，再看解析。', 'review', '/tests?mode=review', '开始复习'), action('02 看懂债券价格曲线 · 15 分钟', '从现金流与折现率出发，用一张图理解反向关系。', 'chart', '用图像讲解债券价格与收益率的关系', '一起看图', 'reply'), action('03 用 3 道题检查理解 · 20 分钟', '从直觉判断到计算，再到完整解释。', 'quiz', '给我一组债券定价练习', '开始随堂练习', 'reply')] } } },
    ],
  },
  {
    id: 'demo-bond', title: '利率与债券价格',
    prompt: '为什么市场利率上升，债券价格反而下降？画图帮我理解。',
    answer: '债券未来付给你的现金流没有变，变的是你今天愿意为它支付多少钱。市场收益率越高，同一笔未来现金流折算到今天就越少。\n\n看这张图：同样是面值 1,000 元、票面利率 4% 的债券，期限越长，价格对收益率变化越敏感。',
    tools: [
      { name: 'search_knowledge_tree', label: '查找债券定价知识', summary: '已关联资金时间价值、现金流折现与久期' },
      { name: 'render_visual', label: '绘制价格与收益率曲线', summary: '对比 3 年期与 10 年期债券', visual: { type: 'function_graph', payload: { title: '收益率上升，债券价格下降', xRange: [1, 9], yRange: [650, 1300], xLabel: '到期收益率（%）', yLabel: '债券价格（元）', expressions: [3, 10].map((years, index) => ({ label: `${years} 年期 · 票面利率 4%`, color: index ? '#6366f1' : '#14b8a6', points: Array.from({ length: 33 }, (_, i) => ({ x: 1 + i / 4, y: Math.round(price(1 + i / 4, years) * 100) / 100 })) })), points: [{ x: 4, y: 1000, label: '收益率 = 票面利率 → 平价' }] } } },
      { name: 'render_visual', label: '展开现金流折现公式', summary: '固定现金流，改变折现率', visual: { type: 'latex_derivation', payload: { title: '把图像连回公式', steps: [{ latex: 'P=\\sum_{t=1}^{n}\\frac{C}{(1+y)^t}+\\frac{F}{(1+y)^n}', note: '价格 = 每期票息现值 + 到期本金现值。y 增大，每一项现值都会下降。' }] } } },
    ],
  },
  {
    id: 'demo-map', title: '债券定价的知识关系',
    prompt: '我总把利率、债券、风险溢价混在一起。能把它们的关系整理出来吗？',
    answer: '它们围绕同一个问题连接起来：未来的钱，今天值多少？\n\n你对「现金流」和「资金时间价值」已经比较熟悉，可以从这两个支点出发。先补上折现率，再看债券定价，最后理解风险溢价为什么会改变价格。图中偏暖的节点是这次优先补齐的部分。',
    tools: [
      { name: 'get_knowledge_mastery_map', label: '读取知识掌握图谱', summary: '已关联 7 个知识点，识别 2 个薄弱环节', visual: { type: 'knowledge_map', payload: { title: '从时间价值，到债券定价', nodes: [{ id: 'time', label: '时间价值', mastery: .91 }, { id: 'cash', label: '现金流', mastery: .86 }, { id: 'discount', label: '折现率', mastery: .61 }, { id: 'bond', label: '债券定价', mastery: .48 }, { id: 'yield', label: '收益率', mastery: .72 }, { id: 'risk', label: '风险溢价', mastery: .35 }, { id: 'duration', label: '久期', mastery: .64 }], edges: [{ from: 'time', to: 'discount' }, { from: 'cash', to: 'bond' }, { from: 'discount', to: 'bond' }, { from: 'yield', to: 'bond' }, { from: 'risk', to: 'discount' }, { from: 'bond', to: 'duration' }, { from: 'yield', to: 'duration' }], highlights: ['bond', 'risk'], note: '掌握度来自演示练习记录。知识之间的连线表示理解上的依赖关系。' } } },
      { name: 'search_courses', label: '寻找相关课程', summary: '找到「金融市场与利率」与「风险与收益」' },
      { name: 'render_visual', label: '匹配下一步学习资源', summary: '从薄弱知识出发，衔接对应课程', visual: { type: 'action_cards', payload: { title: '顺着这条路径学下去', cards: [action('回到现金流折现', '金融市场与利率 · 第 1 节 · 从具体数字建立直觉', 'video', '/course/1?lessonDemo=1', '打开课程'), action('理解风险为什么需要补偿', '风险与收益 · 第 3 节 · 连接折现率与风险溢价', 'course', '/course/3?lessonDemo=1', '继续学习')] } } },
    ],
  },
  {
    id: 'demo-practice', title: '债券定价练习',
    prompt: '刚才的曲线我看懂了。给我几道债券定价题，看看我是不是真的会了。',
    answer: '好，我们按「判断方向 → 代入计算 → 解释原因」练 3 道。你可以直接在这里作答，提交后查看逐题反馈。\n\n这组题会特别检查你是否把票面利率和市场收益率区分开。',
    tools: [
      { name: 'get_recent_practice_result', label: '回看最近练习', summary: '发现薄弱点：折现率选择、债券价格变化' },
      { name: 'get_practice_questions', label: '匹配针对性练习', summary: '已从债券定价知识点选出 3 道题', visual: { type: 'practice_quiz', payload: { practice_id: 'preview-bond-practice', title: '债券定价 · 从直觉到计算', questions: [{ id: 104, text: '一只固定利率债券的票息和本金不变。当市场到期收益率从 4% 上升至 5% 时，它的价格通常会怎样变化？', q_type: 'objective', options: ['下降，因为未来现金流的折现率提高', '上升，因为投资者要求更高收益', '不变，因为票面利率没有变化', '无法判断，与收益率没有关系'], kp_name: '债券定价' }, { id: 105, text: '一只一年期零息债券，面值为 1,000 元，市场收益率为 5%。当前价格最接近多少？', q_type: 'objective', options: ['952.38 元', '1,000 元', '1,050 元', '950 元'], kp_name: '现金流折现' }, { id: 106, text: '两只票面利率相同、信用风险相同的债券，剩余期限分别为 3 年和 10 年。市场收益率同时上升时，哪只债券价格通常变化更大？请说明原因。', q_type: 'subjective', options: [], kp_name: '利率风险与久期' }] } } },
    ],
  },
];

export const demoSceneForMessage = (message: string) => {
  if (/练习|出题|做题|测一下|检验|检查理解/.test(message)) return agentDemoScenes[3];
  if (/图谱|知识图|知识.*关系|风险溢价|混在一起|连接/.test(message)) return agentDemoScenes[2];
  if (/债券|曲线|图像|画图|公式|收益率|利率.*价格/.test(message)) return agentDemoScenes[1];
  return agentDemoScenes[0];
};

export const buildDemoHistory = (day: string): Message[] => agentDemoScenes.flatMap((scene, index) => {
  const base = { conversation_id: scene.id, conversation_title: scene.title, timestamp: `${day}T0${8 - index}:00:00Z` };
  const visualTool = scene.id === 'demo-plan' ? scene.tools[3] : scene.tools.find(tool => tool.visual)!;
  const steps: Message[] = scene.tools.filter(tool => tool !== visualTool).slice(0, 2).map((tool, toolIndex) => ({
    ...base, id: 1001 + index * 10 + toolIndex, role: 'assistant', content: '',
    toolStep: { run_id: `demo-${index}`, call_id: `demo-${index}-${toolIndex}`, round: toolIndex + 1,
      name: tool.name, label: tool.label, status: 'succeeded', result_summary: tool.summary, duration_ms: 240 + toolIndex * 130 },
  }));
  return [{ ...base, id: 1000 + index * 10, role: 'user', content: scene.prompt }, ...steps,
    { ...base, id: 1005 + index * 10, role: 'assistant', content: '', metadata: { all_visuals: [visualTool.visual!] } },
    { ...base, id: 1006 + index * 10, role: 'assistant', content: scene.id === 'demo-bond' ? '未来现金流不变，折现率越高，现值就越低。期限越长，价格通常越敏感。' : scene.id === 'demo-plan' ? '先巩固，再理解，最后用练习检查。你可以直接点击上面的安排开始。' : scene.id === 'demo-map' ? '先补齐「折现率 → 债券定价」，再理解风险溢价。颜色显示你当前的掌握程度。' : '先判断方向，再代入计算，最后解释原因。直接在这里作答，提交后逐题复盘。' }];
});
