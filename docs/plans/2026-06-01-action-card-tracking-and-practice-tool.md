# Action Card 追踪 + 小宇抽题能力 实现计划

> 两个需求：1) Action Cards 追踪完成状态  2) 小宇新工具：抽取相关题目

---

## Part 1: Action Card 追踪

### 目标
学生通过 action card 做题/看视频后，卡片标记"已完成"，数据记录到后端，可面向 VC 展示数据。

### Task 1.1: 新增 ActionCardInteraction Model
- 文件: `backend/ai_assistant/models.py`
- 字段: user, card_title, card_action_type, card_action_url, card_icon, completed, completed_at, metadata
- 索引: (user, card_action_url) 唯一

### Task 1.2: Migration
- `python manage.py makemigrations ai_assistant`

### Task 1.3: 新增 API 端点
- POST `/api/ai/card-interactions/` — 记录点击/完成
- GET `/api/ai/card-interactions/` — 查询用户卡片完成状态
- 文件: `backend/ai_assistant/views.py`, `backend/ai_assistant/urls.py`

### Task 1.4: 前端 ActionCardsRenderer 更新
- 卡片右上角显示 ✅ 已完成标签
- 点击时 POST 记录
- 跳转回来后检查 URL 参数判断是否完成
- 文件: `frontend/src/pages/xiaoyu/visuals/ActionCardsRenderer.tsx`

### Task 1.5: 前端 API 函数
- 文件: `frontend/src/lib/api.ts` 新增 cardInteractions API

---

## Part 2: 小宇抽取相关题目

### 目标
小宇能根据知识点/薄弱点从题库中抽取真实题目，通过 action_cards 推荐给学生做。

### Task 2.1: 新增 get_practice_questions 工具 Handler
- 文件: `backend/ai_assistant/services/tool_executor.py` (PlannerToolExecutor)
- 按知识点、难度、题型筛选题目
- 排除已掌握的题目
- 返回题目列表（不含答案，前端做题用）

### Task 2.2: 工具 Schema + 注册
- 文件: `backend/ai_engine/tools.py` — 新增 GET_PRACTICE_QUESTIONS_SCHEMA + _make_tool
- 文件: `backend/ai_engine/tool_router.py` — PLANNER_TOOLS_META + PLANNER_INTENT_MAP

### Task 2.3: Prompt 更新
- 文件: `backend/prompts/ai_assistant/bots/xiaoyu/tool_guide.txt`

### Task 2.4: 前端 — 做题卡片支持
- quiz action card 点击后跳转到 `/quiz/practice?ids=1,2,3`
- 或者 inline 做题组件
