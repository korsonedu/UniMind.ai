import json
import re
import logging
import time
import requests
from django.conf import settings
from .config import get_llm_config, get_model_for_task
from .observability import record_ai_operation


logger = logging.getLogger(__name__)


class AICallError(Exception):
    """AI 调用失败时的显式异常，供视图层返回更准确状态码。"""

    def __init__(
        self,
        message: str,
        status_code: int = 502,
        retryable: bool = False,
        error_category: str = "unknown",
        upstream_status: int = 0,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.error_category = str(error_category or "unknown")
        self.upstream_status = int(upstream_status or 0)


class AIEngine:
    """底层的 AI 引擎服务类，负责通用的 AI 模型调用逻辑"""

    @classmethod
    def call_ai(
        cls,
        messages,
        temperature=0.7,
        max_tokens=8192,
        raise_on_error=False,
        operation='general',
    ):
        """通用的 AI 模型调用接口"""
        from .circuit_breaker import AICircuitBreaker, CircuitBreakerError
        started_at = time.monotonic()

        try:
            AICircuitBreaker.check(operation)
        except CircuitBreakerError as e:
            logger.warning("AI 熔断器已打开: operation=%s", operation)
            if raise_on_error:
                raise AICallError(
                    str(e), status_code=503, retryable=True, error_category='circuit_open',
                )
            return None

        config = get_model_for_task(operation)
        if not config['api_key']:
            msg = "DEEPSEEK_API_KEY 未设置，AI 调用被跳过。"
            logger.error(msg)
            duration_ms = int((time.monotonic() - started_at) * 1000)
            record_ai_operation(
                operation=operation,
                success=False,
                duration_ms=duration_ms,
                error_category='config',
                metadata={'reason': 'missing_api_key'},
            )
            if raise_on_error:
                raise AICallError(msg, status_code=500, retryable=False, error_category='config')
            return None

        timeout_seconds = max(10, int(getattr(settings, "LLM_REQUEST_TIMEOUT_SECONDS", 120) or 120))
        max_retries = max(0, int(getattr(settings, "LLM_REQUEST_MAX_RETRIES", 1) or 1))

        for attempt in range(max_retries + 1):
            try:
                body = {
                    "model": config['model'],
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if config.get('thinking'):
                    body["reasoning_effort"] = config['thinking']

                r = requests.post(
                    config['base_url'],
                    headers={
                        "Authorization": f"Bearer {config['api_key'].strip()}",
                        "Content-Type": "application/json"
                    },
                    json=body,
                    timeout=timeout_seconds
                )
                r.raise_for_status()
                payload = r.json()
                AICircuitBreaker.record_success(operation)
                duration_ms = int((time.monotonic() - started_at) * 1000)
                record_ai_operation(
                    operation=operation,
                    success=True,
                    duration_ms=duration_ms,
                    metadata={
                        'attempts': attempt + 1,
                        'max_retries': max_retries,
                        'status': r.status_code,
                    },
                )
                return payload
            except requests.Timeout as e:
                AICircuitBreaker.record_failure(operation)
                logger.warning(
                    "AI 调用超时: attempt=%s/%s timeout=%ss err=%s",
                    attempt + 1,
                    max_retries + 1,
                    timeout_seconds,
                    e,
                )
                if attempt < max_retries:
                    time.sleep(min(2 ** attempt, 4))
                    continue
                msg = f"AI 服务响应超时（>{timeout_seconds}s），请稍后重试。"
                duration_ms = int((time.monotonic() - started_at) * 1000)
                record_ai_operation(
                    operation=operation,
                    success=False,
                    duration_ms=duration_ms,
                    error_category='timeout',
                    metadata={'attempts': attempt + 1, 'max_retries': max_retries},
                )
                if raise_on_error:
                    raise AICallError(
                        msg,
                        status_code=504,
                        retryable=True,
                        error_category='timeout',
                    ) from e
                return None
            except requests.HTTPError as e:
                AICircuitBreaker.record_failure(operation)
                response = getattr(e, "response", None)
                status = response.status_code if response is not None else 502
                detail = (response.text or "")[:500] if response is not None else ""
                retryable = status in {408, 409, 425, 429} or status >= 500
                logger.error("AI HTTP异常: status=%s retryable=%s detail=%s", status, retryable, detail)
                if retryable and attempt < max_retries:
                    time.sleep(min(2 ** attempt, 4))
                    continue
                if status == 429:
                    error_category = 'rate_limit'
                elif status >= 500:
                    error_category = 'upstream_5xx'
                elif status >= 400:
                    error_category = 'upstream_4xx'
                else:
                    error_category = 'upstream_http'
                duration_ms = int((time.monotonic() - started_at) * 1000)
                record_ai_operation(
                    operation=operation,
                    success=False,
                    duration_ms=duration_ms,
                    error_category=error_category,
                    metadata={'attempts': attempt + 1, 'status': status},
                )
                msg = "AI 服务暂时不可用，请稍后重试。" if retryable else "AI 服务请求失败，请检查模型配置。"
                if raise_on_error:
                    raise AICallError(
                        msg,
                        status_code=503 if retryable else 502,
                        retryable=retryable,
                        error_category=error_category,
                        upstream_status=status,
                    ) from e
                return None
            except requests.RequestException as e:
                AICircuitBreaker.record_failure(operation)
                logger.warning("AI 网络异常: attempt=%s/%s err=%s", attempt + 1, max_retries + 1, e)
                if attempt < max_retries:
                    time.sleep(min(2 ** attempt, 4))
                    continue
                msg = "AI 网络连接异常，请稍后重试。"
                duration_ms = int((time.monotonic() - started_at) * 1000)
                record_ai_operation(
                    operation=operation,
                    success=False,
                    duration_ms=duration_ms,
                    error_category='network',
                    metadata={'attempts': attempt + 1, 'max_retries': max_retries},
                )
                if raise_on_error:
                    raise AICallError(
                        msg,
                        status_code=503,
                        retryable=True,
                        error_category='network',
                    ) from e
                return None
            except ValueError as e:
                logger.exception("AI 返回 JSON 解析失败: %s", e)
                msg = "AI 服务返回格式异常，请稍后重试。"
                duration_ms = int((time.monotonic() - started_at) * 1000)
                record_ai_operation(
                    operation=operation,
                    success=False,
                    duration_ms=duration_ms,
                    error_category='invalid_json',
                    metadata={'attempts': attempt + 1},
                )
                if raise_on_error:
                    raise AICallError(
                        msg,
                        status_code=502,
                        retryable=True,
                        error_category='invalid_json',
                    ) from e
                return None
            except Exception as e:
                logger.exception("AI 调用异常: %s", e)
                duration_ms = int((time.monotonic() - started_at) * 1000)
                record_ai_operation(
                    operation=operation,
                    success=False,
                    duration_ms=duration_ms,
                    error_category='unexpected',
                    metadata={'attempts': attempt + 1},
                )
                if raise_on_error:
                    raise AICallError(
                        "AI 服务内部异常，请稍后重试。",
                        status_code=500,
                        retryable=False,
                        error_category='unexpected',
                    ) from e
                return None

    @classmethod
    def extract_json(cls, text):
        """通用的 JSON 提取工具，支持 Markdown 包裹和纯文本"""
        if not text:
            return None
        try:
            # 尝试直接解析
            return json.loads(text.strip())
        except json.JSONDecodeError:
            # 尝试正则提取 Markdown 代码块
            content = re.sub(r'^```(json)?\s*', '', text.strip(), flags=re.I)
            content = re.sub(r'\s*```$', '', content)
            try:
                return json.loads(content)
            except Exception as e:
                logger.warning("JSON 提取失败: %s", e)
                return None

    @classmethod
    def simple_chat(cls, system_prompt, user_prompt, temperature=0.7, max_tokens=3000):
        """便捷的对话接口"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        res = cls.call_ai(messages, temperature=temperature, max_tokens=max_tokens)
        if res and 'choices' in res:
            return res['choices'][0]['message']['content'].strip()
        return None
