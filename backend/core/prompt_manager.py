"""
统一 Prompt 管理器 — 从文件系统读取 prompt 模板。

目录结构: backend/prompts/
  quizzes/      — 题库生成相关
  ai_assistant/ — AI 助教对话
  pipeline/     — 出题管线各 Agent
  grading/      — 评分相关

用法:
    from core.prompt_manager import PromptManager
    content = PromptManager.get_prompt("pipeline", "author_generate.txt")
    config = PromptManager.get_prompt_config("quizzes", "grading_prompt.txt")
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional
from django.conf import settings


class PromptConfig:
    """Prompt 配置对象，包含内容、可选的温度参数和模型名。"""
    def __init__(self, content: str, temperature: float = None, model: str = None):
        self.content = content
        self.temperature = temperature
        self.model = model


class PromptManager:
    """统一 Prompt 管理器：从文件读取，PromptTemplateVersion DB 模型用于版本历史。"""

    PROMPTS_DIR = Path(getattr(settings, 'BASE_DIR', Path(__file__).resolve().parent.parent)) / "prompts"

    # ── 兼容旧调用（无 namespace 的 name 调用）────────────────────────
    _LEGACY_NAME_MAP = {
        "AI_QUESTION_AUTHOR": ("pipeline", "author_generate.txt"),
        "AI_QUESTION_REVIEWER": ("pipeline", "reviewer_adversarial.txt"),
        "AI_QUESTION_REVIEWER_BATCH": ("pipeline", "reviewer_single.txt"),
        "AI_QUESTION_CLASSIFIER": ("pipeline", "classifier.txt"),
        "AI_QUESTION_GENERATOR": ("pipeline", "author_generate.txt"),
        "AI_REVIEWER": ("pipeline", "reviewer_adversarial.txt"),
        "AI_TAXONOMIST": ("pipeline", "classifier.txt"),
        "AI_RESUME_TUNER": ("interviews", "resume_tuner.txt"),
        "AI_INTERVIEW_ANALYZER": ("interviews", "interview_analyzer.txt"),
        "AI_INTERVIEW_TURN_FEEDBACK": ("interviews", "turn_feedback.txt"),
    }

    # ── 核心方法 ────────────────────────────────────────────────

    @classmethod
    def _resolve_path(cls, namespace: str, name: str) -> Optional[Path]:
        """将 namespace + name 解析为文件路径。"""
        clean_name = Path(name).name
        path = cls.PROMPTS_DIR / namespace / clean_name
        if path.exists():
            return path
        return None

    @classmethod
    def get_prompt(cls, arg1: str, arg2: str = "", arg3: str = "") -> str:
        """
        从文件系统读取 prompt 内容。兼容两种调用方式：

        - 新: get_prompt(namespace, name, default)
        - 旧: get_prompt(legacy_name, default)  ← 自动通过 _LEGACY_NAME_MAP 转换
        """
        if arg1 in cls._LEGACY_NAME_MAP:
            ns, nm = cls._LEGACY_NAME_MAP[arg1]
            default = arg2 or arg3
            path = cls._resolve_path(ns, nm)
            if path:
                return _read_cached(path)
            return default

        namespace, name, default = arg1, arg2, arg3
        path = cls._resolve_path(namespace, name)
        if path:
            return _read_cached(path)
        return default

    @classmethod
    def get_prompt_config(
        cls, arg1: str, arg2: str = "", arg3: str = ""
    ) -> PromptConfig:
        """
        读取 prompt 并返回 PromptConfig。兼容两种调用：

        - 新: get_prompt_config(namespace, name, default)
        - 旧: get_prompt_config(legacy_name, default)

        如果 prompt 文件包含 /* PROMPT_META ... */ 头部注释，
        会解析其中的 temperature 等元数据。
        """
        if arg1 in cls._LEGACY_NAME_MAP:
            content = cls.get_prompt(arg1, arg2 or arg3)
        else:
            content = cls.get_prompt(arg1, arg2, arg3)

        temperature = None
        model = None
        if content.startswith('/* PROMPT_META'):
            end = content.find('*/')
            if end > 0:
                meta_block = content[len('/* PROMPT_META'):end]
                content = content[end + 2:].strip()
                try:
                    meta = json.loads(meta_block)
                    temperature = meta.get('temperature')
                    model = meta.get('model')
                except Exception:
                    pass
        return PromptConfig(content=content, temperature=temperature, model=model)

    @classmethod
    def list_prompts(cls, namespace: str) -> list:
        """列出某个 namespace 下的所有 prompt 文件名。"""
        dir_path = cls.PROMPTS_DIR / namespace
        if not dir_path.exists():
            return []
        return sorted([
            f.name for f in dir_path.iterdir()
            if f.is_file() and f.suffix in {'.txt', '.json', '.html'}
        ])

    @classmethod
    def list_namespaces(cls) -> list:
        """列出所有可用的 namespace。"""
        if not cls.PROMPTS_DIR.exists():
            return []
        return sorted([
            d.name for d in cls.PROMPTS_DIR.iterdir()
            if d.is_dir() and d.name != '__pycache__'
        ])


@lru_cache(maxsize=32)
def _read_cached(path: Path) -> str:
    """带缓存的文件读取，避免 AI 管线中重复读盘。"""
    return path.read_text(encoding='utf-8').strip()
