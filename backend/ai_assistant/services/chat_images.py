"""Compatibility alias — canonical module lives at ai_assistant.services.facts.chat_images."""
import sys
from .facts import chat_images as _impl

sys.modules[__name__] = _impl
