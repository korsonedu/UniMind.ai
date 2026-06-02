# 小宇可视化 Dashboard 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将小宇的 Dashboard 从固定数据卡片升级为动态可视化画布，支持 LaTeX 推导、解题步骤、知识图谱、数据卡片等富内容渲染。

**Architecture:** 小宇通过 `render_visual` 工具触发 Dashboard 渲染，visual 数据随消息持久化，前端根据 type 分发到对应 renderer。新增对话从空画布开始，历史会话恢复最后的 visual 状态。

**Tech Stack:** Django (backend tools + model), React + TypeScript (frontend renderers), SSE/WS (streaming), KaTeX (LaTeX 渲染)

---

## File Structure

### Backend
| 文件 | 职责 | 改动类型 |
|------|------|---------|
| `backend/ai_engine/tools.py` | 新增 `RENDER_VISUAL_SCHEMA` 和工具定义 | Modify |
| `backend/ai_assistant/services/tool_executor.py` | `PlannerToolExecutor` 新增 `_handle_render_visual` | Modify |
| `backend/ai_assistant/services/chat_dispatch.py` | 消息保存时从 executor 提取 visual 存入 metadata | Modify |
| `backend/ai_assistant/consumers.py` | WS 消息保存时提取 visual | Modify |
| `backend/prompts/ai_assistant/bots/xiaoyu/tool_guide.txt` | 新增 render_visual 使用指南 | Modify |

### Frontend
| 文件 | 职责 | 改动类型 |
|------|------|---------|
| `frontend/src/pages/XiaoYu.tsx` | Landing 文案 + SKILLS 扩展 + visual 事件处理 | Modify |
| `frontend/src/pages/xiaoyu/DashboardPanel.tsx` | 重构为 VisualCanvas，支持 type 分发 | Modify (rewrite) |
| `frontend/src/pages/xiaoyu/visuals/DataCardRenderer.tsx` | data_card renderer（从 DashboardPanel 提取） | Create |
| `frontend/src/pages/xiaoyu/visuals/LatexRenderer.tsx` | latex_derivation renderer | Create |
| `frontend/src/pages/xiaoyu/visuals/StepSolutionRenderer.tsx` | step_solution renderer | Create |
| `frontend/src/pages/xiaoyu/visuals/KnowledgeMapRenderer.tsx` | knowledge_map renderer | Create |
| `frontend/src/pages/xiaoyu/visuals/index.ts` | type → renderer 映射 | Create |

---

### Task 1: 后端 — render_visual 工具定义

**Files:**
- Modify: `backend/ai_engine/tools.py:694-697`（在 planner_only 列表末尾新增）
- Modify: `backend/ai_engine/tools.py`（新增 schema 常量）

- [ ] **Step 1: 在 tools.py 末尾新增 RENDER_VISUAL_SCHEMA**

在文件末尾（exam generator schemas 之后）新增：

```python
# ── 小宇可视化工具 Schema ──────────────────────────────────────

RENDER_VISUAL_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {
            "type": "string",
            "enum": ["data_card", "latex_derivation", "step_solution", "knowledge_map"],
            "description": "可视化类型。data_card=数据卡片，latex_derivation=数学推导，step_solution=解题步骤，knowledge_map=知识图谱",
        },
        "payload": {
            "type": "object",
            "description": "可视化内容，结构由 type 决定。详见各类型 schema。",
        },
    },
    "required": ["type", "payload"],
}
```

- [ ] **Step 2: 在 get_planner_tools() 的 planner_only 列表末尾新增 render_visual 工具**

在 `backend/ai_engine/tools.py:694` 行（`create_dashboard_card` 之后）新增：

```python
        _make_tool("render_visual", "在 Dashboard 画布上渲染可视化内容。用于展示数学推导过程、解题步骤、知识图谱、数据统计等需要视觉呈现的内容。纯文字问答不需要调用此工具。", RENDER_VISUAL_SCHEMA,
            impl_summary="将可视化数据（type + payload）返回给前端，前端根据 type 渲染到 Dashboard 画布。"),
```

- [ ] **Step 3: 验证语法正确**

```bash
cd backend && python3 -m py_compile ai_engine/tools.py
```

Expected: 无输出（语法正确）

- [ ] **Step 4: Commit**

```bash
git add backend/ai_engine/tools.py
git commit -m "feat: add render_visual tool schema and definition for XiaoYu"
```

---

### Task 2: 后端 — render_visual 工具执行器

**Files:**
- Modify: `backend/ai_assistant/services/tool_executor.py:343-345`（PlannerToolExecutor 类末尾）

- [ ] **Step 1: 在 PlannerToolExecutor 中新增 _handle_render_visual 和 visual 缓存**

在 `PlannerToolExecutor` 类的 `__init__` 方法中（如果没有则新增）初始化 visual 缓存，在 `_handle_render_visual` 中存储并返回数据。

在 `PlannerToolExecutor` 类末尾（`_handle_search_articles` 之后）新增：

```python
    def __init__(self, user, institution=None):
        super().__init__(user, institution)
        self.pending_visual = None  # 存储最近一次 render_visual 的结果

    def _handle_render_visual(self, args: Dict) -> Dict:
        """将可视化数据返回给前端，同时缓存到实例供消息持久化。"""
        visual_type = args.get('type', '')
        payload = args.get('payload', {})

        valid_types = {'data_card', 'latex_derivation', 'step_solution', 'knowledge_map'}
        if visual_type not in valid_types:
            return {"error": f"不支持的可视化类型: {visual_type}，支持: {', '.join(valid_types)}"}

        self.pending_visual = {"type": visual_type, "payload": payload}
        return {"status": "ok", "type": visual_type}
```

- [ ] **Step 2: 确认 PlannerToolExecutor 已有 __init__**

读取 `tool_executor.py` 确认 `PlannerToolExecutor` 是否已有 `__init__`。如果有，在其中添加 `self.pending_visual = None`。如果没有，使用上面的完整 `__init__`。

- [ ] **Step 3: 验证语法正确**

```bash
cd backend && python3 -m py_compile ai_assistant/services/tool_executor.py
```

Expected: 无输出

- [ ] **Step 4: Commit**

```bash
git add backend/ai_assistant/services/tool_executor.py
git commit -m "feat: add render_visual handler to PlannerToolExecutor"
```

---

### Task 3: 后端 — visual 持久化到消息 metadata

**Files:**
- Modify: `backend/ai_assistant/consumers.py:147-153`（消息保存处）
- Modify: `backend/ai_assistant/services/chat_dispatch.py:37-45`（消息保存处）

**Context:** 当前 `AIChatMessage` 已有 `metadata` JSONField。我们需要在 AI 回复保存时，从 `tool_executor.pending_visual` 提取 visual 数据存入 metadata。

- [ ] **Step 1: 修改 consumers.py — WS 路径保存 visual**

在 `consumers.py` 中找到 AI 消息保存的代码（约第 147-153 行），在保存消息时将 visual 写入 metadata：

```python
            # 保存 AI 回复消息时，附带 visual 数据
            msg_metadata = {}
            if hasattr(tool_executor, 'pending_visual') and tool_executor.pending_visual:
                msg_metadata['visual'] = tool_executor.pending_visual
                tool_executor.pending_visual = None  # 清除缓存

            self._save_message(
                self.user, self.bot, 'assistant', ai_content,
                conversation_id=conversation_id,
                metadata=msg_metadata,
            )
```

需要确认 `_save_message` 方法支持 metadata 参数。如果不支持，需要扩展该方法。

- [ ] **Step 2: 修改 chat_dispatch.py — SSE 路径保存 visual**

在 `chat_dispatch.py` 中找到消息保存逻辑，同样提取 visual 数据：

```python
            msg_metadata = {}
            if hasattr(tool_executor, 'pending_visual') and tool_executor.pending_visual:
                msg_metadata['visual'] = tool_executor.pending_visual
                tool_executor.pending_visual = None

            AIChatMessage.objects.create(
                user=user, bot=bot, role='assistant',
                content=ai_content, conversation_id=conversation_id,
                metadata=msg_metadata,
            )
```

- [ ] **Step 3: 确认消费者 _save_message 支持 metadata**

读取 `consumers.py` 的 `_save_message` 方法签名。如果只有 `(user, bot, role, content, conversation_id)`，需要新增 `metadata=None` 参数并传递给 `AIChatMessage.objects.create`。

- [ ] **Step 4: 验证语法正确**

```bash
cd backend && python3 -m py_compile ai_assistant/consumers.py && python3 -m py_compile ai_assistant/services/chat_dispatch.py
```

- [ ] **Step 5: Commit**

```bash
git add backend/ai_assistant/consumers.py backend/ai_assistant/services/chat_dispatch.py
git commit -m "feat: persist render_visual output in message metadata"
```

---

### Task 4: 后端 — SSE 流支持 visual 事件

**Files:**
- Modify: `backend/ai_engine/service.py:700-708`（step done 事件构造）

**Context:** 当前 step done 事件只包含 `result_summary`（截断到 200 字符）。对于 `render_visual`，需要将完整 payload 传给前端。

- [ ] **Step 1: 在 service.py 的 step done 事件中，为 render_visual 附加完整 payload**

找到 step done 事件构造代码（约第 700-708 行），在 `result_summary` 之外为 `render_visual` 附加完整数据：

```python
                step_event = {
                    "type": "step",
                    "name": name,
                    "call_id": call_id,
                    "status": "done",
                    "result_summary": summarize_tool_result(name, result) if summarize_tool_result else str(result)[:200],
                }
                # render_visual 需要完整 payload 给前端渲染
                if name == "render_visual" and isinstance(result, dict):
                    step_event["visual"] = result
                if on_step:
                    on_step(step_event)
```

- [ ] **Step 2: 验证语法正确**

```bash
cd backend && python3 -m py_compile ai_engine/service.py
```

- [ ] **Step 3: Commit**

```bash
git add backend/ai_engine/service.py
git commit -m "feat: include full visual payload in render_visual step events"
```

---

### Task 5: 后端 — Prompt 更新

**Files:**
- Modify: `backend/prompts/ai_assistant/bots/xiaoyu/tool_guide.txt`

- [ ] **Step 1: 在 tool_guide.txt 的"知识与资源类"之后新增"可视化渲染类"章节**

```markdown
### 可视化渲染类
- `render_visual` → 在 Dashboard 画布上渲染可视化内容

#### 使用场景
- 讲解数学公式/推导过程时 → type: latex_derivation
- 分析学习数据/统计时 → type: data_card
- 讲解题目步骤时 → type: step_solution
- 展示知识体系/关系时 → type: knowledge_map

#### 不需要渲染的场景
- 纯文字问答（简单提问、闲聊、鼓励）
- 学生没有明确需要视觉辅助的内容
- 不确定用什么类型时，宁可不渲染

#### 原则
- 可视化是对话的增强，不是必需。只在视觉呈现能显著提升理解时才使用。
- 每次对话中 render_visual 不需要每轮都调，只在有值得可视化的内容时调用。
- 现有的 create_dashboard_card 功能已被 render_visual(type="data_card") 替代。
```

- [ ] **Step 2: Commit**

```bash
git add backend/prompts/ai_assistant/bots/xiaoyu/tool_guide.txt
git commit -m "feat: add render_visual usage guide to XiaoYu tool_guide"
```

---

### Task 6: 前端 — 可视化 Renderer 组件

**Files:**
- Create: `frontend/src/pages/xiaoyu/visuals/DataCardRenderer.tsx`
- Create: `frontend/src/pages/xiaoyu/visuals/LatexRenderer.tsx`
- Create: `frontend/src/pages/xiaoyu/visuals/StepSolutionRenderer.tsx`
- Create: `frontend/src/pages/xiaoyu/visuals/KnowledgeMapRenderer.tsx`
- Create: `frontend/src/pages/xiaoyu/visuals/index.ts`

**Context:** 每个 renderer 接收对应类型的 payload，渲染到 Dashboard 画布中。使用 `react-markdown` + `remark-math` + `rehype-katex` 渲染 LaTeX（项目已有依赖）。

- [ ] **Step 1: 创建 DataCardRenderer.tsx**

从现有 `DashboardPanel.tsx` 中提取数据卡片渲染逻辑：

```tsx
import React from 'react';
import { BarChart3, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useNavigate } from 'react-router-dom';
import { cn } from '@/lib/utils';

interface DataCardPayload {
  title: string;
  subtitle?: string;
  items: Array<{
    label: string;
    value: string;
    trend?: 'up' | 'down' | 'neutral';
    progress?: number;
    emphasis?: boolean;
    action_link?: string;
  }>;
  cta?: { label: string; link: string };
}

export const DataCardRenderer: React.FC<{ payload: DataCardPayload }> = ({ payload }) => {
  const navigate = useNavigate();

  return (
    <div className="p-4 space-y-3 animate-in fade-in duration-300">
      <div className="flex items-center gap-2">
        <BarChart3 className="h-4 w-4 text-primary/60" />
        <h3 className="text-sm font-semibold">{payload.title}</h3>
        {payload.subtitle && (
          <span className="text-xs text-muted-foreground ml-auto">{payload.subtitle}</span>
        )}
      </div>
      <div className="space-y-1.5">
        {payload.items?.map((item, i) => {
          const clickable = !!item.action_link;
          const content = (
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">{item.label}</span>
              <span className={cn(
                "font-semibold tabular-nums",
                item.trend === 'up' && "text-emerald-500",
                item.trend === 'down' && "text-red-400",
              )}>
                {item.value}
                {item.trend === 'up' && ' ↑'}
                {item.trend === 'down' && ' ↓'}
              </span>
            </div>
          );
          return clickable ? (
            <button key={i} className="w-full text-left hover:bg-muted/40 rounded px-2 py-1 transition-colors" onClick={() => navigate(item.action_link!)}>
              {content}
            </button>
          ) : (
            <div key={i} className="px-2 py-1">{content}</div>
          );
        })}
      </div>
      {payload.cta && (
        <Button variant="ghost" size="sm" className="w-full gap-1 text-primary/70" onClick={() => navigate(payload.cta!.link)}>
          {payload.cta.label} <ArrowRight className="h-3 w-3" />
        </Button>
      )}
    </div>
  );
};
```

- [ ] **Step 2: 创建 LatexRenderer.tsx**

```tsx
import React from 'react';
import Markdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';

interface LatexDerivationPayload {
  title: string;
  steps: Array<{ latex: string; note?: string }>;
}

export const LatexRenderer: React.FC<{ payload: LatexDerivationPayload }> = ({ payload }) => {
  return (
    <div className="p-4 space-y-4 animate-in fade-in duration-300">
      <h3 className="text-sm font-semibold">{payload.title}</h3>
      <div className="space-y-3">
        {payload.steps.map((step, i) => (
          <div key={i} className="space-y-1">
            <div className="text-xs text-muted-foreground/50">步骤 {i + 1}</div>
            <div className="bg-muted/30 rounded-lg p-3">
              <Markdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                {`$$${step.latex}$$`}
              </Markdown>
            </div>
            {step.note && (
              <p className="text-xs text-muted-foreground">{step.note}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
```

- [ ] **Step 3: 创建 StepSolutionRenderer.tsx**

```tsx
import React from 'react';
import Markdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';

interface StepSolutionPayload {
  title: string;
  steps: Array<{ text: string; latex?: string }>;
}

export const StepSolutionRenderer: React.FC<{ payload: StepSolutionPayload }> = ({ payload }) => {
  return (
    <div className="p-4 space-y-4 animate-in fade-in duration-300">
      <h3 className="text-sm font-semibold">{payload.title}</h3>
      <div className="space-y-3">
        {payload.steps.map((step, i) => (
          <div key={i} className="flex gap-3">
            <div className="flex-shrink-0 w-6 h-6 rounded-full bg-primary/10 text-primary text-xs font-semibold flex items-center justify-center">
              {i + 1}
            </div>
            <div className="flex-1 space-y-1">
              <p className="text-sm">{step.text}</p>
              {step.latex && (
                <div className="bg-muted/30 rounded-lg p-2">
                  <Markdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                    {`$$${step.latex}$$`}
                  </Markdown>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
```

- [ ] **Step 4: 创建 KnowledgeMapRenderer.tsx**

```tsx
import React from 'react';

interface KnowledgeNode {
  id: string;
  label: string;
  mastery?: number; // 0-1
}

interface KnowledgeEdge {
  from: string;
  to: string;
}

interface KnowledgeMapPayload {
  title?: string;
  nodes: KnowledgeNode[];
  edges: KnowledgeEdge[];
  highlights?: string[]; // node ids to highlight
}

const masteryColor = (mastery?: number) => {
  if (mastery === undefined) return 'bg-muted';
  if (mastery >= 0.8) return 'bg-emerald-100 text-emerald-700 border-emerald-200';
  if (mastery >= 0.6) return 'bg-blue-100 text-blue-700 border-blue-200';
  if (mastery >= 0.4) return 'bg-amber-100 text-amber-700 border-amber-200';
  return 'bg-red-100 text-red-700 border-red-200';
};

export const KnowledgeMapRenderer: React.FC<{ payload: KnowledgeMapPayload }> = ({ payload }) => {
  return (
    <div className="p-4 space-y-4 animate-in fade-in duration-300">
      {payload.title && <h3 className="text-sm font-semibold">{payload.title}</h3>}
      <div className="flex flex-wrap gap-2">
        {payload.nodes.map((node) => (
          <div
            key={node.id}
            className={`px-3 py-1.5 rounded-lg border text-xs font-medium ${masteryColor(node.mastery)} ${
              payload.highlights?.includes(node.id) ? 'ring-2 ring-primary/40' : ''
            }`}
          >
            {node.label}
            {node.mastery !== undefined && (
              <span className="ml-1 opacity-60">{Math.round(node.mastery * 100)}%</span>
            )}
          </div>
        ))}
      </div>
      {payload.edges.length > 0 && (
        <div className="text-xs text-muted-foreground/50">
          {payload.edges.length} 个关联关系
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 5: 创建 visuals/index.ts — type 分发映射**

```tsx
import React from 'react';
import { DataCardRenderer } from './DataCardRenderer';
import { LatexRenderer } from './LatexRenderer';
import { StepSolutionRenderer } from './StepSolutionRenderer';
import { KnowledgeMapRenderer } from './KnowledgeMapRenderer';

export interface VisualData {
  type: string;
  payload: any;
}

const RENDERERS: Record<string, React.ComponentType<{ payload: any }>> = {
  data_card: DataCardRenderer,
  latex_derivation: LatexRenderer,
  step_solution: StepSolutionRenderer,
  knowledge_map: KnowledgeMapRenderer,
};

export const getVisualRenderer = (type: string) => RENDERERS[type] || null;
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/xiaoyu/visuals/
git commit -m "feat: add visual renderer components (data_card, latex, step_solution, knowledge_map)"
```

---

### Task 7: 前端 — DashboardPanel 重构为 VisualCanvas

**Files:**
- Modify: `frontend/src/pages/xiaoyu/DashboardPanel.tsx`（重写）

**Context:** 现有 DashboardPanel 展示固定的学习数据卡片。重构为 VisualCanvas，接收 visual 数据并分发到对应 renderer。空画布显示提示文字。

- [ ] **Step 1: 重写 DashboardPanel.tsx 为 VisualCanvas**

```tsx
import React from 'react';
import { getVisualRenderer, type VisualData } from './visuals';

interface VisualCanvasProps {
  visual: VisualData | null;
}

export const VisualCanvas: React.FC<VisualCanvasProps> = ({ visual }) => {
  if (!visual) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center space-y-2">
          <p className="text-sm text-muted-foreground/40">小宇会在对话中为你生成可视化内容</p>
          <p className="text-xs text-muted-foreground/25">数学推导、解题步骤、知识图谱、学习数据</p>
        </div>
      </div>
    );
  }

  const Renderer = getVisualRenderer(visual.type);
  if (!Renderer) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-sm text-muted-foreground/40">不支持的可视化类型: {visual.type}</p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto">
      <Renderer payload={visual.payload} />
    </div>
  );
};

// 保留旧的 DashboardPanel export 用于兼容（内部转发到 VisualCanvas）
export { VisualCanvas as DashboardPanel };
export type { VisualData as DashboardData };
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: 无报错

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/xiaoyu/DashboardPanel.tsx
git commit -m "feat: refactor DashboardPanel to VisualCanvas with type dispatch"
```

---

### Task 8: 前端 — XiaoYu.tsx 更新

**Files:**
- Modify: `frontend/src/pages/XiaoYu.tsx`

**Context:** 需要更新三处：Landing 文案 + SKILLS 扩展、处理 SSE/WS 中的 visual 事件、加载历史时恢复 visual。

- [ ] **Step 1: 更新 Landing 文案**

将 greeting 区域的标题和副标题替换为新文案：

```tsx
<h1 className="text-base font-semibold tracking-tight text-foreground/90">小宇XiaoYu让学习更具效率。对话即学习。</h1>
<p className="text-[11px] text-muted-foreground/50">最懂你的学习agent，从数据分析到知识讲解，一个入口搞定</p>
```

- [ ] **Step 2: 扩展 SKILLS 列表**

在现有 5 个技能之后新增知识问答类技能：

```tsx
const SKILLS = [
  { icon: Target, label: '分析薄弱点', prompt: '帮我分析薄弱知识点，给出提升建议' },
  { icon: CalendarCheck, label: '制定学习计划', prompt: '根据我的现状制定一份学习计划' },
  { icon: CheckCircle2, label: '查看复习任务', prompt: '帮我看看今天有哪些需要复习的内容' },
  { icon: BarChart3, label: '学习数据总览', prompt: '帮我分析学习数据，看看整体情况' },
  { icon: BookOpen, label: '推荐课程', prompt: '根据我的薄弱点推荐适合的课程' },
  { icon: Lightbulb, label: '解释一个概念', prompt: '请帮我讲解一个知识点' },
  { icon: MessageCircleQuestion, label: '分析一道题', prompt: '帮我分析这道题的解题思路' },
  { icon: BrainCircuit, label: '总结知识点', prompt: '帮我总结某个知识点的核心内容' },
];
```

需要从 lucide-react 导入 `MessageCircleQuestion` 和 `BrainCircuit`。

- [ ] **Step 3: 新增 visual 状态和 SSE visual 事件处理**

在组件顶部新增 visual 状态：

```tsx
const [visual, setVisual] = useState<VisualData | null>(null);
```

在 SSE 消息处理的 step done 分支中，检测 render_visual 并更新 visual 状态：

```tsx
} else if (step.status === 'done') {
  // render_visual 的结果更新 Dashboard
  if (step.name === 'render_visual' && step.visual) {
    setVisual(step.visual);
  }
  // ... 现有的 done 处理逻辑
}
```

- [ ] **Step 4: 加载历史会话时恢复 visual**

在 `handleLoadSession` 和初始化加载逻辑中，从消息列表中提取最后一条带 visual 的消息：

```tsx
const extractLastVisual = (msgs: Message[]): VisualData | null => {
  for (let i = msgs.length - 1; i >= 0; i--) {
    const m = msgs[i];
    if (m.metadata?.visual) return m.metadata.visual;
  }
  return null;
};
```

在 `handleLoadSession` 中：

```tsx
const handleLoadSession = useCallback((session: ConversationSession) => {
  setMessages(session.messages);
  setActiveSessionId(session.id);
  setVisual(extractLastVisual(session.messages));
  setSessionOpen(false);
}, []);
```

需要扩展 Message 接口，增加 `metadata` 字段：

```tsx
interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: string;
  toolStep?: AgentStep;
  inlineCard?: { ... };
  metadata?: { visual?: VisualData };
  visible?: boolean;
  _id?: string;
}
```

- [ ] **Step 5: 将 visual 传递给 VisualCanvas**

在双栏布局中，将 DashboardPanel 替换为 VisualCanvas 并传入 visual：

```tsx
<div className="flex-1 min-w-0 h-full">
  <VisualCanvas visual={visual} />
</div>
```

- [ ] **Step 6: 新对话时重置 visual**

在 `handleReset` 中清除 visual 状态：

```tsx
const handleReset = useCallback(async () => {
  // ... 现有逻辑
  setVisual(null);
  // ...
}, [bot]);
```

- [ ] **Step 7: 验证 TypeScript 编译**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: 无报错

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/XiaoYu.tsx
git commit -m "feat: update XiaoYu landing copy, skills, and visual event handling"
```

---

### Task 9: 后端 — 更新 Agent 架构文档

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: 更新 Agent 架构表格中的工具数**

小宇工具数从 18 变为 19（新增 render_visual）。

- [ ] **Step 2: 更新关键路由表（如有变化）**

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for visual dashboard architecture"
```

---

### Task 10: 验证 — 端到端冒烟测试

- [ ] **Step 1: 后端检查**

```bash
make backend-check
```

Expected: 无报错

- [ ] **Step 2: 前端检查**

```bash
make frontend-check
```

Expected: 无报错

- [ ] **Step 3: 手动验证 — Landing 页**

启动开发服务器，访问 `/xiaoyu`，确认：
- 新标题文案显示正确
- 技能按钮扩展到 7-8 个
- 输入框 placeholder 正常轮播

- [ ] **Step 4: 手动验证 — 知识问答场景**

发送"帮我讲解极限的定义"，确认：
- 小宇正常回答
- 如果小宇调用了 render_visual → Dashboard 显示 LaTeX 推导
- 空画布默认提示在无 visual 时显示

- [ ] **Step 5: 手动验证 — 数据分析场景**

发送"帮我分析薄弱知识点"，确认：
- 小宇调用工具获取数据
- 如果调用了 render_visual(type=data_card) → Dashboard 显示数据卡片

- [ ] **Step 6: 手动验证 — 历史恢复**

刷新页面，加载刚才的历史会话，确认：
- Dashboard 恢复最后的 visual 内容

- [ ] **Step 7: 手动验证 — 新对话**

点击"新对话"，确认：
- Dashboard 回到空画布
