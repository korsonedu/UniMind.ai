import logging
from core.prompt_manager import PromptManager
from ai_service import AIService
from ai_engine.service import AIEngine
import json

logger = logging.getLogger(__name__)


def _build_system_message(session_type: str, style: str) -> dict:
    """构建面试官 system prompt，session_type 决定面试场景，style 决定追问风格。"""
    if session_type == 'english':
        default_prompt = (
            "You are an expert examiner for a graduate-level program. "
            "Your goal is to simulate a realistic, professional, and slightly challenging English interview. "
            "Rules:\n"
            "1. Always respond in English.\n"
            "2. Ask ONE clear, specific question at a time related to the candidate's field of study.\n"
            "3. If the candidate makes a significant grammar mistake, briefly correct it before asking the next question.\n"
            "4. Keep your response under 50 words to maintain a conversational pace."
        )
        config = PromptManager.get_prompt_config("AI_SPOKEN_ENGLISH_EXAMINER", default_prompt)
    elif session_type == 'resume':
        style_desc = "高压追问、严厉刁钻、频繁质疑经历真实性" if style == 'pressure' else "循循善诱、和蔼可亲、重点挖掘潜力"
        default_prompt = (
            f"你是一名高校复试考官。你正在对考生进行【简历深挖】面试。\n"
            f"你的风格设定为：{style_desc}。\n\n"
            "【行为准则】\n"
            "1. 严格基于考生过去的发言进行追问，寻找逻辑漏洞或含糊其辞的地方。\n"
            "2. 每次只问【一个】最核心的问题，不要连发多问。\n"
            "3. 口语化表达，像真实的面试官一样对话，不要超过80个字。\n"
            "4. 如果考生的回答很空泛，直接指出并要求举例说明。"
        )
        config = PromptManager.get_prompt_config("AI_RESUME_INTERVIEWER", default_prompt)
    else:
        style_desc = "高压追问、严厉刁钻、专挑概念漏洞和逻辑矛盾" if style == 'pressure' else "循循善诱、和蔼可亲、以引导启发为主"
        default_prompt = (
            f"你是一名高校复试考官。你正在对考生进行【专业课】面试。\n"
            f"你的风格设定为：{style_desc}。\n\n"
            "【行为准则】\n"
            "1. 针对考生刚刚的回答，深入追问底层的专业核心原理。\n"
            "2. 每次只问【一个】核心专业问题，不要一次性抛出多个。\n"
            "3. 口语化表达，无AI痕迹（不要用“首先、其次”），回复字数控制在80字以内。\n"
            "4. 如果考生概念错误，毫不留情地纠正（压力型）或委婉指出（和蔼型）。\n"
            "5. 可以结合当前真实的时事热点测试应用能力。"
        )
        config = PromptManager.get_prompt_config("AI_MOCK_INTERVIEWER_PRO", default_prompt)
    return {"role": "system", "content": config.content}, config


class InterviewAIService:

    @classmethod
    def tune_resume(cls, resume_text: str):
        """AI 简历调优：诊断、润色并预测陷阱题"""
        default_prompt = (
            "你是一个资深的HR及面试官。请评估考生的简历，从排版、STAR法则、专业素养给出评分和润色后的内容。\n"
            "返回严格的 JSON 格式: \n"
            "{\n"
            '  "score": 85,\n'
            '  "diagnostics": "指出简历的致命问题...",\n'
            '  "optimized_content": {"experience": "润色后的经历描述..."},\n'
            '  "predicted_questions": ["深挖问题1", "深挖问题2"]\n'
            "}"
        )
        prompt_config = PromptManager.get_prompt_config("AI_RESUME_TUNER", default_prompt)

        response = AIService.simple_chat_text(
            system_prompt=prompt_config.content,
            user_prompt=f"原版简历内容：\n{resume_text}",
            operation="interviews.tune_resume",
            temperature=prompt_config.temperature,
        )

        return AIService.extract_json(response)

    @classmethod
    def generate_opening_question(cls, session_type: str, style: str) -> str:
        """为新会话生成面试官的开场白 / 第一个问题。"""
        sys_msg, config = _build_system_message(session_type, style)
        opener_prompt = (
            "面试刚刚开始，你是面试官，请做一个简短的开场白（包含自我介绍和第一个问题）。"
            if session_type != 'english'
            else "The interview is starting. As the examiner, give a brief opening (introduce yourself and ask the first question)."
        )
        messages = [sys_msg, {"role": "user", "content": opener_prompt}]
        response = AIService.call_ai(
            messages,
            operation="interviews.mock_reply",
            temperature=config.temperature if config else 0.4,
        )
        return (AIService.extract_content(response) or "").strip()

    @classmethod
    def generate_interview_reply(cls, session_type: str, style: str, chat_history: list):
        """基于上下文，生成面试官的下一句追问"""
        sys_msg, config = _build_system_message(session_type, style)
        messages = [sys_msg]
        messages.extend(chat_history)

        response = AIService.call_ai(
            messages,
            operation="interviews.mock_reply",
            temperature=config.temperature if config else 0.4,
        )
        return AIService.extract_content(response)

    @classmethod
    def generate_interview_reply_stream(cls, session_type: str, style: str, chat_history: list):
        """流式生成面试官追问，yield 每个 token。"""
        sys_msg, config = _build_system_message(session_type, style)
        messages = [sys_msg]
        messages.extend(chat_history)

        yield from AIEngine.call_ai_stream(
            messages,
            operation="interviews.mock_reply",
            temperature=config.temperature if config else 0.4,
        )

    @classmethod
    def generate_post_interview_radar(cls, chat_history: list):
        """面试结束后的五维雷达图和深度复盘"""
        default_prompt = (
            "你是一个资深的高校复试分析专家。请根据这轮面试的完整对话记录，对考生进行客观、深度的五维复盘打分。\n"
            "请严格返回如下 JSON 格式，不要包含任何其他说明文字：\n"
            "{\n"
            '  "radar_scores": {\n'
            '    "theory": 80,\n'
            '    "logic": 70,\n'
            '    "stress": 85,\n'
            '    "fluency": 75,\n'
            '    "english": 60\n'
            "  },\n"
            '  "overall_feedback": "对考生的整体评价，指出最大的亮点和致命弱点，字数150字左右。"\n'
            "}"
        )
        prompt_config = PromptManager.get_prompt_config("AI_INTERVIEW_ANALYZER", default_prompt)

        history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in chat_history])

        response = AIService.simple_chat_text(
            system_prompt=prompt_config.content,
            user_prompt=f"面试记录：\n{history_text}",
            operation="interviews.radar_analysis",
            temperature=prompt_config.temperature,
        )

        return AIService.extract_json(response)

    @classmethod
    def annotate_candidate_turn(cls, session_type: str, answer_text: str):
        default_prompt = (
            "你是高校复试教研老师。针对考生刚刚回答的单句话，给出1到2句简短、毒辣的可执行改进建议。\n"
            "【规则】\n"
            "1. 禁止空泛的表扬。\n"
            "2. 直接指出概念错误、逻辑跳跃、或者口语化严重的问题。\n"
            "3. 如果回答完美，只需回复“逻辑严密，无明显漏洞”。\n"
            "4. 纯文本输出，不要使用任何Markdown格式。"
        )
        prompt_config = PromptManager.get_prompt_config("AI_INTERVIEW_TURN_FEEDBACK", default_prompt)
        response = AIService.simple_chat_text(
            system_prompt=prompt_config.content,
            user_prompt=f"会话类型：{session_type}\n考生回答：{answer_text}",
            operation="interviews.turn_feedback",
            temperature=prompt_config.temperature if prompt_config.temperature is not None else 0.2,
        )
        return str(response or "").strip()
