import logging
from core.prompt_manager import PromptManager
from ai_service import AIService
from ai_engine.service import AIEngine
from ai_engine.tools import RESUME_TUNE_SCHEMA, INTERVIEW_RADAR_SCHEMA
from quizzes.models import KnowledgePoint
import json

logger = logging.getLogger(__name__)

# Interview temperature — conversational, creative but not wild
INTERVIEW_TEMPERATURE = 0.4


def _get_knowledge_context(institution) -> str:
    """获取机构知识树顶级模块名称，用于专业课面试 prompt 上下文。"""
    if institution is None:
        return ""
    modules = KnowledgePoint.objects.filter(
        institution=institution, parent__isnull=True
    ).order_by('order', 'id').values_list('name', flat=True)[:10]
    if not modules:
        return ""
    return f"该机构主要专业领域为：{'、'.join(modules)}。请围绕这些主题进行专业课追问。"


def _build_prompt(session_type: str, style: str, institution=None) -> str:
    """构建面试官 system prompt。不依赖模板文件——prompt 包含动态 style，不适合静态模板。"""
    if session_type == 'english':
        return (
            "You are an expert examiner for a graduate-level program. "
            "Your goal is to simulate a realistic, professional, and slightly challenging English interview.\n\n"
            "Rules:\n"
            "1. Always respond in English.\n"
            "2. Ask ONE clear, specific question at a time related to the candidate's field of study.\n"
            "3. If the candidate makes a significant grammar mistake, briefly correct it before asking the next question.\n"
            "4. Keep your response under 50 words to maintain a conversational pace.\n"
            "5. Output ONLY spoken words. Never use parenthetical stage directions or action descriptions."
        )
    elif session_type == 'resume':
        style_desc = "高压追问、严厉刁钻、频繁质疑经历真实性" if style == 'pressure' else "循循善诱、和蔼可亲、重点挖掘潜力"
        return (
            f"你是一名高校复试考官。你正在对考生进行【简历深挖】面试。\n"
            f"你的风格设定为：{style_desc}。\n\n"
            "【行为准则】\n"
            "1. 严格基于考生过去的发言进行追问，寻找逻辑漏洞或含糊其辞的地方。\n"
            "2. 每次只问一个最核心的问题，不要连发多问。\n"
            "3. 口语化表达，像真实的面试官一样对话，不要超过80个字。\n"
            "4. 如果考生的回答很空泛，直接指出并要求举例说明。\n"
            "5. 只输出面试官说的话。严禁用括号描述动作、表情或语气，例如（笑）、（温和地）、（停顿）。"
        )
    else:
        style_desc = "高压追问、严厉刁钻、专挑概念漏洞和逻辑矛盾" if style == 'pressure' else "循循善诱、和蔼可亲、以引导启发为主"
        biz_hint = ""
        if institution and institution.business_type:
            biz_hint = f"机构讲授的主要课程为：{institution.business_type}。"
        knowledge_hint = _get_knowledge_context(institution)
        context_line = " ".join(filter(None, [biz_hint, knowledge_hint])).strip()
        prompt = (
            f"你是一名高校复试考官。你正在对考生进行【专业课】面试。\n"
            f"你的风格设定为：{style_desc}。\n"
        )
        if context_line:
            prompt += f"\n{context_line}\n"
        prompt += (
            "\n【行为准则】\n"
            "1. 针对考生刚刚的回答，深入追问底层的专业核心原理。\n"
            "2. 每次只问一个核心专业问题，不要一次性抛出多个。\n"
            "3. 口语化表达，无AI痕迹，回复字数控制在80字以内。\n"
            "4. 如果考生概念错误，请纠正指出。\n"
            "5. 可以结合当前真实的时事热点测试应用能力。\n"
            "6. 只输出面试官说的话。严禁用括号描述动作、表情或语气，例如（笑）、（温和地）、（停顿）。"
        )
        return prompt


class InterviewAIService:

    @classmethod
    def tune_resume(cls, resume_text: str):
        """AI 简历调优：诊断、润色并预测陷阱题"""
        default_prompt = (
            "你是一个资深的HR及面试官。请评估考生的简历，从排版、STAR法则、专业素养给出评分和润色后的内容。"
        )
        prompt_config = PromptManager.get_prompt_config("AI_RESUME_TUNER", default_prompt)

        result = AIService.structured_output(
            system_prompt=prompt_config.content,
            user_prompt=f"原版简历内容：\n{resume_text}",
            schema=RESUME_TUNE_SCHEMA,
            tool_name="submit_resume_tune",
            tool_description="提交简历评估和润色结果",
            operation="interviews.tune_resume",
            temperature=prompt_config.temperature,
        )

        if result is not None:
            return result

        # fallback to old extract_json path
        response = AIService.simple_chat_text(
            system_prompt=prompt_config.content,
            user_prompt=f"原版简历内容：\n{resume_text}",
            operation="interviews.tune_resume",
            temperature=prompt_config.temperature,
        )
        return AIService.extract_json(response)

    @classmethod
    def generate_opening_question(cls, session_type: str, style: str, institution=None) -> str:
        """为新会话生成面试官的开场白 / 第一个问题。"""
        system_prompt = _build_prompt(session_type, style, institution)
        opener_prompt = (
            "面试刚刚开始，你是面试官，请做一个简短的开场白（自我介绍并问第一个问题）。只输出说的话，不要加任何括号内的动作或表情描述。"
            if session_type != 'english'
            else "The interview is starting. As the examiner, give a brief opening (introduce yourself and ask the first question). Output only spoken words, no stage directions."
        )
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": opener_prompt}]
        response = AIService.call_ai(
            messages,
            operation="interviews.mock_reply",
            temperature=INTERVIEW_TEMPERATURE,
        )
        return (AIService.extract_content(response) or "").strip()

    @classmethod
    def generate_interview_reply(cls, session_type: str, style: str, chat_history: list, institution=None):
        """基于上下文，生成面试官的下一句追问"""
        system_prompt = _build_prompt(session_type, style, institution)
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(chat_history)

        response = AIService.call_ai(
            messages,
            operation="interviews.mock_reply",
            temperature=INTERVIEW_TEMPERATURE,
        )
        return AIService.extract_content(response)

    @classmethod
    def generate_interview_reply_stream(cls, session_type: str, style: str, chat_history: list, institution=None):
        """流式生成面试官追问，yield 每个 token。"""
        system_prompt = _build_prompt(session_type, style, institution)
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(chat_history)

        yield from AIEngine.call_ai_stream(
            messages,
            operation="interviews.mock_reply",
            temperature=INTERVIEW_TEMPERATURE,
        )

    @classmethod
    def generate_post_interview_radar(cls, chat_history: list):
        """面试结束后的五维雷达图和深度复盘"""
        default_prompt = (
            "你是一个资深的高校复试分析专家。请根据这轮面试的完整对话记录，对考生进行客观、深度的五维复盘打分。"
        )
        prompt_config = PromptManager.get_prompt_config("AI_INTERVIEW_ANALYZER", default_prompt)

        history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in chat_history])

        result = AIService.structured_output(
            system_prompt=prompt_config.content,
            user_prompt=f"面试记录：\n{history_text}",
            schema=INTERVIEW_RADAR_SCHEMA,
            tool_name="submit_interview_radar",
            tool_description="提交面试五维评估结果",
            operation="interviews.radar_analysis",
            temperature=prompt_config.temperature,
        )

        if result is not None:
            return result

        # fallback to old extract_json path
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
            "3. 如果回答完美，只需回复'逻辑严密，无明显漏洞'。\n"
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
