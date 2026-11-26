"""Compatibility alias — canonical module lives at ai_assistant.services.facts.learning_recall."""
import sys
from .facts import learning_recall as _impl

sys.modules[__name__] = _impl
