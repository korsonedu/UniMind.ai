"""Compatibility alias — canonical module lives at ai_assistant.services.state.sdtm.ulr_memory."""
import sys
from .state.sdtm import ulr_memory as _impl

sys.modules[__name__] = _impl
