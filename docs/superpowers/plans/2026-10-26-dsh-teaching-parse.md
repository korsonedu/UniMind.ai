# DSH 教研文本解析实施计划

> 使用 superpowers:executing-plans 连续执行，一次独立复核，只做必要冒烟。

**Goal:** Directus 教研后台把粘贴的题目资料解析为候选题，人工编辑、确认后才入库。

**Architecture:** 复用 teaching.generate 异步任务及 pipeline.review。新增 parse 模式，要求选定一个现有考点；模型无考点选择权、发布权。AIService 固定 operation quizzes.preview_parse 通过默认关闭的独立开关迁入已有服务端 DSH collector，单次 fast 请求，数组用对象包裹后解包。

**Tech Stack:** Django/Celery、现有 Directus Vue 模块、DSH 0.2.1rc2、TS collector。

**Spec:** 完整规划 v1.2 的 M1 提前教研录入辅助及人工审核边界。

## 约束和复核重点

- 不改实际 .env，不启用正式流量，不新增机构或教师权限；沿用签名管理员及当前内容范围校验。
- UNIMIND_DSH_TEACHING_ENABLED 默认 false。新解析入口未开启时明确拒绝，不意外使用旧模型。原有解析 API 的默认路径保持不变。
- 材料上限 10000 字且 40000 字节；只接受一个考点。仅解析文本，本批不增加 OCR/PDF 上传、联网或自动发布。
- 固定 fast/3200 tokens/一次请求，无重试或其他模型 fallback；复用临时 SDK home、槽位和超时清理。
- TS wire Schema 将可空 type 数组等价转换为 oneOf；Django 保留原始 Schema 校验。教研使用独立任务提示词，材料仅为不可信数据。
- 候选题为空/无效或模型失败应标记失败，不写 Question；确认操作仍幂等。人工录入入口继续可用。

## Task 1: 固定解析任务

- [x] 先写定向冒烟：开关隔离、固定路由/预算、数组解包及坏 Schema 拒绝。
- [x] 最小实现 adapter、任务提示词及原解析方法缺失的 classmethod；验证 RED→GREEN。

## Task 2: 管理员异步解析与审核

- [x] 先写定向冒烟：考点范围、资料界限、关闭拒绝、重复任务/投递、确认前不入库、确认幂等。
- [x] 在现有后台任务与 Vue 生成弹窗新增 parse 模式，沿用原审核流程。
- [x] 实际 SDK 协议模拟、管理后台类型检查/构建；一次独立复核，必要修复，文档及本地提交。

Ruling: 本批不迁移完整教研聊天和 quick/ARC/bulk 生成；它们有不同业务工具和质量门槛。解析只提供 M1 辅助录入最小闭环，不宣称真实模型题目解析质量已验收。

## 验收记录

- 定向测试 10 passed：路由/预算/坏 Schema、空值保留、考点范围、资料界限、关闭拒绝、重复投递、确认前不入库、失败文案、重试保留材料。
- admin-extension 类型检查与构建通过；实际 SDK 冒烟通过单次请求、3200 tokens、temperature 0.2、确认后一次入库。
- 独立复核发现并修复：运行期失败原因分类、缺失评分点被默认补全、轮询覆盖未保存编辑、parse 模式多余题型勾选、候选题缺考点名称、编码异常处理。
- 未验收：真实模型解析质量、生产后台、正式开关启用。
