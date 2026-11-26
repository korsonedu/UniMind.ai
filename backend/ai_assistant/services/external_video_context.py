"""Compatibility alias — canonical module lives at ai_assistant.services.facts.external_video_context."""
import sys
from .facts import external_video_context as _impl

sys.modules[__name__] = _impl
