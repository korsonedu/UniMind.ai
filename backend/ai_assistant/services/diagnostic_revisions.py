"""Compatibility alias — canonical module lives at ai_assistant.services.facts.diagnostic_revisions."""
import sys
from .facts import diagnostic_revisions as _impl

sys.modules[__name__] = _impl
