"""Compatibility alias — canonical module lives at ai_assistant.services.views.planner_visuals."""
import sys
from .views import planner_visuals as _impl

sys.modules[__name__] = _impl
