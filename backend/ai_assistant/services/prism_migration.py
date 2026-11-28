"""Compatibility alias — canonical module lives at ai_assistant.services.state.prism.prism_migration."""
import sys
from .state.prism import prism_migration as _impl

sys.modules[__name__] = _impl
