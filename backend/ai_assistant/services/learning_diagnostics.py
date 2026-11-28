"""Compatibility alias — canonical module lives at ai_assistant.services.facts.learning_diagnostics."""
import sys
from .facts import learning_diagnostics as _impl

sys.modules[__name__] = _impl
