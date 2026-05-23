import time
import logging
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# 三态: closed → open → half_open → closed
STATE_CLOSED = "closed"
STATE_OPEN = "open"
STATE_HALF_OPEN = "half_open"


class CircuitBreakerError(Exception):
    """当熔断器处于打开状态时抛出的异常"""
    pass


class AICircuitBreaker:
    """
    标准三态熔断器 (closed → open → half_open → closed).

    - closed:     正常放行，累计失败计数
    - open:       直接拒绝，等待 recovery_timeout 后自动转 half_open
    - half_open:  放行探测请求，成功则闭合，失败则重新打开
    """

    @classmethod
    def _get_thresholds(cls):
        return (
            getattr(settings, 'AI_CB_FAILURE_THRESHOLD', 5),
            getattr(settings, 'AI_CB_RECOVERY_TIMEOUT', 300),
            getattr(settings, 'AI_CB_WINDOW_TIMEOUT', 60),
        )

    @classmethod
    def _get_keys(cls, service_name="default"):
        return (
            f"ai_cb_fails_{service_name}",
            f"ai_cb_state_{service_name}",
            f"ai_cb_half_open_success_{service_name}",
        )

    @classmethod
    def record_failure(cls, service_name="default"):
        fail_key, state_key, half_key = cls._get_keys(service_name)
        threshold, recovery_timeout, window_timeout = cls._get_thresholds()

        try:
            current_state = cache.get(state_key) or STATE_CLOSED
            fails = cache.get(fail_key, 0)
            fails += 1

            if current_state == STATE_HALF_OPEN:
                # 半开状态下探测请求失败 → 重新打开
                logger.critical(
                    f"[CircuitBreaker] {service_name} 半开探测失败，重新熔断 {recovery_timeout}s。"
                )
                cache.set(state_key, STATE_OPEN, timeout=recovery_timeout)
                cache.set(fail_key, threshold, timeout=recovery_timeout)
                return

            # closed 状态：累计失败
            cache.set(fail_key, fails, timeout=window_timeout)

            if fails >= threshold:
                if current_state != STATE_OPEN:
                    logger.critical(
                        f"[CircuitBreaker] {service_name} 触发熔断！"
                        f"{window_timeout}s 内失败 {fails} 次。拦截 {recovery_timeout}s。"
                    )
                cache.set(state_key, STATE_OPEN, timeout=recovery_timeout)
        except Exception as e:
            logger.error(f"CircuitBreaker 记录失败状态出错: {e}")

    @classmethod
    def record_success(cls, service_name="default"):
        fail_key, state_key, half_key = cls._get_keys(service_name)
        threshold, recovery_timeout, window_timeout = cls._get_thresholds()

        try:
            current_state = cache.get(state_key) or STATE_CLOSED

            if current_state == STATE_HALF_OPEN:
                # 半开探测成功 → 闭合
                logger.info(
                    f"[CircuitBreaker] {service_name} 半开探测成功，熔断器闭合。"
                )
                cache.delete(fail_key)
                cache.delete(state_key)
                cache.delete(half_key)
            elif current_state == STATE_CLOSED:
                # 正常成功 → 重置失败计数
                cache.delete(fail_key)
            # STATE_OPEN 时不应有请求通过 check()，忽略
        except Exception:
            pass

    @classmethod
    def is_open(cls, service_name="default"):
        fail_key, state_key, half_key = cls._get_keys(service_name)
        try:
            current_state = cache.get(state_key)
            if current_state == STATE_OPEN:
                return True
            if current_state == STATE_HALF_OPEN:
                return False
            return False
        except Exception:
            return False

    @classmethod
    def check(cls, service_name="default"):
        """
        检查是否放行。如果当前是 open 状态，检查是否可以转 half_open。
        转为 half_open 后放行（探测请求）。
        """
        fail_key, state_key, half_key = cls._get_keys(service_name)
        threshold, recovery_timeout, window_timeout = cls._get_thresholds()

        try:
            current_state = cache.get(state_key) or STATE_CLOSED

            if current_state == STATE_OPEN:
                raise CircuitBreakerError(
                    f"Service {service_name} is currently circuit broken."
                )

            if current_state == STATE_HALF_OPEN:
                cache.set(half_key, 1, timeout=recovery_timeout)
                return  # 放行探测请求

            # STATE_CLOSED → 正常放行
            return
        except CircuitBreakerError:
            raise
        except Exception as e:
            logger.error(f"CircuitBreaker check 出错: {e}")
            # 不确定状态 → 放行，避免误拦
            return
