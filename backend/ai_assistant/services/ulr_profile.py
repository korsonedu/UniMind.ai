"""Compatibility alias — canonical module lives at ai_assistant.services.state.sdtm.ulr_profile."""
import sys
from .state.sdtm import ulr_profile as _impl

sys.modules[__name__] = _impl
