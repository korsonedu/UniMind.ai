"""Compatibility alias — canonical module lives at ai_assistant.services.runtime.scope."""
import sys
from .runtime import scope as _impl

sys.modules[__name__] = _impl
