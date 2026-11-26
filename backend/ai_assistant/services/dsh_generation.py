"""Compatibility alias — canonical module lives at ai_assistant.services.runtime.generation_gateway."""
import sys
from .runtime import generation_gateway as _impl

sys.modules[__name__] = _impl
