"""Compatibility alias — canonical module lives at ai_assistant.services.facts.learning_library."""
import sys
from .facts import learning_library as _impl

sys.modules[__name__] = _impl
