import time
import logging
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

class CircuitBreakerError(Exception):
    """当熔断器处于打开状态时抛出的异常"""
    pass

class AICircuitBreaker:
    """AI 熔断器，使用 Django Cache 记录失败状态"""

    @classmethod
    def _get_thresholds(cls):
        return (
            getattr(settings, 'AI_CB_FAILURE_THRESHOLD', 5),
            getattr(settings, 'AI_CB_RECOVERY_TIMEOUT', 300),
            getattr(settings, 'AI_CB_WINDOW_TIMEOUT', 60),
        )
    
    @classmethod
    def _get_keys(cls, service_name="default"):
        return f"ai_cb_fails_{service_name}", f"ai_cb_state_{service_name}"
        
    @classmethod
    def record_failure(cls, service_name="default"):
        fail_key, state_key = cls._get_keys(service_name)
        threshold, recovery_timeout, window_timeout = cls._get_thresholds()

        try:
            fails = cache.get(fail_key, 0)
            fails += 1
            cache.set(fail_key, fails, timeout=window_timeout)

            if fails >= threshold:
                if cache.get(state_key) != "open":
                    logger.critical(f"[CircuitBreaker] {service_name} 触发熔断！{window_timeout}s 内失败 {fails} 次。拦截 {recovery_timeout}s。")
                cache.set(state_key, "open", timeout=recovery_timeout)
        except Exception as e:
            logger.error(f"CircuitBreaker 记录失败状态出错: {e}")

    @classmethod
    def record_success(cls, service_name="default"):
        fail_key, state_key = cls._get_keys(service_name)
        try:
            if cache.get(state_key) == "open":
                logger.info(f"[CircuitBreaker] {service_name} 恢复服务，熔断器闭合。")
            cache.delete(fail_key)
            cache.delete(state_key)
        except Exception:
            pass

    @classmethod
    def is_open(cls, service_name="default"):
        _, state_key = cls._get_keys(service_name)
        try:
            return cache.get(state_key) == "open"
        except Exception:
            return False

    @classmethod
    def check(cls, service_name="default"):
        if cls.is_open(service_name):
            raise CircuitBreakerError(f"Service {service_name} is currently circuit broken.")
