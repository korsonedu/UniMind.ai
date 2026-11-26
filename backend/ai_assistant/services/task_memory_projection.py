"""Compatibility alias — canonical module lives at ai_assistant.services.state.sdtm.task_memory_projection."""
import sys
from .state.sdtm import task_memory_projection as _impl

sys.modules[__name__] = _impl
