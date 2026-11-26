"""Compatibility alias — canonical module lives at ai_assistant.services.state.bep.bayesian_evidence."""
import sys
from .state.bep import bayesian_evidence as _impl

sys.modules[__name__] = _impl
