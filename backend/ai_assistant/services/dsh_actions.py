"""Compatibility alias — canonical module lives at ai_assistant.services.runtime.diagnostics_actions."""
import sys
from .runtime import diagnostics_actions as _impl

sys.modules[__name__] = _impl
