"""Compatibility alias — canonical module lives at ai_assistant.services.facts.learning_task_evidence."""
import sys
from .facts import learning_task_evidence as _impl

sys.modules[__name__] = _impl
