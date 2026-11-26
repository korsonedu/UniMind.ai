"""Compatibility alias — canonical module lives at ai_assistant.services.state.prism.prism_feedback."""
import sys
from .state.prism import prism_feedback as _impl

sys.modules[__name__] = _impl
