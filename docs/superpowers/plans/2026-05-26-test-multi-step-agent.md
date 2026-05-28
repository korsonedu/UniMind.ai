# 测试：多步可见 Agent

## 前置条件

1. 后端运行中（`cd backend && python3 manage.py runserver`）
2. 前端运行中（`cd frontend && npm run dev`）
3. 有可用的 exam_generator bot（id=5）或 planner bot（id=4）

## 测试步骤

### 1. 后端 WebSocket 连通性

```bash
# 用已登录的 cookie 测试 WS 连接
# 先从浏览器 DevTools > Application > Cookies 复制 sessionid 和 csrftoken

# 测试 WS 端点是否可达（无认证应返回 403，说明路由生效）
python3 -c "
import asyncio, websockets
async def test():
    try:
        ws = await asyncio.wait_for(websockets.connect('ws://127.0.0.1:8000/ws/ai/chat/5/'), timeout=5)
        print('Connected!')
        await ws.close()
    except websockets.exceptions.InvalidStatus as e:
        print(f'HTTP {e.response.status_code} (403=路由正常，需认证)')
    except Exception as e:
        print(f'{type(e).__name__}: {e}')
asyncio.run(test())
"
```

预期：返回 `HTTP 403`（路由匹配但未认证），不是 `HTTP 500`（路由不存在）

### 2. Django 系统检查

```bash
cd backend && python3 manage.py check
```

预期：`System check identified no issues (0 silenced)`

### 3. 前端构建检查

```bash
cd frontend && npx tsc -b 2>&1 | grep -E "(AgentStepCard|useAgentChat|AIAssistant)" || echo "我们的文件无 TS 错误"
```

预期：`我们的文件无 TS 错误`

### 4. 功能测试（浏览器）

1. 打开前端，登录（用有权限的账号）
2. 进入 AI 助手页面，选择「出题助手」（exam_generator, bot_id=5）
3. 发送：`帮我出 5 道高中数学导数题`
4. **观察**：
   - 对话流中应出现折叠卡片，显示如"搜索知识点「导数」"、"基于 X 个知识点生成 5 道题"等
   - 每张卡片：spinner（进行中）→ 绿色勾（完成）
   - 点击卡片可展开查看参数和结果摘要
   - 最终文本回复逐字出现（流式）
   - 完成后文本合并到历史消息，步骤卡片消失
5. 切换到「小宇」（planner, bot_id=4），发：`帮我制定本周学习计划`
6. **观察**：同样应显示步骤卡片（获取学习数据、查询复习任务等）

### 5. 对照测试

1. 选择「科晟全能导师」（assistant, bot_id=1）
2. 发送任意问题
3. **预期**：走原有 polling 模式，`[Thinking...]` 转圈 → 一次性返回答案，无步骤卡片

### 6. 错误场景

- WS 断开时前端不崩溃（刷新页面应恢复正常）
- 发空消息时 WS 返回 error 事件

## 验证清单

- [x] `python3 manage.py check` 通过
- [x] WS 路由可达（返回 403 而非 500）
- [x] 前端 TS 编译无 AgentStepCard/useAgentChat/AIAssistant 相关错误
- [ ] exam_generator 发消息后出现步骤卡片
- [ ] planner 发消息后出现步骤卡片
- [ ] assistant bot 保持原有 polling 模式
- [ ] 步骤卡片可展开查看详情
- [ ] 文本回复逐 token 流式输出
- [ ] 完成后步骤卡片消失，最终消息进入历史
