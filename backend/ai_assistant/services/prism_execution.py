"""Compatibility alias — canonical module lives at ai_assistant.services.decision.prism_execution."""
import sys
from .decision import prism_execution as _impl

sys.modules[__name__] = _impl
