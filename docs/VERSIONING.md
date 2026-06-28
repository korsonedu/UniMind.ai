# UniMind.ai 版本管理规范

## 一、版本号规则（SemVer 变体）

```
vMAJOR.MINOR.PATCH[-suffix]
```

| 字段 | 何时 bump | 举例 |
|------|----------|------|
| MAJOR | 产品大版本：架构重构、数据库 schema 大改（不兼容旧数据）、商业模式变更 | v3.0.0 |
| MINOR | 功能里程碑：新 Agent、新完整模块（支付、课程、面试等）、大型 UI 改版 | v2.10.0 |
| PATCH | 日常迭代：bugfix、小功能、优化、安全补丁、prompt 调优 | v2.9.3 |

### suffix 后缀

| 后缀 | 含义 | 场景 |
|------|------|------|
| -dev | 开发中 | 功能未全部完成，开发期标记（当前默认） |
| -rc.N | 候选版 | 功能完成，待测试/验收 |
| 无后缀 | 正式版 | 测试通过，发布到生产 |

示例生命周期：
```
v2.10.0-dev  →  v2.10.0-rc.1  →  v2.10.0-rc.2  →  v2.10.0
```

---

## 二、何时推送（Push）

### 必须立即 push 的情况
1. **修复线上 bug**（hotfix）— 修完即推
2. **安全漏洞修复** — 修完即推
3. **BLOCKER 问题**（影响登录/支付/核心流程）

### 功能开发期间
- 每个**逻辑完整的功能点**完成后 push（不要攒到巨量再推）
- 一个 PR / 一个功能点 = 一个 push
- 开发期间 commit 到 feature 分支，功能完成合并到 main 再 push

### 版本发布时
- 版本号 bump 后 push
- 同步更新 CHANGELOG.md

---

## 三、Commit Message 规范（Conventional Commits）

```
<type>(<scope>): <subject>

<body>   ← feat/fix/hotfix/refactor 必须写（what + why）；chore/docs/test 可选
```

### type 类型

| type | 含义 | 触发 MINOR/PATCH |
|------|------|-----------------|
| feat | 新功能 | MINOR |
| fix | bug 修复 | PATCH |
| fix(security) | 安全修复 | PATCH |
| refactor | 重构（无功能变更） | — |
| perf | 性能优化 | — |
| style | 代码风格/UI 样式 | — |
| docs | 文档 | — |
| test | 测试 | — |
| chore | 构建/依赖/配置 | — |
| chore(migration) | 数据库迁移 | — |
| revert | 回滚 | — |

### scope 范围（可选，推荐）

```
ai_engine, ai_assistant, quizzes, users, courses, frontend,
payments, core, prompts, docs, deploy, deps
```

### 示例

```bash
# 好的 commit message
feat(ai_assistant): 新增 render_visual 工具，支持 4 类可视化卡片
fix(quizzes): 修复模拟考试提交时 race condition
fix(security): 文件上传 magic bytes 校验扩展到视频/文档
refactor(courses): OSS 分片直传重构，删除 5 个旧 View
chore(migration): 移除废弃的 assistant bot_type
docs: 更新 CHANGELOG 至 v1.1.0

# 差的 commit message（不要这样写）
update code
fix bug
wip
```

### 多文件改动怎么办

一个逻辑改动涉及多文件，**一个 commit**：
```bash
git add backend/ai_assistant/ frontend/src/components/
git commit -m "feat(ai_assistant): render_visual 工具 + 前端 VisualCanvas 组件"
```

如果一次做了多个不相关的改动，**拆成多个 commit**：
```bash
# commit 1: 安全修复
git commit -m "fix(security): 修复 SVG XSS 漏洞，从白名单移除 .svg"

# commit 2: 新功能
git commit -m "feat(quizzes): 新增错题本导出 PDF 功能"
```

---

## 四、版本发布流程

```
1. 功能全部完成
   ↓
2. 更新 CHANGELOG.md（合并本轮所有 commit 为人类可读的变更记录）
   ↓
3. bump 版本号（去掉 -dev 后缀，或升 MINOR/PATCH）
   ↓
4. git tag v2.10.0
   ↓
5. git push + git push --tags
   ↓
6. 服务器 git pull + npm build + systemctl restart
   ↓
7. 再次迭代时，在 CHANGELOG 顶部开新的 -dev 版本头
```

---

## 五、分支策略

**强制分支隔离**：任何代码改动必须建分支。main 不接受直接提交。

```
main                          ← 唯一长期分支，永远可部署
  ├─ feat/render-visual       ← 功能分支
  ├─ fix/upload-race          ← bugfix 分支
  └─ hotfix/security-svg      ← 紧急修复
```

详细规则见 Git 铁律（project_git_governance memory）。

---

## 六、CHANGELOG.md 模板

```markdown
## vX.Y.Z — 标题 (YYYY-MM-DD)

### Added
- 新功能描述

### Fixed
- 修复描述

### Changed
- 变更描述

### Docs
- 文档更新描述
```

---

## 七、版本号快速参考

```
当前版本:  v1.2.0
下次 MINOR: v1.3.0（新模块/大功能上线时）
下次 PATCH: v1.2.1（日常迭代）
下次 MAJOR: v2.0.0（架构大改/商业模式变更）
```
