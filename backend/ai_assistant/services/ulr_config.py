"""Compatibility alias — canonical module lives at ai_assistant.services.runtime.ulr_config."""
import sys
from .runtime import ulr_config as _impl

sys.modules[__name__] = _impl
