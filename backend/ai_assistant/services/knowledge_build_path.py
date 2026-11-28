"""Compatibility alias — canonical module lives at ai_assistant.services.state.knowledge.knowledge_build_path."""
import sys
from .state.knowledge import knowledge_build_path as _impl

sys.modules[__name__] = _impl
