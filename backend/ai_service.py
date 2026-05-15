"""
Shim: re-exports AIService from ai_engine.ai_service for backward compatibility.

All consumers should eventually import directly from ai_engine.ai_service:
    from ai_engine.ai_service import AIService
"""

from ai_engine.ai_service import AIService, _SafeDict  # noqa: F401
