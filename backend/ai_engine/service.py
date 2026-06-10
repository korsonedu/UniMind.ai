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
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
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

    # DeepSeek DSML 工具调用标记正则
    # 匹配完整块 <龘xxx>...</龘xxx> 或自闭合 <龘xxx/>
    _DSML_RE_1 = re.compile(r'<龘.*?(?:</龘\w+>|/>)', re.DOTALL)
    # 匹配 <｜｜DSML｜｜xxx>...</｜｜DSML｜｜xxx>
    _DSML_RE_2 = re.compile(r'<｜｜DSML｜｜\w+.*?(?:</｜｜DSML｜｜\w+>)', re.DOTALL)

    @staticmethod
    def _strip_dsml(text: str) -> str:
        """剥离 DeepSeek DSML 工具调用标记，返回干净的用户可见文本。"""
        if not text:
            return text
        # 循环剥离直到无变化
        prev = None
        while prev != text:
            prev = text
            text = AIEngine._DSML_RE_1.sub('', text)
            text = AIEngine._DSML_RE_2.sub('', text)
        # 剥离残留的孤立闭合标签
        text = re.sub(r'</龘\w+>', '', text)
        text = re.sub(r'</｜｜DSML｜｜\w+>', '', text)
        # 流式截断场景：丢弃未闭合标签之后的全部内容
        for marker in ['<龘', '<｜｜DSML｜｜']:
            idx = text.find(marker)
            if idx >= 0:
                text = text[:idx]
        return text.strip()

    @staticmethod
    def _has_open_dsml(text: str) -> bool:
        """检查文本中是否存在未闭合的 DSML 标记块。"""
        import re as _re
        # 格式1: <龘>
        if '<龘' in text:
            opens = len(_re.findall(r'<龘\w+[\s>]|<龘\w+/>', text))
            closes = len(_re.findall(r'</龘\w+>', text))
            if opens > closes:
                return True
        # 格式2: <｜｜DSML｜｜>
        if '<｜｜DSML｜｜' in text:
            opens = len(_re.findall(r'<｜｜DSML｜｜\w+', text))
            closes = len(_re.findall(r'</｜｜DSML｜｜\w+>', text))
            if opens > closes:
                return True
        return False

    @staticmethod
    def _parse_dsml_tool_calls(text: str):
        """从含有 DSML 标记的文本中提取工具调用列表（OpenAI 兼容格式）。

        支持两种 DeepSeek 原生格式：
        1. <龘invoke name="..."> <龘parameter name="..." string="true|false">VALUE</龘parameter> </龘invoke>
        2. <｜｜DSML｜｜invoke name="..."> <｜｜DSML｜｜parameter name="...">VALUE</｜｜DSML｜｜parameter> </｜｜DSML｜｜invoke>
        """
        import re as _re
        tool_calls = []

        patterns = [
            # 格式1: <龘invoke> 带 string="true|false" 属性
            (
                _re.compile(r'<龘invoke\s+name="([^"]+)">(.*?)</龘invoke>', _re.DOTALL),
                _re.compile(r'<龘parameter\s+name="([^"]+)"\s+string="([^"]+)">(.*?)</龘parameter>', _re.DOTALL),
                True,  # has_string_attr
            ),
            # 格式2: <｜｜DSML｜｜invoke> 无 string 属性
            (
                _re.compile(r'<｜｜DSML｜｜invoke\s+name="([^"]+)">(.*?)</｜｜DSML｜｜invoke>', _re.DOTALL),
                _re.compile(r'<｜｜DSML｜｜parameter\s+name="([^"]+)"[^>]*>(.*?)</｜｜DSML｜｜parameter>', _re.DOTALL),
                False,
            ),
        ]

        for invoke_pattern, param_pattern, has_string_attr in patterns:
            for invoke_match in invoke_pattern.finditer(text):
                func_name = invoke_match.group(1)
                invoke_body = invoke_match.group(2)
                args = {}
                for p in param_pattern.finditer(invoke_body):
                    pname = p.group(1)
                    if has_string_attr:
                        is_string = p.group(2) == 'true'
                        pval = p.group(3).strip()
                        if is_string:
                            args[pname] = pval
                        else:
                            try:
                                args[pname] = json.loads(pval)
                            except (json.JSONDecodeError, TypeError):
                                args[pname] = pval
                    else:
                        pval = p.group(2).strip()
                        try:
                            args[pname] = json.loads(pval)
                        except (json.JSONDecodeError, ValueError):
                            args[pname] = pval

                tool_calls.append({
                    "id": f"dsml_{len(tool_calls)}_{func_name}",
                    "type": "function",
                    "function": {
                        "name": func_name,
                        "arguments": json.dumps(args, ensure_ascii=False),
                    },
                })

        return tool_calls

    @staticmethod
    def _build_body(config, messages, temperature, max_tokens, tools, tool_choice, stream=False, _preserve_tool_choice=False):
        """构建 LLM 请求体。处理 DeepSeek thinking mode 对 tool_choice 的限制。"""
        body = {
            "model": config['model'],
            "messages": messages,
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
        }
        if stream:
            body["stream"] = True
        if tools is not None:
            body["tools"] = tools
        if config.get('thinking'):
            body["thinking"] = {"type": "enabled"}
        # DeepSeek 不支持 tool_choice="required"（agent chat 场景），降级为 auto
        # structured_output 场景通过 _preserve_tool_choice=True 跳过降级
        if not _preserve_tool_choice and 'deepseek' in config.get('model', '').lower() and tool_choice == "required":
            tool_choice = "auto"
        if tool_choice is not None:
            body["tool_choice"] = tool_choice
        return body

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
        _preserve_tool_choice=False,
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
            msg = "LLM_API_KEY 未设置，AI 调用被跳过。"
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
                body = cls._build_body(config, messages, temperature, max_tokens, tools, tool_choice, _preserve_tool_choice=_preserve_tool_choice)

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
            tool_calls = response.get('choices', [{}])[0].get('message', {}).get('tool_calls', [])
            if tool_calls:
                return tool_calls
        except Exception:
            logger.warning("_extract_tool_calls failed: %s", response)
            return []

        # DeepSeek 有时把 tool call 以 DSML 原生格式放在 content 里
        try:
            content = response.get('choices', [{}])[0].get('message', {}).get('content', '')
            if content:
                parsed = cls._parse_dsml_tool_calls(content)
                if parsed:
                    return parsed
        except Exception:
            pass
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

        DeepSeek thinking mode 不支持 tool_choice="required"，只支持默认的
        "auto"（即不传 tool_choice）。当 thinking 开启时自动降级为 "auto"，
        并通过 prompt 引导模型调用工具，同时保留 content fallback。
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

        # DeepSeek thinking mode rejects explicit tool_choice — handled in call_ai.
        # When thinking is on, tool_choice is stripped from the request body.
        # Use "required" for non-thinking tasks to enforce structured output.
        _tool_choice = "required"

        tools = [cls._tool_def(tool_name, tool_description, schema)]
        response = cls.call_ai(
            messages=messages,
            tools=tools,
            tool_choice=_tool_choice,
            temperature=temperature,
            max_tokens=max_tokens,
            operation=operation,
            raise_on_error=raise_on_error,
            _preserve_tool_choice=True,
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

        # fallback: 模型有时把 JSON 放在 content 而非 tool_calls 里
        content = cls._extract_content(response)
        if content:
            logger.info("structured_output fallback: content_len=%d preview=%r", len(content), content[:200])
            try:
                result = json.loads(content)
                logger.info("structured_output fallback: direct JSON parse succeeded")
                return result.get('items', result) if _is_array_schema else result
            except (json.JSONDecodeError, TypeError, KeyError):
                import re
                json_match = re.search(r'\[[\s\S]*\]|\{[\s\S]*\}', content)
                if json_match:
                    try:
                        result = json.loads(json_match.group())
                        logger.info("structured_output fallback: regex JSON parse succeeded")
                        return result.get('items', result) if _is_array_schema else result
                    except (json.JSONDecodeError, TypeError, KeyError) as e:
                        logger.warning("structured_output fallback: regex JSON parse failed: %s", e)
                else:
                    logger.warning("structured_output fallback: no JSON pattern found in content")
        else:
            logger.warning("structured_output fallback: content is empty/None")

        logger.warning(
            "structured_output: model did not call tool '%s' operation=%s",
            tool_name, operation,
        )
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
                # 剥离可能混入 content 的 DSML 工具调用标记
                raw_content = response['choices'][0]['message'].get('content') or ''
                if raw_content:
                    response['choices'][0]['message']['content'] = cls._strip_dsml(raw_content)
                return response

            # 将 assistant 消息（含 tool_calls + reasoning_content）追加到历史
            # DeepSeek thinking mode 要求后续轮次完整回传 reasoning_content
            raw_msg = response['choices'][0]['message']
            assistant_msg = {
                "role": "assistant",
                "content": raw_msg.get('content'),
                "tool_calls": tool_calls,
            }
            if raw_msg.get('reasoning_content'):
                assistant_msg["reasoning_content"] = raw_msg['reasoning_content']
            all_messages.append(assistant_msg)

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
                    "type": "tool",
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
    def call_ai_with_streaming_tools(cls, messages, tools, tool_executor,
                                      on_step=None, on_message=None, tool_choice="auto",
                                      temperature=0.7, max_tokens=8192,
                                      operation='general', max_tool_rounds=5,
                                      raise_on_error=False):
        """
        多轮 Agent 循环 + 流式输出 + 步骤回调。

        与 call_ai_with_tools 相同逻辑，但：
        1. LLM 调用使用 stream=True，逐 token 推送 text_delta
        2. 每步 tool call/result 通过 on_step 回调推送

        on_step: callable(event_dict) — 接收 step/text_delta/done/error 事件
        on_message: callable(text) — 有 tool_calls 的轮次，通过此回调发送中间消息
        返回: {"content": str} 最后一轮文本（无 tool_calls 时）
        """
        from .circuit_breaker import AICircuitBreaker, CircuitBreakerError
        from django.conf import settings as _settings

        all_messages = list(messages)
        accumulated_text = ""
        all_rounds_text = []  # 收集所有轮次的中间文本，避免耗尽 rounds 时丢失

        for round_i in range(max_tool_rounds):
            config = get_model_for_task(operation)
            if not config['api_key']:
                if on_step:
                    on_step({"type": "error", "message": "LLM_API_KEY 未设置"})
                return {"content": ""}

            try:
                AICircuitBreaker.check(operation)
            except CircuitBreakerError:
                if on_step:
                    on_step({"type": "error", "message": "AI 服务熔断中，请稍后重试"})
                return {"content": ""}

            body = cls._build_body(config, all_messages, temperature, max_tokens, tools, tool_choice, stream=True)

            timeout_seconds = max(30, int(getattr(_settings, "LLM_REQUEST_TIMEOUT_SECONDS", 120) or 120))

            # Log request body (without full messages/tools for readability)
            _body_log = {k: v for k, v in body.items() if k not in ('messages', 'tools')}
            _body_log['tools_count'] = len(body.get('tools', []))
            logger.info(
                "ai.call_ai_stream request: model=%s operation=%s round=%s msgs=%s body=%s",
                config['model'], operation, round_i, len(all_messages), json.dumps(_body_log, ensure_ascii=False),
            )
            if round_i > 0:
                for i, m in enumerate(all_messages):
                    role = m.get('role', '?')
                    tc = len(m.get('tool_calls', [])) if m.get('tool_calls') else 0
                    tcid = m.get('tool_call_id', '')
                    content_len = len(str(m.get('content', '')))
                    logger.info("  msg[%s] role=%s content_len=%s tool_calls=%s tool_call_id=%s", i, role, content_len, tc, tcid)

            # Debug: dump message format on follow-up rounds
            if round_i > 0:
                for mi, m in enumerate(all_messages):
                    if m.get('role') == 'assistant' and m.get('tool_calls'):
                        logger.info("  follow-up assistant msg[%s] keys=%s has_reasoning=%s tc_count=%s",
                                    mi, list(m.keys()), 'reasoning_content' in m, len(m.get('tool_calls', [])))
                        # Log first tool_call structure
                        tc0 = m['tool_calls'][0] if m['tool_calls'] else {}
                        logger.info("  tc[0] keys=%s", list(tc0.keys()))

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
            except Exception as e:
                # Log full request body for 4xx errors
                error_body = ""
                try:
                    if hasattr(e, 'response') and e.response is not None:
                        error_body = e.response.text[:800]
                except Exception:
                    pass
                # Also dump the messages that caused the error
                if round_i > 0:
                    for mi, m in enumerate(all_messages):
                        role = m.get('role', '?')
                        keys = list(m.keys())
                        tc = len(m.get('tool_calls', [])) if m.get('tool_calls') else 0
                        logger.error("  FAIL msg[%s] role=%s keys=%s tc=%s content_preview=%s",
                                     mi, role, keys, tc, str(m.get('content', ''))[:100])
                logger.error("call_ai_with_streaming_tools HTTP error: operation=%s round=%s err=%s body=%s", operation, round_i, e, error_body)
                AICircuitBreaker.record_failure(operation)
                if on_step:
                    on_step({"type": "error", "message": f"AI 调用失败: {e}"})
                return {"content": accumulated_text or "AI 服务暂时不可用，请稍后重试。"}

            # Consume SSE stream
            tool_calls_map = {}
            finish_reason = None
            reasoning_content = ""
            text_emitted_this_round = 0  # Track how much clean text was already emitted

            for line in r.iter_lines(decode_unicode=True):
                if not line or not line.startswith('data: '):
                    continue
                data_str = line[6:]
                if data_str.strip() == '[DONE]':
                    break
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                choice = data.get('choices', [{}])[0]
                delta = choice.get('delta', {})
                finish_reason = choice.get('finish_reason') or finish_reason

                # Capture reasoning_content for thinking mode (DeepSeek requires it in follow-up)
                rc = delta.get('reasoning_content') or ''
                if rc:
                    reasoning_content += rc

                content = delta.get('content', '')
                if content:
                    accumulated_text += content
                    # 流式 DSML 过滤：如果在 DSML 块中（有 <龘 且未闭合），
                    # 暂不 emit，等完整后再一次性剥离+发送，防止 DSML 泄露到前端
                    in_dsml = cls._has_open_dsml(accumulated_text)
                    if not in_dsml:
                        clean_text = cls._strip_dsml(accumulated_text)
                        new_clean = clean_text[text_emitted_this_round:]
                        if new_clean and on_step:
                            on_step({"type": "text_delta", "delta": new_clean})
                        text_emitted_this_round = len(clean_text)

                for tc_chunk in delta.get('tool_calls', []):
                    idx = tc_chunk.get('index', 0)
                    if idx not in tool_calls_map:
                        tool_calls_map[idx] = {
                            "id": tc_chunk.get('id', ''),
                            "type": "function",
                            "function": {"name": '', "arguments": ''},
                        }
                    tc = tool_calls_map[idx]
                    if tc_chunk.get('id'):
                        tc['id'] = tc_chunk['id']
                    func_chunk = tc_chunk.get('function', {})
                    if func_chunk.get('name'):
                        tc['function']['name'] = func_chunk['name']
                    if func_chunk.get('arguments'):
                        tc['function']['arguments'] += func_chunk['arguments']

            AICircuitBreaker.record_success(operation)

            tool_calls = [tool_calls_map[k] for k in sorted(tool_calls_map.keys())] if tool_calls_map else []

            # DSML fallback: 如果 DeepSeek 把工具调用作为 DSML 文本输出而没有标准 tool_calls，
            # 从 accumulated_text 中解析 DSML 并转为 tool_calls
            if not tool_calls and ('<龘' in accumulated_text or '<｜｜DSML｜｜' in accumulated_text):
                dsml_tool_calls = cls._parse_dsml_tool_calls(accumulated_text)
                if dsml_tool_calls:
                    tool_calls = dsml_tool_calls
                    logger.info(
                        "call_ai_with_streaming_tools: parsed %d tool calls from DSML",
                        len(tool_calls)
                    )

            logger.info("call_ai_with_streaming_tools round=%s done: text_len=%s tool_calls=%s finish_reason=%s",
                        round_i, len(accumulated_text), len(tool_calls), finish_reason)

            # 预先剥离 DSML，避免后续多处重复计算
            clean_accumulated = cls._strip_dsml(accumulated_text)

            if not tool_calls:
                return {"content": clean_accumulated}

            # Emit any remaining clean text that wasn't streamed during this round
            remaining = clean_accumulated[text_emitted_this_round:]
            if remaining and on_step:
                on_step({"type": "text_delta", "delta": remaining})

            # 有 tool_calls 的轮次：该轮文本通过 on_message 发出（因为不会 return）
            if clean_accumulated:
                all_rounds_text.append(clean_accumulated)
                if on_message:
                    on_message(clean_accumulated)

            # Build assistant message matching DeepSeek API format
            assistant_msg = {
                "role": "assistant",
                "content": clean_accumulated or None,
                "tool_calls": tool_calls,
            }
            if reasoning_content:
                assistant_msg["reasoning_content"] = reasoning_content
            all_messages.append(assistant_msg)

            for tc in tool_calls:
                func = tc.get('function', {})
                name = func.get('name', '')
                call_id = tc.get('id', '')
                try:
                    args = json.loads(func.get('arguments', '{}'))
                except (json.JSONDecodeError, TypeError):
                    args = {}

                try:
                    from ai_assistant.services.tool_executor import generate_step_label, summarize_tool_result
                    label = generate_step_label(name, args)
                except ImportError:
                    label = f"执行 {name}"
                    summarize_tool_result = None

                if on_step:
                    on_step({
                        "type": "step",
                        "call_id": call_id,
                        "step": round_i + 1,
                        "status": "calling",
                        "name": name,
                        "label": label,
                        "args_summary": json.dumps(args, ensure_ascii=False)[:200],
                    })

                # 让工具内部能拿到真实 call_id，用于发送进度事件
                if hasattr(tool_executor, '_current_call_id'):
                    tool_executor._current_call_id = call_id

                try:
                    result = tool_executor(name, args)
                except Exception as e:
                    result = json.dumps({"error": str(e)}, ensure_ascii=False)

                step_event = {
                    "type": "step",
                    "call_id": call_id,
                    "step": round_i + 1,
                    "status": "done",
                    "name": name,
                    "label": label,
                    "result_summary": summarize_tool_result(name, result) if summarize_tool_result else str(result)[:200],
                }
                # render_visual: attach full payload for frontend rendering
                if name == "render_visual" and hasattr(tool_executor, 'pending_visuals'):
                    logger.info("[step] render_visual pending_visuals count=%d", len(tool_executor.pending_visuals))
                    if tool_executor.pending_visuals:
                        pv = tool_executor.pending_visuals[-1]  # Latest visual for step event
                        # Ensure payload is dict (DeepSeek may pass it as JSON string)
                        if isinstance(pv.get('payload'), str):
                            try:
                                pv['payload'] = json.loads(pv['payload'])
                            except (json.JSONDecodeError, TypeError):
                                pv['payload'] = {}
                        step_event["visual"] = pv
                if on_step:
                    on_step(step_event)

                all_messages.append({
                    "role": "tool",
                    "content": str(result),
                    "tool_call_id": call_id,
                })

            accumulated_text = ""
            if round_i < max_tool_rounds - 2:
                tool_choice = "required"
            else:
                tool_choice = "auto"

        logger.warning(
            "call_ai_with_streaming_tools: exhausted max_tool_rounds=%s, forcing final text reply",
            max_tool_rounds,
        )
        # 工具轮次用完后，强制追加一轮纯文本生成
        all_messages.append({
            "role": "system",
            "content": "工具调用轮次已用完。请根据已有信息直接给出最终回复，不要再调用任何工具。",
        })
        try:
            config = get_model_for_task(operation)
            final_resp = cls.call_ai(
                messages=all_messages,
                tools=None,
                tool_choice="none",
                temperature=temperature,
                max_tokens=max_tokens,
                operation=operation,
            )
            final_text = ""
            if final_resp and isinstance(final_resp, dict):
                final_text = final_resp.get("content", "") or ""
                if not final_text and "choices" in final_resp:
                    final_text = final_resp["choices"][0]["message"]["content"] or ""
            if final_text:
                final_text = cls._strip_dsml(final_text)
                if on_step:
                    on_step({"type": "text_delta", "delta": final_text})
                return {"content": final_text}
        except Exception as e:
            logger.exception("Final text reply failed: %s", e)

        # 合并所有轮次的中间文本，避免丢失
        combined = accumulated_text or ""
        if not combined and all_rounds_text:
            combined = "\n\n".join(all_rounds_text)
        return {"content": cls._strip_dsml(combined)}

    @classmethod
    def agentic_structured_output(cls, messages, schema, tool_name, tool_description,
                                  research_tools, tool_executor,
                                  temperature=0.7, max_tokens=8192, operation='general',
                                  max_tool_rounds=5, raise_on_error=False):
        """
        多轮 Agent + 结构化输出：模型可先调用研究工具获取信息，再提交结构化结果。

        流程：
        1. 将 research_tools + submit tool 一起传给模型（不传 tool_choice）
        2. 模型自主决定是否/何时调用研究工具
        3. 模型调用 submit tool → 提取 arguments 作为结构化结果返回
        4. 模型未调用 submit tool → 返回 None（无 fallback）

        research_tools: [{"type":"function","function":{...}}, ...]  研究用工具
        tool_executor:  callable(tool_name, arguments_dict) -> str   研究工具执行器
        schema/tool_name/tool_description: 最终提交工具的 JSON Schema
        """
        submit_tool = cls._tool_def(tool_name, tool_description, schema)
        all_tools = list(research_tools) + [submit_tool]
        all_messages = list(messages)

        for _ in range(max_tool_rounds):
            response = cls.call_ai(
                messages=all_messages,
                tools=all_tools,
                tool_choice="auto",
                temperature=temperature,
                max_tokens=max_tokens,
                operation=operation,
                raise_on_error=raise_on_error,
            )
            if not response:
                return None

            tool_calls = cls._extract_tool_calls(response)
            if not tool_calls:
                # model stopped calling tools without submitting — no fallback
                logger.warning(
                    "agentic_structured_output: model did not call submit tool '%s' operation=%s",
                    tool_name, operation,
                )
                return None

            all_messages.append(response['choices'][0]['message'])

            final_result = None
            for tc in tool_calls:
                func = tc.get('function', {})
                name = func.get('name', '')
                try:
                    args = json.loads(func.get('arguments', '{}'))
                except (json.JSONDecodeError, TypeError):
                    args = {}

                if name == tool_name:
                    final_result = args
                    # 给模型一个确认，让它知道提交成功
                    all_messages.append({
                        "role": "tool",
                        "type": "tool",
                        "tool_call_id": tc.get('id', ''),
                        "content": "ok",
                    })
                else:
                    result = tool_executor(name, args)
                    all_messages.append({
                        "role": "tool",
                        "type": "tool",
                        "tool_call_id": tc.get('id', ''),
                        "content": str(result),
                    })

            if final_result is not None:
                return final_result

        logger.warning(
            "agentic_structured_output: exhausted max_tool_rounds=%s", max_tool_rounds,
        )
        return None

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
