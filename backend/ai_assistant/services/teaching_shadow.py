"""Compatibility alias — canonical module lives at ai_assistant.services.state.rsi.teaching_shadow."""
import sys
from .state.rsi import teaching_shadow as _impl

sys.modules[__name__] = _impl
