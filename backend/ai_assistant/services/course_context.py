"""Compatibility alias — canonical module lives at ai_assistant.services.facts.course_context."""
import sys
from .facts import course_context as _impl

sys.modules[__name__] = _impl
