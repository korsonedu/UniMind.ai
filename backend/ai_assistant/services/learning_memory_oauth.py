"""Compatibility alias — canonical module lives at ai_assistant.services.runtime.learning_memory_oauth."""
import sys
from .runtime import learning_memory_oauth as _impl

sys.modules[__name__] = _impl
