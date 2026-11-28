"""Compatibility alias — canonical module lives at ai_assistant.services.runtime.project_learning_tools."""
import sys
from .runtime import project_learning_tools as _impl

sys.modules[__name__] = _impl
