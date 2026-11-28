"""Compatibility alias — canonical module lives at ai_assistant.services.facts.external_audio_asr."""
import sys
from .facts import external_audio_asr as _impl

sys.modules[__name__] = _impl
