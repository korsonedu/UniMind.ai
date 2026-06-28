# 测试同事工作流

你负责：**Eular 发版 → 你拉到本地 → 手工测试 → 提需求/报 bug → Eular 修改**。

## 一、环境准备（一次性）

```bash
# 1. 克隆仓库
git clone git@github.com:xxx/UniMindCode.git
cd UniMindCode

# 2. 后端
cd backend
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 编辑 .env，填入本地数据库配置

# 3. 前端
cd ../frontend
npm install
```

## 二、日常测试流程

### 每次测试前

```bash
# 1. 拉最新代码
git fetch origin main
git checkout main
git reset --hard origin/main   # 丢弃本地所有改动，确保干净

# 2. 更新依赖（如有变更）
cd backend && source venv/bin/activate && pip install -r requirements.txt
cd ../frontend && npm install

# 3. 数据库迁移
cd backend && source venv/bin/activate
python manage.py migrate

# 4. 启动服务
# 终端1: 后端
cd backend && source venv/bin/activate && python manage.py runserver

# 终端2: 前端
cd frontend && npm run dev

# 终端3: 异步任务（出题等功能需要）
cd backend && source venv/bin/activate && celery -A school_system worker -l info
```

前端默认 `http://localhost:5173`，后端 `http://localhost:8000`。

### 版本号确认

问 Eular 当前测试的是哪个版本，或自己看：

```bash
git tag --sort=-creatordate | head -5   # 最近5个版本
```

## 三、测试要点

按 Eular 发的 CHANGELOG 逐项验证。重点关注：

| 维度 | 查什么 |
|------|--------|
| **新功能** | 按 CHANGELOG 的 Added 逐条走通 |
| **修复项** | 按 CHANGELOG 的 Fixed 确认不再复现 |
| **回归** | 登录、刷题、支付、小宇对话 — 核心流程不能挂 |
| **边界** | 空数据、超长输入、网络断开、快速连续点击 |

## 四、提需求 / 报 Bug

### 在哪里提

Eular 会告诉你在哪提（GitHub Issues / 飞书 / 群聊）。

### 怎么写

每个问题/需求包含：

```
标题：一句话说清楚

复现步骤：
1. 打开 xxx 页面
2. 点击 xxx
3. 输入 xxx

预期：应该 xxx
实际：xxx

截图/录屏：（附上）
```

**一条 issue 只写一个问题。** 不要在一大段里混多个问题。

## 五、Git 规则（你的版本）

完整规则 Eular 遵守，你只需要记住这几条：

### ✅ 你可以做

```bash
git fetch origin          # 拉取最新代码信息
git checkout main         # 切换到 main 分支
git reset --hard origin/main  # 重置到远程最新（丢弃本地改动）
git log --oneline -20     # 看最近提交
git tag --sort=-creatordate | head -10  # 看版本列表
```

### ❌ 绝对不要做

- **不要 `git push`** — 任何分支都不要推
- **不要 `git commit`** — 你不改代码，不需要提交
- **不要 `git merge` / `git rebase`** — 你只管拉取，不管合并
- **不要在 main 上改任何文件** — 如果误改了，`git reset --hard origin/main` 恢复

> **简单记：你只读不写。** 除了改 `.env` 配本地数据库，不碰任何代码文件。

## 六、常见问题

### 拉代码时说有本地改动？

```bash
git status                    # 看看改了什么
git reset --hard origin/main  # 全部丢弃
```

### 数据库迁移报错？

```bash
cd backend && source venv/bin/activate
python manage.py migrate --fake-initial   # 跳过已存在的表
```

### 端口被占用？

```bash
lsof -i :8000   # 看谁占着后端端口
lsof -i :5173   # 看谁占着前端端口
kill <PID>      # 杀掉
```

### 环境彻底乱了？

从头来：
```bash
git reset --hard origin/main
cd backend && source venv/bin/activate && python manage.py migrate
```

---

> 有问题随时问 Eular。环境搭不起来别硬扛，让他帮你过一遍。
