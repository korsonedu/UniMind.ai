"""Compatibility alias — canonical module lives at ai_assistant.services.runtime.session_tools."""
import sys
from .runtime import session_tools as _impl

sys.modules[__name__] = _impl
