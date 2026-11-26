"""Compatibility alias — canonical module lives at ai_assistant.services.views.title_generator."""
import sys
from .views import title_generator as _impl

sys.modules[__name__] = _impl
