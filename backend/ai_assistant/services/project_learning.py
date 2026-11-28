"""Compatibility alias — canonical module lives at ai_assistant.services.decision.project_learning."""
import sys
from .decision import project_learning as _impl

sys.modules[__name__] = _impl
