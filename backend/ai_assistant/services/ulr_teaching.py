"""Compatibility alias — canonical module lives at ai_assistant.services.decision.ulr_teaching."""
import sys
from .decision import ulr_teaching as _impl

sys.modules[__name__] = _impl
