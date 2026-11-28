"""Compatibility alias — canonical module lives at ai_assistant.services.runtime.fixed_tasks."""
import sys
from .runtime import fixed_tasks as _impl

sys.modules[__name__] = _impl
