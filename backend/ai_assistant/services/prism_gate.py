"""Compatibility alias — canonical module lives at ai_assistant.services.decision.prism_gate."""
import sys
from .decision import prism_gate as _impl

sys.modules[__name__] = _impl
