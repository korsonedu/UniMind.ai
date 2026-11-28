"""Compatibility alias — canonical module lives at ai_assistant.services.runtime.ulr_outbox."""
import sys
from .runtime import ulr_outbox as _impl

sys.modules[__name__] = _impl
