"""Compatibility alias — canonical module lives at ai_assistant.services.decision.learning_guidance."""
import sys
from .decision import learning_guidance as _impl

sys.modules[__name__] = _impl
