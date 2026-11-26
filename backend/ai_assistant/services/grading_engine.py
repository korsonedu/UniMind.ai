"""Compatibility alias — canonical module lives at ai_assistant.services.runtime.grading_engine."""
import sys
from .runtime import grading_engine as _impl

sys.modules[__name__] = _impl
