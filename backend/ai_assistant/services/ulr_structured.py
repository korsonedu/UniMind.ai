"""Compatibility alias — canonical module lives at ai_assistant.services.runtime.ulr_structured."""
import sys
from .runtime import ulr_structured as _impl

sys.modules[__name__] = _impl
