"""Compatibility alias — canonical module lives at ai_assistant.services.runtime.chat_dispatch."""
import sys
from .runtime import chat_dispatch as _impl

sys.modules[__name__] = _impl
