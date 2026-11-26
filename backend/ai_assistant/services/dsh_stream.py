"""Compatibility alias — canonical module lives at ai_assistant.services.views.stream."""
import sys
from .views import stream as _impl

sys.modules[__name__] = _impl
