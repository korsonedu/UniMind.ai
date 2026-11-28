"""Compatibility alias — canonical module lives at ai_assistant.services.runtime.xiaoyu_turn."""
import sys
from .runtime import xiaoyu_turn as _impl

sys.modules[__name__] = _impl
