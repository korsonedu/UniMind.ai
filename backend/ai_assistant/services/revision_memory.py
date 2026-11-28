"""Compatibility alias — canonical module lives at ai_assistant.services.state.sdtm.revision_memory."""
import sys
from .state.sdtm import revision_memory as _impl

sys.modules[__name__] = _impl
