"""Compatibility alias — canonical module lives at ai_assistant.services.facts.learning_practice_memory."""
import sys
from .facts import learning_practice_memory as _impl

sys.modules[__name__] = _impl
