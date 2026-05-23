# 综合复试模块设计蓝图 (Comprehensive Interview Module)

## 1. 宏观愿景 (Vision)
在 431 金融考研中，复试环节（包含简历面、专业面、英语口语面）是决定最终录取的“临门一脚”。为了提供全场景的备考支持，我们将原本单一的“复试模拟器”升级为**综合复试模块 (Comprehensive Interview Module)**。
本模块不仅是一个通过语音对话练习胆量的工具，更是一套包含“简历打磨 -> 英语特训 -> 沉浸式专业模拟面试 -> 面试后深度复盘”的完整备考工作流。

## 2. 核心子模块拆解 (Core Sub-modules)

### 2.1 智能简历调优 (AI Resume Tuning)
- **业务场景**：考生的初版简历往往缺乏亮点，未能突出金融学科相关的量化分析能力或实习价值。
- **功能设计**：
  - **文档解析 (OCR/Parsing)**：支持考生上传 PDF/Word 版简历。
  - **结构化诊断**：AI 从“排版规范”、“金融素养展现”、“STAR法则运用”等维度对简历进行打分。
  - **一键润色**：利用大模型将干瘪的描述（如“做过行研”）改写为高价值描述（如“运用 DCF 模型对某行业龙头进行估值预测”）。
  - **动态面试题库预测**：系统根据最终版的简历，预测导师可能在复试中深挖的 10 个“坑点”（如“你在这份实习中用的具体估值参数是多少？”），为后续模拟面试生成个性化 Prompt 题库。

### 2.2 英语口语特训 (Spoken English Practice)
- **业务场景**：金融专硕复试普遍包含英语自我介绍和专业英语问答，考生易出现“哑巴英语”。
- **功能设计**：
  - **自我介绍纠音**：考生朗读英语自我介绍，系统通过 STT 记录，并指出发音、语调、语法错误。
  - **专业名词特训**：系统随机下发 431 相关的英文词汇（如 Quantitative Easing, Capital Asset Pricing Model），考生需即兴给出一段不少于 3 句的英文解释。
  - **流畅度评分 (Fluency Scoring)**：基于语音停顿和重复词进行量化打分。

### 2.3 沉浸式智能复试 (Immersive Mock Interview)
- **业务场景**：最核心的对练场，提供全真模拟环境。
- **功能设计**：
  - **房间配置 (Room Setup)**：考生进入前，可选择“和蔼可亲”、“高压抗压”、“中英双语混合”等不同的导师人设。
  - **实时全双工语音 (Real-time Voice)**：采用 WebSocket 双向流式传输，前端捕获麦克风 -> 后端流式 STT -> 注入 LLM -> TTS 生成音频推回前端。确保对话延迟在 1.5 秒以内。
  - **多轮对抗追问**：导师不会机械地问下一个问题，而是根据考生的上一个回答进行深度追问（例如：“你提到无税 MM 理论，那如果引入破产成本呢？”）。

### 2.4 面试后深度复盘 (Post-Interview Analytics)
- **功能设计**：
  - **逐句点评 (Transcript Analysis)**：生成完整的文字对话稿，并在空白处/错误处加入批注（类似代码的 Code Review）。
  - **五维雷达图 (Skill Radar)**：从“专业知识”、“逻辑条理”、“应变抗压”、“表达流畅度”、“英语水平”五个维度进行评分。

## 3. 后端架构与技术选型预研

由于模块交互复杂，必须在 Django 中单开一个 Application 进行隔离。

- **应用规划**：新建 Django App：`interviews`
- **通信协议**：
  - 简历调优：传统的 HTTP RESTful API。
  - 英语口语 & 智能复试：**WebSocket (Django Channels + ASGI)**，保障音频 Chunk 级别的流式传输。
- **外部 AI 依赖**：
  - **LLM**：复用现有的 `AIEngine`。需要新增 Prompt 模板如 `RESUME_TUNER`, `MOCK_INTERVIEWER_PRO`, `ENGLISH_EXAMINER`。
  - **STT (Speech-to-Text)**：预研接入 Whisper API, 阿里听悟 或 腾讯流式语音识别。
  - **TTS (Text-to-Speech)**：预研接入 OpenAI TTS, Edge TTS 或 Azure 语音（Azure 的停顿和语气更像真人）。

## 4. 数据库模型设计草案 (Database Models Draft)

### `ResumeRecord` (简历记录表)
- `user`: 关联用户
- `original_file`: 原始文件路径
- `parsed_content`: OCR 解析的原始文本
- `optimized_content`: AI 润色后的结构化 JSON
- `predicted_questions`: 针对简历预测的陷阱题 JSON

### `InterviewSession` (面试会话表)
- `user`: 关联用户
- `session_type`: 选项 ('resume', 'english', 'professional', 'mixed')
- `interviewer_style`: 导师风格
- `status`: 状态 ('ongoing', 'completed', 'analyzing')
- `radar_scores`: 五维雷达图评分 JSON
- `overall_feedback`: 总结性评语
- `started_at`, `finished_at`

### `InterviewTurn` (面谈轮次明细表 - 每一回合的问答)
- `session`: 关联 `InterviewSession`
- `turn_number`: 第几轮对话
- `speaker`: 说话人 ('interviewer', 'candidate')
- `content_text`: 识别或生成的文本
- `audio_url`: 语音文件的对象存储地址
- `latency_ms`: 系统响应延迟（用于监控监控和优化）
- `feedback_for_turn`: 针对考生的这一句话，AI 给出的逐句点评（仅 speaker='candidate' 时有值）
