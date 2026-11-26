"""Compatibility alias — canonical module lives at ai_assistant.services.runtime.bridge."""
import sys
from .runtime import bridge as _impl

sys.modules[__name__] = _impl
