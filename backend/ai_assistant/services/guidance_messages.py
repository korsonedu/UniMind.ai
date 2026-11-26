"""Compatibility alias — canonical module lives at ai_assistant.services.views.guidance_messages."""
import sys
from .views import guidance_messages as _impl

sys.modules[__name__] = _impl
