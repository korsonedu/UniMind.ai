# AI 复试模拟器与语音交互系统 (AI Mock Interview Simulator)

## 1. 背景与动机
在 431 金融考研中，初试（笔试）通过后，复试（面试）往往是决定最终录取的关键环节。传统的题库系统无法解决学生“开不了口”、“逻辑不连贯”的痛点。
为此，我们在系统中新增一个独立的**“复试 (Mock Interview)”**模块（对应侧边栏的新入口）。通过整合语音识别 (STT)、大语言模型 (LLM) 和 语音合成 (TTS)，打造一个沉浸式的、具有压迫感的“虚拟导师面试”场景。

## 2. 核心功能设计

### 2.1 角色扮演与场景预设 (Roleplay Scenarios)
学生在进入复试房间前，可以进行参数配置：
- **导师风格**：
  - 风格 A：和蔼可亲型（侧重引导，适合初期练胆）。
  - 风格 B：压力测试型（语速快，频繁打断，专挑漏洞，适合冲刺期）。
- **面试方向**：宏观经济、公司理财、时事热点（如当前美联储降息对 A 股的影响）或个人简历深挖（上传简历让 AI 针对性提问）。

### 2.2 实时语音交互全链路 (Real-time Voice Pipeline)
面试过程需要极低的延迟和极高的真实感：

1. **听 (STT - Speech to Text)**：
   - 前端通过浏览器 WebRTC / MediaRecorder API 捕获麦克风音频。
   - 调用流式语音识别服务（如 Whisper API / 阿里录音转写）将语音转为文字。
2. **想 (LLM - Reasoning)**：
   - 将转录的文字发送给后端的 Prompt Engine（挂载 `MOCK_INTERVIEWER` 模板）。
   - AI 根据上下文历史和设定的“导师人设”，生成下一句追问或评价。
3. **说 (TTS - Text to Speech)**：
   - 后端流式调用 TTS API（如 OpenAI TTS, Azure 语音, 或 Edge TTS）。
   - 将合成的音频流式推回前端播放。并配合一个简单的声波 UI 动画，增强沉浸感。

### 2.3 面试后深度复盘 (Post-Interview Analytics)
一场 15 分钟的面试结束后，系统必须给出高价值的回报：
- **逐句点评 (Line-by-line Feedback)**：展示完整的对话文字记录（Transcript），并在学生的发言下方用红字标出“逻辑不严密”、“专业术语使用错误”的地方，给出修正建议。
- **雷达图评估 (Skill Radar)**：从 5 个维度打分：
  - 理论扎实度 (Theoretical Knowledge)
  - 逻辑条理性 (Logical Coherence)
  - 应变能力 (Adaptability)
  - 表达流畅度 (Fluency)
  - 情绪稳定性 (Confidence - 可通过语音语速/停顿频率简单推算)

## 3. 前端 UI 与交互架构

- **Sidebar 入口**：在前端导航栏（如 `frontend/src/App.tsx` 的 Sidebar）新增 `[复试模拟]` 图标。
- **页面布局**：
  - **大厅页 (Lobby)**：选择导师风格和考试方向，点击“进入考场”。
  - **面试房 (Interview Room)**：极简暗色调 UI。中央是一个虚拟的声波波动动画（代表导师在听或在说），下方是一个按住说话（或语音唤醒）的麦克风按钮。
  - **报告页 (Report)**：面试结束后的复盘大屏，展示雷达图和逐句建议。

## 4. 后端落地指南 (Backend Architecture)

为支持流式交互，后端（可能需要 `school_system/asgi.py` 支持的 WebSocket 或 SSE）：
- **模块归属**：可以在现有的 `study_room` app 中扩展，或新建一个 `interviews` app。
- **通信协议**：强烈建议使用 **WebSocket (Django Channels)** 进行双向通信。
  - 前端通过 WS 发送音频 Chunk。
  - 后端拼接后请求 STT -> LLM -> TTS，再将音频 Chunk 通过 WS 推回前端。
- **数据库**：
  - `InterviewSession` (记录时间、风格、总分)
  - `InterviewTurn` (记录每一轮的 QA 文本、音频地址、单句得分)，方便生成复盘报告。
