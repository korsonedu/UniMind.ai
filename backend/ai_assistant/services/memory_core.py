"""Compatibility alias — canonical module lives at ai_assistant.services.state.sdtm.memory_core."""
import sys
from .state.sdtm import memory_core as _impl

sys.modules[__name__] = _impl
