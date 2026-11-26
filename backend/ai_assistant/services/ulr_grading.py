"""Compatibility alias — canonical module lives at ai_assistant.services.runtime.ulr_grading."""
import sys
from .runtime import ulr_grading as _impl

sys.modules[__name__] = _impl
