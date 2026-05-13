# 工作量与修改记录：Phase 5 综合复试模块 (Worklog)

> **文档目的**：本日志详细记录了综合复试模块 (Comprehensive Interview Module) 在规划、设计及后续落地过程中的全部工作量，供团队同事审阅架构思路及代码变更量。

---

## 阶段一：模块宏观架构与蓝图设计 (已完成)

### 1. 业务逻辑梳理与产品定义
- **需求洞察**：将原始的单一“模拟面试”扩充为“简历调优”、“英语口语”、“智能复试”、“复盘报告”四大核心子系统，覆盖初试到录取前的最后冲刺链路。
- **产出文档**：撰写了详尽的 `docs/COMPREHENSIVE_INTERVIEW_MODULE.md`，明确了功能边界和技术难点。

### 2. 数据库架构设计 (Schema Design)
在蓝图文档中，设计了 3 张核心新表，以支撑高频的语音交互与分析：
1. `ResumeRecord`：负责承载简历的输入、OCR文本、AI 润色输出以及针对简历生成的动态题库。
2. `InterviewSession`：会话级主表，定义面试方向（全英/专业/简历）、导师风格，并保存最终的五维雷达图数据。
3. `InterviewTurn`：轮次级明细表，精准记录双边对话的文本、音频存储地址、延迟毫秒数以及逐句的 AI Code Review 式批注。

### 3. 技术难点预研与路线制定
- **全双工流式架构**：明确摒弃传统短连接 HTTP，规划使用 **Django Channels (WebSocket)** 承担前端麦克风音频采集到后端 STT -> LLM -> TTS 的流式数据桥梁。
- **应用层解耦**：规划在 Django 中新建独立的 `interviews` 应用，不与先前的 `quizzes` (客观题/主观题系统) 混表，保障系统微服务化的清晰度。

---

## 阶段二：基建与模型落地 (待执行)

*（以下为接下来即将执行的代码级工作量，将在此实时更新）*

- [ ] 注册并创建新的 Django App: `interviews`
- [ ] 在 `interviews/models.py` 中编写 `ResumeRecord`, `InterviewSession`, `InterviewTurn` 模型。
- [ ] 注册相关的 Django Admin 管理后台，以便教研人员监控模型面试质量。
- [ ] 生成并执行数据库迁移 (`makemigrations interviews`, `migrate`)。

---

## 阶段三：核心 Prompt 与 AI 链路集成 (待执行)

- [ ] 在 `PromptTemplate` 系统中注入面试专属系统 Prompt：
  - `AI_RESUME_TUNER`: 简历“STAR法则”诊断与改写。
  - `AI_MOCK_INTERVIEWER`: 扮演刁钻的金融导师。
  - `AI_SPOKEN_ENGLISH_EXAMINER`: 针对英语口语的语法、流畅度评委。
- [ ] 编写底层通信逻辑：规划接入 WebSocket 或模拟 REST 的占位符服务。

---
*日志将在开发进程中持续滚动更新。*