"""Compatibility alias — canonical module lives at ai_assistant.services.decision.public_methods."""
import sys
from .decision import public_methods as _impl

sys.modules[__name__] = _impl
