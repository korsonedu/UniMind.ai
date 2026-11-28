"""Compatibility alias — canonical module lives at ai_assistant.services.state.bep.bayesian_evaluation."""
import sys
from .state.bep import bayesian_evaluation as _impl

sys.modules[__name__] = _impl
