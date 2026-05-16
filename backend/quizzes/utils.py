"""quizzes 通用工具函数。"""
from typing import Any


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
