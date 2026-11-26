"""Compatibility alias — canonical module lives at ai_assistant.services.views.language."""
import sys
from .views import language as _impl

sys.modules[__name__] = _impl
