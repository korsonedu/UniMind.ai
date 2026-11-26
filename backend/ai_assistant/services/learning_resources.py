"""Compatibility alias — canonical module lives at ai_assistant.services.runtime.learning_resources."""
import sys
from .runtime import learning_resources as _impl

sys.modules[__name__] = _impl
