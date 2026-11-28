"""Compatibility alias — canonical module lives at ai_assistant.services.state.knowledge.learning_continuity."""
import sys
from .state.knowledge import learning_continuity as _impl

sys.modules[__name__] = _impl
