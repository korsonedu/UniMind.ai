"""Compatibility alias — canonical module lives at ai_assistant.services.facts.teaching_sidecar."""
import sys
from .facts import teaching_sidecar as _impl

sys.modules[__name__] = _impl
