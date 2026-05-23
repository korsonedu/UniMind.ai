import json
import re
import ssl
import logging
import time
import requests
from requests.adapters import HTTPAdapter
from django.conf import settings
from .config import get_model_for_task
from .observability import record_ai_operation


logger = logging.getLogger(__name__)


def _create_deepseek_session() -> requests.Session:
    """创建强制 TLS 1.2 的 session。"""
    ctx = ssl.create_default_context()
    ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    adapter = HTTPAdapter(pool_connections=10, pool_maxsize=20)
    session = requests.Session()
    session.mount('https://', adapter)
    # 覆盖 adapter 的 SSL context
    adapter.poolmanager.connection_pool_kw['ssl_context'] = ctx
    return session


_session = _create_deepseek_session()


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
        tools=None,
        tool_choice=None,
    ):
        """
        通用的 AI 模型调用接口。

        tools / tool_choice: OpenAI 兼容的 function calling 参数。
        不传则行为与之前完全一致。
        """
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
            msg = "MIMO_API_KEY 未设置，AI 调用被跳过。"
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
                    "max_completion_tokens": max_tokens,
                }
                if tools is not None:
                    body["tools"] = tools
                if tool_choice is not None:
                    body["tool_choice"] = tool_choice
                if config.get('thinking'):
                    body["thinking"] = {"type": "enabled"}

                logger.info(
                    "ai.call_ai request: model=%s operation=%s tool_choice=%s thinking=%s",
                    config['model'], operation, tool_choice, config.get('thinking'),
                )

                r = _session.post(
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
                usage = payload.get('usage', {}) if isinstance(payload, dict) else {}
                record_ai_operation(
                    operation=operation,
                    success=True,
                    duration_ms=duration_ms,
                    metadata={
                        'attempts': attempt + 1,
                        'max_retries': max_retries,
                        'status': r.status_code,
                        'prompt_tokens': usage.get('prompt_tokens', 0),
                        'completion_tokens': usage.get('completion_tokens', 0),
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
        """通用的 JSON 提取工具，支持 Markdown 包裹、混合文本和常见 JSON 瑕疵"""
        if not text:
            return None
        s = text.strip()

        # 1) 直接解析
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            pass

        # 2) 提取 markdown ```json ... ``` 代码块（可在文本任意位置）
        fence_m = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', s, flags=re.I)
        if fence_m:
            try:
                return json.loads(fence_m.group(1).strip())
            except json.JSONDecodeError:
                pass

        # 3) 用括号匹配定位最外层 JSON 对象或数组
        for left, right in [('{', '}'), ('[', ']')]:
            start = s.find(left)
            if start < 0:
                continue
            depth = 0
            end = -1
            for i in range(start, len(s)):
                ch = s[i]
                if ch == left:
                    depth += 1
                elif ch == right:
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if end > start:
                try:
                    return json.loads(s[start:end + 1])
                except json.JSONDecodeError:
                    pass

        logger.warning("JSON 提取失败: %s", text[:200])
        return None

    # ── Tool Calling / Agent ───────────────────────────────────────

    @classmethod
    def _tool_def(cls, name, description, parameters):
        return {
            "type": "function",
            "function": {"name": name, "description": description, "parameters": parameters},
        }

    @classmethod
    def _extract_tool_calls(cls, response):
        if not response:
            return []
        try:
            return response.get('choices', [{}])[0].get('message', {}).get('tool_calls', [])
        except Exception:
            logger.warning("_extract_tool_calls failed: %s", response)
            return []

    @classmethod
    def _extract_content(cls, response):
        if not response:
            return None
        try:
            choices = response.get('choices') or []
            if not choices:
                return None
            content = choices[0].get('message', {}).get('content')
            if not content:
                content = choices[0].get('message', {}).get('reasoning_content')
            return (content or '').strip() or None
        except Exception:
            logger.warning("_extract_content failed for response")
            return None

    @classmethod
    def structured_output(cls, messages, schema, tool_name="output",
                          tool_description="Submit the structured output",
                          temperature=0.7, max_tokens=8192, operation='general',
                          raise_on_error=False):
        """
        强制模型输出符合 JSON Schema 的结构化数据。
        替代 regex-based extract_json()，消除 JSON 解析失败风险。

        DeepSeek thinking mode 不支持指定具体 function 的 tool_choice 对象，
        但支持 "required" 字符串形式，强制模型至少调用一个工具。
        """
        # DeepSeek/OpenAI function calling 要求 parameters schema 顶层 type 必须为 object，
        # 对于 array schema，自动包裹一层 object 并在提取后解包。
        _is_array_schema = schema.get('type') == 'array'
        if _is_array_schema:
            schema = {
                'type': 'object',
                'properties': {'items': schema},
                'required': ['items'],
            }

        tools = [cls._tool_def(tool_name, tool_description, schema)]
        response = cls.call_ai(
            messages=messages,
            tools=tools,
            tool_choice="required",
            temperature=temperature,
            max_tokens=max_tokens,
            operation=operation,
            raise_on_error=raise_on_error,
        )
        if not response:
            return None

        tool_calls = cls._extract_tool_calls(response)
        if tool_calls:
            try:
                result = json.loads(tool_calls[0]['function']['arguments'])
                return result.get('items', result) if _is_array_schema else result
            except (json.JSONDecodeError, TypeError, KeyError):
                pass

        # fallback: 模型未遵守 tool_choice 时，尝试从 content 提取
        content = cls._extract_content(response)
        if content:
            return cls.extract_json(content)
        return None

    @classmethod
    def call_ai_with_tools(cls, messages, tools, tool_executor,
                           tool_choice="auto", temperature=0.7, max_tokens=8192,
                           operation='general', max_tool_rounds=5,
                           raise_on_error=False):
        """
        多轮 Agent 循环：模型可多次调用工具，结果返回后继续推理。

        tool_executor: callable(tool_name, arguments_dict) -> str
        """
        all_messages = list(messages)

        for _ in range(max_tool_rounds):
            response = cls.call_ai(
                messages=all_messages,
                tools=tools,
                tool_choice=tool_choice,
                temperature=temperature,
                max_tokens=max_tokens,
                operation=operation,
                raise_on_error=raise_on_error,
            )
            if not response:
                return None

            tool_calls = cls._extract_tool_calls(response)
            if not tool_calls:
                return response

            # 将 assistant 消息（含 tool_calls）追加到历史
            all_messages.append(response['choices'][0]['message'])

            # 执行工具并追加结果
            for tc in tool_calls:
                func = tc.get('function', {})
                name = func.get('name', '')
                try:
                    args = json.loads(func.get('arguments', '{}'))
                except (json.JSONDecodeError, TypeError):
                    args = {}
                result = tool_executor(name, args)
                all_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get('id', ''),
                    "content": str(result),
                })

            # 首轮后改为 auto，让模型决定是否继续调用工具
            tool_choice = "auto"

        logger.warning(
            "call_ai_with_tools: exhausted max_tool_rounds=%s, "
            "returning last response with %s pending tool_calls",
            max_tool_rounds, len(cls._extract_tool_calls(response)),
        )
        return response

    @classmethod
    def call_ai_stream(cls, messages, temperature=0.7, max_tokens=8192, operation='general', max_retries=None):
        """流式 AI 调用，yield 每个 delta.content 片段。支持重试。"""
        from .circuit_breaker import AICircuitBreaker, CircuitBreakerError

        if max_retries is None:
            max_retries = getattr(settings, "LLM_REQUEST_MAX_RETRIES", 1)
        config = get_model_for_task(operation)
        if not config['api_key']:
            record_ai_operation(operation=operation, success=False, duration_ms=0, error_category='config',
                                metadata={'reason': 'missing_api_key'})
            yield None
            return

        timeout_seconds = max(30, int(getattr(settings, "LLM_REQUEST_TIMEOUT_SECONDS", 120) or 120))

        for attempt in range(max_retries + 1):
            started_at = time.monotonic()

            try:
                AICircuitBreaker.check(operation)
            except CircuitBreakerError:
                record_ai_operation(operation=operation, success=False, duration_ms=0, error_category='circuit_open')
                yield None
                return

            body = {
                "model": config['model'],
                "messages": messages,
                "temperature": temperature,
                "max_completion_tokens": max_tokens,
                "stream": True,
            }
            if config.get('thinking'):
                body["thinking"] = {"type": "enabled"}

            try:
                r = _session.post(
                    config['base_url'],
                    headers={
                        "Authorization": f"Bearer {config['api_key'].strip()}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                    timeout=timeout_seconds,
                    stream=True,
                )
                r.raise_for_status()

                for line in r.iter_lines(decode_unicode=True):
                    if not line or not line.startswith('data: '):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == '[DONE]':
                        break
                    try:
                        data = json.loads(data_str)
                        delta = data.get('choices', [{}])[0].get('delta', {})
                        content = delta.get('content', '')
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

                AICircuitBreaker.record_success(operation)
                duration_ms = int((time.monotonic() - started_at) * 1000)
                record_ai_operation(operation=operation, success=True, duration_ms=duration_ms, metadata={'stream': True})
                return
            except requests.Timeout:
                AICircuitBreaker.record_failure(operation)
                if attempt < max_retries:
                    backoff = 2.0 ** attempt
                    logger.warning("call_ai_stream timeout retry %s/%s in %.1fs", attempt + 1, max_retries, backoff)
                    time.sleep(backoff)
                    continue
                duration_ms = int((time.monotonic() - started_at) * 1000)
                record_ai_operation(operation=operation, success=False, duration_ms=duration_ms, error_category='timeout', metadata={'stream': True})
                yield None
                return
            except requests.HTTPError:
                AICircuitBreaker.record_failure(operation)
                if attempt < max_retries:
                    backoff = 2.0 ** attempt
                    logger.warning("call_ai_stream HTTP error retry %s/%s in %.1fs", attempt + 1, max_retries, backoff)
                    time.sleep(backoff)
                    continue
                duration_ms = int((time.monotonic() - started_at) * 1000)
                record_ai_operation(operation=operation, success=False, duration_ms=duration_ms, error_category='upstream_http', metadata={'stream': True})
                yield None
                return
            except requests.RequestException:
                AICircuitBreaker.record_failure(operation)
                if attempt < max_retries:
                    backoff = 2.0 ** attempt
                    logger.warning("call_ai_stream request error retry %s/%s in %.1fs", attempt + 1, max_retries, backoff)
                    time.sleep(backoff)
                    continue
                duration_ms = int((time.monotonic() - started_at) * 1000)
                record_ai_operation(operation=operation, success=False, duration_ms=duration_ms, error_category='network', metadata={'stream': True})
                yield None
                return

    @classmethod
    def simple_chat(cls, system_prompt, user_prompt, temperature=0.7, max_tokens=3000):
        """便捷的对话接口"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        res = cls.call_ai(messages, temperature=temperature, max_tokens=max_tokens)
        if res and 'choices' in res:
            content = res['choices'][0]['message']['content']
            return content.strip() if content else None
        return None
