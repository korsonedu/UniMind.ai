"""Compatibility alias — canonical module lives at ai_assistant.services.state.sdtm.fact_evidence."""
import sys
from .state.sdtm import fact_evidence as _impl

sys.modules[__name__] = _impl
