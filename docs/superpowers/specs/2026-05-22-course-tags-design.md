# Course Tag System Design

**日期:** 2026-05-22
**状态:** pending review

## 目标

为课程添加机构级自由标签系统。上传时即时创建 + 后台管理，课程中心支持标签筛选。

## 数据模型

### CourseTag

| 字段 | 类型 | 说明 |
|------|------|------|
| id | PK | |
| institution | FK → Institution | 机构隔离 |
| name | CharField(50) | 标签名 |
| slug | SlugField(60) | URL 友好，自动从 name 生成 |
| created_at | DateTime | |

- `unique_together: (institution, slug)` — 同机构下标签 slug 唯一，不同机构可有同名标签

### CourseTagRelation

| 字段 | 类型 | 说明 |
|------|------|------|
| id | PK | |
| course | FK → Course | |
| tag | FK → CourseTag | |
| created_at | DateTime | |

- `unique_together: (course, tag)`
- 通过表，不直接 M2M，方便未来扩展（如排序、加权重）

### 索引策略

- CourseTag: unique index on (institution, slug)
- CourseTagRelation: unique index on (course, tag)
- CourseTagRelation: index on (tag_id) — 方便查"某标签下所有课程"

## API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/courses/tags/` | GET | 机构标签列表，含 `course_count` |
| `/api/courses/tags/` | POST | 创建标签（管理员） |
| `/api/courses/tags/{id}/` | PUT/DELETE | 编辑/删除标签（管理员） |
| `/api/courses/tags/batch-assign/` | POST | 批量标签操作。接收 `{course_id, tags: ["基础","必看"]}`，已存在 slug 匹配→直接关联，不存在→自动创建 |
| `/api/courses/` | GET | 新增 `?tag=slug` 筛选（多选 `?tag=a&tag=b` 取交集） |

## 前端

### 课程中心 (CourseCenter.tsx)

- 顶部加标签 chip 横向滚动条，点击筛选，支持多选（交集）
- 课程卡片底部显示标签 badges
- 无标签课程在"全部"视图下正常显示，tag 筛选后隐藏

### 课程上传表单 (Maintenance.tsx)

- 现有 `TagInput` 组件增强：输入时从 `/api/courses/tags/` 拉取机构已有标签做 autocomplete
- 匹配到的 → 选中加 badge；匹配不到的 → 回车自动创建新标签
- 提交时通过 `batch-assign` 接口关联

### 标签管理 (Maintenance → 新 tab "标签")

- 标签列表（名称、课程数、操作按钮）
- 新增/编辑弹窗（输入 name 即可，slug 自动生成）
- 删除需确认（删除标签 → 级联删除所有关联关系，不删课程）

## Serializer 变更

- `CourseSerializer` 新增 `tags` 字段（嵌套 `CourseTagSerializer`，source 走 `tag_relations`）
- 新增 `CourseTagSerializer`

## 边界情况

- 删除标签：只删关联关系，课程本体不受影响
- 同slug标签重复创建：batch-assign 接口做 get_or_create，按 slug 去重
- 空标签名：前后端均校验，name 不能为空白
- 跨机构：机构A的标签不会出现在机构B的标签列表或自动补全中

## 不做的事

- 不碰现有 Article tags（文章标签继续保持 JSONField 字符串数组，两个系统场景不同）
- 不给 Album 加标签（一期只做 Course 级别）
- 不做标签排序/置顶（保持简单，后续按需加）
- 不做标签颜色/图标（YAGNI）
