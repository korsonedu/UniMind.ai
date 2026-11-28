"""Compatibility alias — canonical module lives at ai_assistant.services.state.knowledge.learning_knowledge."""
import sys
from .state.knowledge import learning_knowledge as _impl

sys.modules[__name__] = _impl
