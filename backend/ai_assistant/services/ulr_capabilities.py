"""Compatibility alias — canonical module lives at ai_assistant.services.runtime.ulr_capabilities."""
import sys
from .runtime import ulr_capabilities as _impl

sys.modules[__name__] = _impl
