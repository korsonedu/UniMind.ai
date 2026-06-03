# VisualCanvas 从独立面板改为内联卡片

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 把小宇页面的 VisualCanvas 从 split-view 独立左侧面板改为对话流内的内联卡片，消除空板、改善视觉-对话连贯性。

**Architecture:** AgentChatLayout 新增 `layout` 模式支持。`'split'`（默认，Workbench 不受影响）保持现有左右分屏；`'inline'`（小宇使用）去掉左侧面板，chat 占满宽度，`render_visual` 工具步骤渲染为内联 VisualCard 而非 ToolStepMessage。所有 6 种 visual renderer（data_card、latex_derivation、step_solution、knowledge_map、action_cards、function_graph）原样保留，只改渲染容器。

**Tech Stack:** React 19, TypeScript, Tailwind CSS, shadcn/ui

**影响范围:**
- 修改: `AgentChatLayout.tsx`（核心布局组件）
- 修改: `XiaoYu.tsx`（切换到 inline 模式）
- 新增: `InlineVisualCard.tsx`（内联卡片包装组件）
- 不动: `Workbench.tsx`（保持 split 模式）
- 不动: `visuals/` 目录下所有 renderer（原样复用）
- 不动: `useAgentConversation.ts`、`useAgentChat.ts`（数据流不变）

---

### Task 1: 创建 InlineVisualCard 包装组件

**Objective:** 创建一个内联卡片容器组件，包装现有 visual renderer，使其适合嵌入对话流。

**Files:**
- Create: `frontend/src/components/InlineVisualCard.tsx`

**Step 1: 创建组件**

```tsx
// frontend/src/components/InlineVisualCard.tsx
import React from 'react';
import { getVisualRenderer, type VisualData } from '@/pages/xiaoyu/visuals';
import { cn } from '@/lib/utils';

interface InlineVisualCardProps {
  visual: VisualData;
  index?: number;
}

const PRIORITY_STYLES: Record<string, string> = {
  high: 'col-span-full',
  normal: '',
  low: 'opacity-80',
};

export const InlineVisualCard: React.FC<InlineVisualCardProps> = React.memo(({ visual, index = 0 }) => {
  const Renderer = getVisualRenderer(visual.type);
  if (!Renderer) {
    return (
      <div className="flex w-full">
        <div className="max-w-[85%] rounded-lg border border-border/40 bg-muted/30 px-3 py-2">
          <p className="text-[11px] text-foreground/30">不支持的可视化类型: {visual.type}</p>
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        'flex w-full animate-in fade-in slide-in-from-bottom-1 duration-300',
        PRIORITY_STYLES[visual.priority || 'normal'],
      )}
      style={{ animationDelay: `${Math.min(index * 40, 200)}ms` }}
    >
      <div className="w-full max-w-[90%] rounded-xl border border-border/50 bg-card overflow-hidden">
        <div className="p-3">
          <Renderer payload={visual.payload} />
        </div>
      </div>
    </div>
  );
});

InlineVisualCard.displayName = 'InlineVisualCard';
```

**Step 2: 验证**

```bash
cd frontend && npx tsc --noEmit --pretty
```
Expected: 无报错。

**Step 3: Commit**

```bash
git add frontend/src/components/InlineVisualCard.tsx
git commit -m "feat: add InlineVisualCard component for inline visual rendering"
```

---

### Task 2: AgentChatLayout 支持 inline 布局模式

**Objective:** 给 AgentChatLayout 添加 `layout` prop，在 `layout='inline'` 时去掉 split-view，chat 占满宽度，并将 render_visual 步骤渲染为 InlineVisualCard。

**Files:**
- Modify: `frontend/src/components/AgentChatLayout.tsx`

**Step 1: 添加 layout prop 到接口**

在 `AgentChatLayoutProps` 接口中添加：

```tsx
export interface AgentChatLayoutProps {
  // ... existing props ...

  /** 布局模式。'split' = 左右分屏（默认），'inline' = 单栏对话流 */
  layout?: 'split' | 'inline';

  // Right panel（仅 split 模式使用）
  renderRightPanel?: (props: RightPanelProps) => React.ReactNode;
}
```

注意：`renderRightPanel` 变为可选（加 `?`）。

**Step 2: 在组件顶部解构 layout prop**

```tsx
export default function AgentChatLayout(props: AgentChatLayoutProps) {
  const {
    findBot, skills, typewriterWords, chatPlaceholder, resetMessage,
    landingTitle, landingDescription, skillTooltip = '技能',
    botDisplayName,
    processContent,
    getExtraPayload, onStepDone, onDone,
    extractVisualFromStep,
    onLoadSession, onReset, onDeleteSession,
    renderRightPanel,
    layout = 'split',  // 新增
  } = props;
```

**Step 3: import InlineVisualCard**

在文件顶部添加：

```tsx
import { InlineVisualCard } from '@/components/InlineVisualCard';
import type { VisualData } from '@/pages/xiaoyu/visuals';
```

（VisualData 类型已有 import，检查是否冲突）

**Step 4: 修改 Chat State 的渲染逻辑**

将 Chat State 的 return 替换为根据 layout 模式分支渲染：

```tsx
// ── Chat state ──

// inline 模式：全宽单栏对话流，visual 内联
if (layout === 'inline') {
  return (
    <TooltipProvider delayDuration={300}>
      <div className="h-full flex flex-col animate-in fade-in duration-300">
        {/* Header */}
        <div className="h-10 shrink-0 px-4 flex items-center justify-between border-b border-border/40">
          <div className="flex items-center gap-1.5">
            <span className="text-[12px] font-semibold text-foreground/80">{botDisplayName}</span>
            {sessions.length > 1 && (
              <Popover open={sessionOpen} onOpenChange={setSessionOpen}>
                <PopoverTrigger asChild>
                  <button className="text-[9px] text-muted-foreground/40 hover:text-foreground/60 transition-colors">
                    {sessions.length} 个对话
                  </button>
                </PopoverTrigger>
                <PopoverContent align="start" side="bottom" className="w-56 p-1 rounded-lg border-border/60 shadow-lg max-h-52 overflow-y-auto">
                  <div className="space-y-0.5">
                    {[...sessions].reverse().map(session => (
                      <div key={session.id}
                        className={cn("w-full flex items-start gap-1 px-2 py-1.5 rounded-md transition-colors group", session.id === activeSessionId ? "bg-muted/50" : "hover:bg-muted/50")}>
                        <button onClick={() => { wrappedLoadSession(session); }}
                          className="flex-1 flex flex-col gap-0.5 text-left min-w-0">
                          <span className="text-[11px] font-medium truncate">{session.label}</span>
                          <span className="text-[9px] text-muted-foreground/50">
                            {session.messages.length} 条消息
                            {session.lastTime && ` · ${new Date(session.lastTime).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`}
                          </span>
                        </button>
                        {onDeleteSession && session.id !== activeSessionId && (
                          <button onClick={(e) => { e.stopPropagation(); onDeleteSession(session); }}
                            className="shrink-0 mt-0.5 p-0.5 rounded opacity-0 group-hover:opacity-100 text-muted-foreground/40 hover:text-destructive transition-all">
                            <Trash2 className="h-2.5 w-2.5" />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                </PopoverContent>
              </Popover>
            )}
          </div>
          <Button variant="ghost" size="sm" onClick={wrappedReset}
            className="rounded text-muted-foreground/40 hover:text-foreground/60 gap-0.5 px-1.5 h-5">
            <RotateCcw className="h-2.5 w-2.5" />
            <span className="text-[9px] font-medium">新对话</span>
          </Button>
        </div>

        {/* Messages — 内联视觉卡片 */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto min-h-0">
          <div className="max-w-3xl mx-auto p-4 space-y-3">
            {messages.filter(m => m.role === 'user' || m.visible !== false).map((msg, i) => {
              // render_visual 步骤 → 内联 VisualCard
              if (msg.toolStep?.name === 'render_visual' && msg.toolStep.status === 'done' && msg.toolStep.visual) {
                return (
                  <InlineVisualCard
                    key={msg._id || i}
                    visual={msg.toolStep.visual as VisualData}
                    index={i}
                  />
                );
              }
              // 其他工具步骤 → ToolStepMessage
              if (msg.toolStep) {
                return <ToolStepMessage key={msg._id || i} step={msg.toolStep} index={i} />;
              }
              // 普通消息 → ChatBubble
              return <ChatBubble key={msg._id || i} msg={msg} isUser={msg.role === 'user'} index={i} />;
            })}
            {loading && (
              <ChatBubble msg={{ role: 'assistant', content: '' }} isUser={false} isThinking index={messages.length} />
            )}
          </div>
        </div>

        {/* Input */}
        <div className="shrink-0 p-4 border-t border-border/40">
          <div className="max-w-3xl mx-auto">
            <div className="flex items-center gap-0 mb-1 ml-0.5">
              <Popover open={skillOpen} onOpenChange={setSkillOpen}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <PopoverTrigger asChild>
                      <button className={cn("p-1 rounded transition-colors", skillOpen ? "text-primary/60" : "text-muted-foreground/40 hover:text-foreground/60")}>
                        <Lightbulb className="h-3 w-3" />
                      </button>
                    </PopoverTrigger>
                  </TooltipTrigger>
                  <TooltipContent side="top" className="text-[10px]">{skillTooltip}</TooltipContent>
                </Tooltip>
                <PopoverContent align="start" side="top" className="w-48 p-1 rounded-lg border-border/60 shadow-lg">
                  <div className="space-y-0.5">
                    {skills.map(skill => (
                      <button key={skill.label} onClick={() => handleSkillSelect(skill.prompt)}
                        className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded-md hover:bg-muted/50 transition-colors text-left">
                        <skill.icon className="h-3 w-3 shrink-0 text-muted-foreground/40" />
                        <span className="text-[11px] font-medium">{skill.label}</span>
                      </button>
                    ))}
                  </div>
                </PopoverContent>
              </Popover>
            </div>
            <div className="flex items-center gap-1.5 bg-card rounded-xl p-1 border border-border/60 transition-all duration-200 focus-within:border-border">
              <Input
                value={input}
                onChange={e => setInput(e.target.value)}
                onCompositionStart={() => setIsComposition(true)}
                onCompositionEnd={() => setIsComposition(false)}
                onKeyDown={e => { if (e.key === 'Enter' && !isComposing) { e.preventDefault(); handleSend(); } }}
                placeholder={chatPlaceholder}
                autoComplete="off"
                className="bg-transparent border-none shadow-none focus-visible:ring-0 text-[13px] h-9 px-3 placeholder:text-muted-foreground/40"
                disabled={loading}
              />
              <Button onClick={handleSend} disabled={loading || !input.trim()} size="icon"
                className="rounded-lg h-9 w-9 bg-foreground text-background shadow-none active:scale-95 transition-all shrink-0 hover:opacity-90">
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}

// split 模式：原有左右分屏（保持不变）
return (
  <TooltipProvider delayDuration={300}>
    <div className="h-full flex animate-in fade-in duration-300">
      {/* ... 原有 split 代码完全不变 ... */}
    </div>
  </TooltipProvider>
);
```

**Step 5: 处理 inline 模式下 visual 数据流的简化**

在 inline 模式下，不再需要 `visual` state 和 `pendingVisualsRef` 来收集 visual 后传递给右侧面板。visual 直接附加在 `msg.toolStep.visual` 上，由渲染逻辑直接读取。

但现有的 `onStepDone` 回调已经在 XiaoYu.tsx 中将 `step.visual` 写入 `msg.toolStep`（第 48-50 行的 `onStepDone` 回调），所以 inline 模式下 visual 数据已经在消息上了，不需要额外处理。

`visual` state 和 `pendingVisualsRef` 在 inline 模式下不使用即可，无需删除（split 模式仍需要）。

**Step 6: 验证**

```bash
cd frontend && npx tsc --noEmit --pretty
```
Expected: 无报错。

**Step 7: Commit**

```bash
git add frontend/src/components/AgentChatLayout.tsx
git commit -m "feat: add inline layout mode to AgentChatLayout"
```

---

### Task 3: XiaoYu 切换到 inline 模式

**Objective:** 修改 XiaoYu.tsx 使用 `layout='inline'`，去掉 split 模式下的右侧面板。

**Files:**
- Modify: `frontend/src/pages/XiaoYu.tsx`

**Step 1: 精简 XiaoYu.tsx**

```tsx
import React from 'react';
import { Target, CalendarCheck, CheckCircle2, BarChart3, BookOpen, Lightbulb, MessageCircleQuestion, BrainCircuit } from 'lucide-react';
import AgentChatLayout from '@/components/AgentChatLayout';
import type { Bot, ConversationSession } from '@/hooks/useAgentConversation';

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

export const XiaoYu: React.FC = () => {
  return (
    <AgentChatLayout
      layout="inline"
      findBot={(bots) => bots.find((b: Bot) => b.name === '小宇')}
      skills={SKILLS}
      typewriterWords={['让小宇帮你制定学习计划', '让小宇分析薄弱知识点', '让小宇推荐适合的课程', '让小宇看看复习进度']}
      chatPlaceholder="和小宇对话..."
      resetMessage="已开始新对话"
      landingTitle="小宇XiaoYu让学习更具效率。对话即学习。"
      landingDescription="最懂你的学习agent，从数据分析到知识讲解，一个入口搞定"
      botDisplayName="小宇"
      onDeleteSession={() => {}}
      onLoadSession={(session, defaultHandler) => {
        defaultHandler(session);
      }}
      onDone={(refreshSessions) => {
        refreshSessions();
      }}
      onStepDone={(step, prev) => {
        return prev.map(m =>
          m.toolStep?.call_id === step.call_id ? { ...m, toolStep: step } : m
        );
      }}
    />
  );
};

export default XiaoYu;
```

**变更说明:**
- 添加 `layout="inline"`
- 删除 `extractVisualFromStep`（inline 模式下 visual 直接从 step 读取）
- 删除 `renderRightPanel`（inline 模式不需要右侧面板）
- 删除 `VisualCanvas` import
- 删除 `RightPanelProps` import
- 删除 `extractLastVisual` 函数（不再需要）
- 删除 `Message` import（不再需要，只保留 `Bot` 和 `ConversationSession`）

**Step 2: 验证编译**

```bash
cd frontend && npx tsc --noEmit --pretty
```
Expected: 无报错。

**Step 3: Commit**

```bash
git add frontend/src/pages/XiaoYu.tsx
git commit -m "feat: switch XiaoYu to inline visual layout"
```

---

### Task 4: 构建验证 + 清理

**Objective:** 确保完整构建通过，清理不再需要的死代码。

**Files:**
- Verify: `frontend/src/pages/xiaoyu/DashboardPanel.tsx`（保留，Workbench 或未来可能用）
- Verify: `frontend/src/pages/Workbench.tsx`（不受影响）

**Step 1: 完整构建**

```bash
cd frontend && npm run build
```
Expected: 构建成功，无错误。

**Step 2: 检查 Workbench 不受影响**

打开命题官页面（`/workbench`），确认：
- 左侧 QuestionPanel 仍然正常显示
- 右侧聊天面板正常
- split-view 布局不变

**Step 3: 检查小宇页面**

打开小宇页面（`/xiaoyu`），确认：
- 无左右分屏，聊天占满宽度
- 发送消息后，render_visual 步骤渲染为内联卡片
- 各类 visual（data_card、step_solution、knowledge_map 等）正常显示
- 工具步骤（非 render_visual）仍显示为 ToolStepMessage
- 输入框、技能选择、历史对话功能正常

**Step 4: 如果一切正常，部署**

```bash
git add -A
git commit -m "feat: inline visual cards for XiaoYu page"
# push 到远程
git push
```

---

## 不在本次范围内（后续可做）

- **Workbench 也改为 inline 模式**：命题官的 QuestionPanel 可以类似地内联到对话流中，但需要单独规划
- **landing 页面优化**：当前 landing 还是居中输入框 + 技能标签，可以进一步优化为小宇主动开口的样式
- **移动端适配**：inline 模式天然支持移动端，但需要单独测试和微调间距
