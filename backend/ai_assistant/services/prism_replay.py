"""Compatibility alias — canonical module lives at ai_assistant.services.state.prism.prism_replay."""
import sys
from .state.prism import prism_replay as _impl

sys.modules[__name__] = _impl
