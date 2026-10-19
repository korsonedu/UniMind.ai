"""阿里云百炼 Qwen 文件转写提供者（异步 URL ASR）。

配置来自 settings.ASR_PROVIDER_CONFIG['qwen_filetrans']：
    api_key / base_url / model / timeout / poll_interval / max_wait

该提供者只接受 HTTP(S) URL，视频由 Qwen 侧异步抓取，不需要本地下载。
"""

import logging
import re
import time

import requests

from .base import ASRProvider, ASRProviderRegistry, TranscriptResult, TranscriptSegment

logger = logging.getLogger(__name__)


class QwenFileTransASRProvider(ASRProvider):
    """Qwen 异步文件转写，保留句级时间戳。"""

    supports_url = True

    DEFAULT_BASE_URL = "https://maas.qianwenaiapi.com/api/v1"
    DEFAULT_MODEL = "qwen-audio-3.1-asr-flash-filetrans"
    DEFAULT_MAX_WAIT = 3600
    RETRY_DELAYS = (2, 5, 10)

    def transcribe(self, audio_path: str) -> TranscriptResult:
        raise NotImplementedError("qwen_filetrans 仅支持 transcribe_url，不支持本地文件")

    def transcribe_url(self, url: str) -> TranscriptResult:
        api_key = self.config.get("api_key", "")
        if not api_key:
            raise ValueError("Qwen ASR 需要 api_key，请设置 QWEN_ASR_API_KEY 环境变量")

        base_url = str(self.config.get("base_url") or self.DEFAULT_BASE_URL).rstrip("/")
        model = self.config.get("model") or self.DEFAULT_MODEL
        timeout = float(self.config.get("timeout", 60))
        poll_interval = float(self.config.get("poll_interval", 3))
        max_wait = min(float(self.config.get("max_wait", self.DEFAULT_MAX_WAIT)), self.DEFAULT_MAX_WAIT)

        deadline = time.monotonic() + max_wait
        headers = {"Authorization": f"Bearer {api_key}"}

        submit_response = self._request_with_retry(
            "提交 Qwen ASR 任务",
            lambda: requests.post(
                f"{base_url}/services/audio/asr/transcription",
                headers={
                    **headers,
                    "Content-Type": "application/json",
                    "X-DashScope-Async": "enable",
                },
                json={
                    "model": model,
                    "input": {"file_urls": [url]},
                    "parameters": {},
                },
                timeout=timeout,
            ),
        )
        submitted = self._read_json(submit_response, "提交 Qwen ASR 任务")
        output = submitted.get("output") if isinstance(submitted.get("output"), dict) else {}
        task_id = output.get("task_id")
        if not task_id:
            raise RuntimeError(f"Qwen ASR 任务提交失败: {self._error_detail(submitted)}")
        logger.info("Qwen ASR task submitted: task_id=%s status=%s", task_id, output.get("task_status"))

        polled = None
        task_status = None
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"Qwen ASR 任务轮询超时: task_id={task_id}, status={task_status or 'PENDING'}"
                )
            poll_response = self._request_with_retry(
                "查询 Qwen ASR 任务",
                lambda: requests.get(f"{base_url}/tasks/{task_id}", headers=headers, timeout=timeout),
            )
            polled = self._read_json(poll_response, "查询 Qwen ASR 任务")
            output = polled.get("output") if isinstance(polled.get("output"), dict) else {}
            task_status = output.get("task_status")
            if task_status == "SUCCEEDED":
                break
            if task_status in ("FAILED", "CANCELED"):
                raise RuntimeError(
                    f"Qwen ASR 任务{task_status}: task_id={task_id}, {self._error_detail(polled)}"
                )
            time.sleep(poll_interval)

        results = output.get("results") if isinstance(output.get("results"), list) else []
        for item in results:
            if not isinstance(item, dict):
                continue
            subtask_status = item.get("subtask_status")
            if subtask_status and subtask_status != "SUCCEEDED":
                raise RuntimeError(
                    f"Qwen ASR 子任务{subtask_status}: task_id={task_id}, {self._error_detail(polled)}"
                )

        transcription_url = None
        if results and isinstance(results[0], dict):
            transcription_url = results[0].get("transcription_url")
        if not transcription_url:
            fallback = output.get("result")
            if isinstance(fallback, dict):
                transcription_url = fallback.get("transcription_url")
        if not transcription_url:
            raise RuntimeError(f"Qwen ASR 成功响应缺少 transcription_url: task_id={task_id}")

        download_response = self._request_with_retry(
            "下载 Qwen ASR 结果",
            lambda: requests.get(transcription_url, timeout=timeout),
        )
        result_data = self._read_json(download_response, "下载 Qwen ASR 结果")

        transcripts = result_data.get("transcripts")
        sentences = None
        if isinstance(transcripts, list) and transcripts and isinstance(transcripts[0], dict):
            sentences = transcripts[0].get("sentences")
        if not isinstance(sentences, list) or not sentences:
            raise ValueError("Qwen ASR 结果为空：缺少 sentences")

        segments = []
        texts = []
        for sentence in sentences:
            if not isinstance(sentence, dict):
                continue
            text = self._normalize_text(sentence.get("text"))
            if not text:
                continue
            if sentence.get("begin_time") is None or sentence.get("end_time") is None:
                raise ValueError("Qwen ASR 句子缺少时间戳")
            start = float(sentence["begin_time"]) / 1000.0
            end = float(sentence["end_time"]) / 1000.0
            segments.append(TranscriptSegment(start=start, end=end, text=text))
            texts.append(text)

        if not segments:
            raise ValueError("Qwen ASR 结果为空：所有句子文本为空")

        usage = result_data.get("usage") if isinstance(result_data.get("usage"), dict) else {}
        logger.info(
            "Qwen ASR task succeeded: task_id=%s sentences=%d input_tokens=%s output_tokens=%s",
            task_id, len(segments), usage.get("input_tokens"), usage.get("output_tokens"),
        )

        return TranscriptResult(language="zh", segments=segments, full_text="\n".join(texts))

    def _request_with_retry(self, action: str, request_func):
        """对网络错误与 429/5xx 做 2/5/10 秒有限重试。"""
        last_attempt = len(self.RETRY_DELAYS)
        for attempt in range(last_attempt + 1):
            try:
                response = request_func()
            except requests.RequestException as exc:
                if attempt == last_attempt:
                    # 不把异常原文透出，避免带签名的 OSS URL 进入日志/异常。
                    raise RuntimeError(f"{action}失败: 网络错误 {exc.__class__.__name__}") from None
            else:
                if response.status_code != 429 and not 500 <= response.status_code < 600:
                    return response
                if attempt == last_attempt:
                    return response
            time.sleep(self.RETRY_DELAYS[attempt])
        raise RuntimeError(f"{action}失败")

    @staticmethod
    def _read_json(response, action: str) -> dict:
        try:
            data = response.json()
        except ValueError:
            data = None
        if response.status_code >= 400:
            raise RuntimeError(
                f"{action}失败: HTTP {response.status_code}, "
                f"{QwenFileTransASRProvider._error_detail(data)}"
            )
        if not isinstance(data, dict):
            raise RuntimeError(f"{action}失败: 响应不是 JSON 对象")
        return data

    @staticmethod
    def _error_detail(data) -> str:
        """只提取 code/message/request_id，禁止回显请求或结果 URL。"""
        if not isinstance(data, dict):
            return "无错误详情"
        candidates = [data]
        output = data.get("output")
        if isinstance(output, dict):
            candidates.append(output)
            if isinstance(output.get("results"), list):
                candidates.extend(item for item in output["results"] if isinstance(item, dict))
        for item in candidates:
            code = item.get("code")
            message = item.get("message")
            if code or message:
                detail = f"code={code or '-'}, message={message or '-'}"
                request_id = item.get("request_id") or data.get("request_id")
                if request_id:
                    detail += f", request_id={request_id}"
                return detail
        return "无错误详情"

    @staticmethod
    def _normalize_text(value) -> str:
        text = str(value or "").strip()
        return re.sub(r"(?<=[一-鿿])\s+(?=[一-鿿])", "", text)


ASRProviderRegistry.register("qwen_filetrans", QwenFileTransASRProvider)
