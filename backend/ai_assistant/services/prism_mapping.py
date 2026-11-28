"""Compatibility alias — canonical module lives at ai_assistant.services.state.prism.prism_mapping."""
import sys
from .state.prism import prism_mapping as _impl

sys.modules[__name__] = _impl
