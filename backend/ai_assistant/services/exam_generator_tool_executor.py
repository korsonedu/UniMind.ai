"""Compatibility alias — canonical module lives at ai_assistant.services.runtime.exam_generator_tool_executor."""
import sys
from .runtime import exam_generator_tool_executor as _impl

sys.modules[__name__] = _impl
