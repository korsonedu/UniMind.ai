import logging
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

STATE_CLOSED = "closed"
STATE_OPEN = "open"
STATE_HALF_OPEN = "half_open"


class CircuitBreakerError(Exception):
    """当熔断器处于打开状态时抛出的异常"""
    pass


class AICircuitBreaker:
    """
    双层熔断器：operation 层 + model_tier 层。

    - operation 层：单个任务类型的故障隔离
    - model_tier 层：同一模型等级（fast/pro）的故障隔离
    两层任一打开即拒绝请求。
    """

    @staticmethod
    def _get_thresholds(model_tier='fast'):
        base_threshold = getattr(settings, 'AI_CB_FAILURE_THRESHOLD', 5)
        base_recovery = getattr(settings, 'AI_CB_RECOVERY_TIMEOUT', 300)
        base_window = getattr(settings, 'AI_CB_WINDOW_TIMEOUT', 60)
        if model_tier == 'pro':
            return (
                getattr(settings, 'AI_CB_PRO_FAILURE_THRESHOLD', 3),
                getattr(settings, 'AI_CB_PRO_RECOVERY_TIMEOUT', base_recovery),
                base_window,
            )
        return (base_threshold, base_recovery, base_window)

    @staticmethod
    def _get_keys(service_name="default", model_tier=None):
        scope = model_tier if model_tier else service_name
        if model_tier:
            return (
                f"ai_cb_model_fails_{scope}",
                f"ai_cb_model_state_{scope}",
                f"ai_cb_model_half_{scope}",
            )
        return (
            f"ai_cb_fails_{scope}",
            f"ai_cb_state_{scope}",
            f"ai_cb_half_open_success_{scope}",
        )

    @classmethod
    def record_failure(cls, service_name="default", model_tier=None):
        cls._record_failure_for_keys(*cls._get_keys(service_name), service_name, model_tier=model_tier)
        if model_tier:
            cls._record_failure_for_keys(*cls._get_keys(service_name, model_tier),
                                         f"{model_tier} 模型等级", model_tier=model_tier)

    @classmethod
    def _record_failure_for_keys(cls, fail_key, state_key, half_key, label, model_tier=None):
        threshold, recovery_timeout, window_timeout = cls._get_thresholds(model_tier or 'fast')
        try:
            current_state = cache.get(state_key) or STATE_CLOSED
            fails = cache.get(fail_key, 0)
            fails += 1
            if current_state == STATE_HALF_OPEN:
                logger.critical(f"[CircuitBreaker] {label} 半开探测失败，重新熔断 {recovery_timeout}s。")
                cache.set(state_key, STATE_OPEN, timeout=recovery_timeout)
                cache.set(fail_key, threshold, timeout=recovery_timeout)
                return
            cache.set(fail_key, fails, timeout=window_timeout)
            if fails >= threshold:
                if current_state != STATE_OPEN:
                    logger.critical(f"[CircuitBreaker] {label} 触发熔断！{window_timeout}s 内失败 {fails} 次。拦截 {recovery_timeout}s。")
                cache.set(state_key, STATE_OPEN, timeout=recovery_timeout)
        except Exception as e:
            logger.error(f"CircuitBreaker 记录失败出错 ({label}): {e}")

    @classmethod
    def record_success(cls, service_name="default", model_tier=None):
        cls._record_success_for_keys(*cls._get_keys(service_name))
        if model_tier:
            cls._record_success_for_keys(*cls._get_keys(service_name, model_tier))

    @classmethod
    def _record_success_for_keys(cls, fail_key, state_key, half_key):
        try:
            current_state = cache.get(state_key) or STATE_CLOSED
            if current_state == STATE_HALF_OPEN:
                logger.info(f"[CircuitBreaker] 半开探测成功，熔断器闭合。")
                cache.delete(fail_key)
                cache.delete(state_key)
                cache.delete(half_key)
            elif current_state == STATE_CLOSED:
                cache.delete(fail_key)
        except Exception:
            logger.warning("CircuitBreaker 记录成功失败 (Redis 不可用?)", exc_info=True)

    @classmethod
    def check(cls, service_name="default", model_tier=None):
        cls._check_layer(*cls._get_keys(service_name), service_name)
        if model_tier:
            cls._check_layer(*cls._get_keys(service_name, model_tier), f"{model_tier} 模型等级")

    @classmethod
    def _check_layer(cls, fail_key, state_key, half_key, label, model_tier=None):
        threshold, recovery_timeout, __ = cls._get_thresholds(model_tier or 'fast')
        try:
            current_state = cache.get(state_key) or STATE_CLOSED
            if current_state == STATE_OPEN:
                raise CircuitBreakerError(f"Service {label} is currently circuit broken.")
            if current_state == STATE_HALF_OPEN:
                cache.set(half_key, 1, timeout=recovery_timeout)
                return
            return
        except CircuitBreakerError:
            raise
        except Exception as e:
            logger.error(f"CircuitBreaker check 出错 ({label}): {e}")
            return

    @classmethod
    def is_open(cls, service_name="default", model_tier=None):
        try:
            cls.check(service_name, model_tier)
            return False
        except CircuitBreakerError:
            return True
