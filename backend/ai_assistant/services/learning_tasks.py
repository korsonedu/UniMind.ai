"""Compatibility alias — canonical module lives at ai_assistant.services.facts.learning_tasks."""
import sys
from .facts import learning_tasks as _impl

sys.modules[__name__] = _impl
