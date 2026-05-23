# PdfMockExam 重构 + 全局移动端响应式 — 设计文档

**日期**: 2026-05-21
**状态**: 设计完成，待实施

---

## 1. 密卷页面重构

### 1.1 文件拆分

```
frontend/src/pages/PdfMockExam.tsx          # 主页面（Tab 切换 + 数据加载 + 轮询）
frontend/src/components/exam/
  ├── AiExamTab.tsx          # AI 生成密卷列表
  ├── TeacherExamTab.tsx     # 名师精选密卷列表 + 教师管理区域
  ├── PublishExamForm.tsx    # 发布试卷内联表单（替代弹窗）
  ├── SubmissionPanel.tsx    # 提交批改内联面板（替代弹窗）
  └── types.ts               # 共享类型
```

### 1.2 主页面结构

PdfMockExam.tsx 精简为：
- `activeTab` 状态切换 (ai | teacher)
- `loadData()` 集中数据加载，同时拉取 AI 和 Teacher 列表
- 自动轮询：processing 状态记录每 5s 刷新
- `<AiExamTab>` / `<TeacherExamTab>` 渲染

### 1.3 教师工作流

**状态定义：**
```typescript
type SubmissionStatus = 'not_submitted' | 'submitted' | 'graded';
```

**学生视角：**
- 未提交 → 显示上传区
- 已提交(待批改) → 显示"已提交，等待批改"状态
- 已批改 → 显示分数、反馈、下载批改件

**教师视角：**
- 试卷卡片下方展开提交概览表（非弹窗）
- 表格列：学生 | 提交时间 | 状态 | 分数 | 操作
- 点击[批改]在表格行内展开批改表单（分数 + 反馈 + 上传批改PDF）
- 保存批改后触发通知

**发布试卷（教师）：**
- 内联表单（替代 PublishExamDialog 弹窗）：标题 + 描述 + PDF 上传 + 发布按钮
- 通过 isAdmin 控制可见性

### 1.4 UI 设计原则

- 卡片层次：试卷卡片 > 提交表格 > 批改内联区，视觉逐层缩进
- 状态用 Badge 区分颜色：未提交(gray) / 待批改(amber) / 已批改(green)
- 操作按钮统一 `size="sm" variant="outline"`，破坏性操作用 `destructive`
- 空状态使用 `<EmptyState>` 组件
- 加载中使用 centered spinner

---

## 2. 全局移动端响应式重构

### 2.1 底部导航栏

保留当前底部 Tab 方案，5 个入口：

| 图标 | 标签 | 路由 |
|------|------|------|
| BookOpen | 课程 | /courses |
| Trophy | 刷题 | /tests |
| GitMerge | 知识图谱 | /knowledge-map |
| Clock | 自习室 | /study |
| UserIcon | 我的 | /profile |

优化项：
- Active 态：primary 色底部指示条（2px border-top）+ 图标/文字 primary 色
- 沉浸式页面（/tests/session, /course/, /study）自动隐藏底栏
- 非底栏路由不亮任何入口

### 2.2 断点策略

| 断点 | 布局 |
|------|------|
| < 768px (mobile) | 侧边栏隐藏，底栏显示，内容 `px-4`，全宽 |
| 768-1023px (tablet) | 侧边栏收起(仅图标)，内容 `px-6` |
| >= 1024px (desktop) | 侧边栏展开，内容 `max-w-*` 居中 |

### 2.3 页面移动端适配模式

对全部 21 个页面应用以下规则：

1. **卡片列表页**：`grid grid-cols-1` 单列，卡片 `w-full`
2. **操作行**：`flex-row` → `flex-col`，按钮 `w-full` 撑满
3. **多列网格**：已有的 `md:grid-cols-2 lg:grid-cols-3` 保留，移动端自动单列
4. **弹窗**：移动端 `max-w-[calc(100vw-2rem)]`，`drawer` 底部弹出
5. **表格**：`overflow-x-auto` 横向滚动 + `min-w-[600px]` 确保内容不被挤压
6. **安全区**：`pb-[env(safe-area-inset-bottom)]` 底栏留白
7. **触控**：可点击元素最小 44x44px
8. **overscroll**：滚动容器加 `overscroll-contain`

### 2.4 页面优先级

| 优先级 | 页面 | 说明 |
|--------|------|------|
| P0 | PdfMockExam | 本次重构目标 |
| P0 | MainLayout | 底部导航 + 响应式骨架 |
| P1 | TestSessionPage, CourseDetails, KnowledgeMap | 核心页面 |
| P1 | InstitutionDashboard, InstitutionStudents | 机构管理核心 |
| P2 | ArticleDetail, StudyRoom, WrongQuestionReview | 次要页面 |
| P2 | QASystem, KnowledgeNodeDetail | 内容页面 |
| P3 | 其余 maintenance/ 面板页面 | 管理后台 |
| P3 | Landing, Login/Register | 已有响应式 |

### 2.5 MainLayout 响应式改动

- 侧边栏：`hidden md:flex` 保持不变
- 顶部 header：`hidden md:flex` 保持不变，移动端由页面自行处理返回导航
- 底部导航：`md:hidden` 仅在移动端显示
- 内容区：`md:pl-[var(--sidebar-width)]` → 移动端 `pl-0 pb-[var(--bottom-nav-h)]`

---

## 3. 不涉及的范围

- 后端 API 变更（现有 6 个 teacher-exam 端点保持不变）
- 用户权限模型变更（isAdmin 判断保留）
- Landing/Intro 页面（明确排除）
- 国际化翻译文件（仅追加新 key，不修改已有）
- 通知系统后端（前端仅触发已有 API）

---

## 4. 成功标准

1. `npm run build` 通过，0 TypeScript 错误
2. 密卷页面教师工作流完整：发布 → 提交 → 批改 → 通知，无不必要弹窗
3. 移动端底部导航 5 个入口可用，沉浸页面自动隐藏
4. 所有页面 `<768px` 宽度下无水平溢出
5. 触控目标 >= 44x44px，安全区正确处理
