"""Compatibility alias — canonical module lives at ai_assistant.services.runtime.ulr_runtime."""
import sys
from .runtime import ulr_runtime as _impl

sys.modules[__name__] = _impl
