"""Compatibility alias — canonical module lives at ai_assistant.services.decision.method_adoption."""
import sys
from .decision import method_adoption as _impl

sys.modules[__name__] = _impl
