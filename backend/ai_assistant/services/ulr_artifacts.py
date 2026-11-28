"""Compatibility alias — canonical module lives at ai_assistant.services.views.ulr_artifacts."""
import sys
from .views import ulr_artifacts as _impl

sys.modules[__name__] = _impl
