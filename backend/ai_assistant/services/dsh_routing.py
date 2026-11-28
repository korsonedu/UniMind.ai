"""Compatibility alias — canonical module lives at ai_assistant.services.runtime.tool_routing."""
import sys
from .runtime import tool_routing as _impl

sys.modules[__name__] = _impl
