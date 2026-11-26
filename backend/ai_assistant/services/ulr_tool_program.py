"""Compatibility alias — canonical module lives at ai_assistant.services.runtime.ulr_tool_program."""
import sys
from .runtime import ulr_tool_program as _impl

sys.modules[__name__] = _impl
