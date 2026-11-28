"""Compatibility alias — canonical module lives at ai_assistant.services.views.cards."""
import sys
from .views import cards as _impl

sys.modules[__name__] = _impl
