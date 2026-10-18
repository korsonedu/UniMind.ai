import glob
import logging
import math
import os
import subprocess
import tempfile
import time
import requests
from typing import List

from .base import ASRProvider, ASRProviderRegistry, TranscriptResult, TranscriptSegment

logger = logging.getLogger(__name__)


class GLMChunkedASRProvider(ASRProvider):
    """智谱 GLM-ASR-2512 语音转文字提供者。

    API 限制：文件 ≤ 25MB、时长 ≤ 30 秒。
    此提供者自动用 ffmpeg 切分 + 逐段调用 + 按时间戳拼接。

    API 文档：https://docs.bigmodel.cn/cn/guide/models/sound-and-video/glm-asr-2512

    配置示例（settings.ASR_PROVIDER_CONFIG / 环境变量）：
        ASR_DEFAULT_PROVIDER=glm_asr
        GLM_ASR_API_KEY=xxx
    """

    DEFAULT_CHUNK_DURATION = 15  # 秒，更细粒度的时间戳

    def transcribe(self, audio_path: str) -> TranscriptResult:
        api_key = self.config.get("api_key", "")
        base_url = self.config.get("base_url", "https://open.bigmodel.cn/api/paas/v4")
        model = self.config.get("model", "glm-asr-2512")
        timeout = self.config.get("timeout", 60)
        chunk_duration = self.config.get("chunk_duration", self.DEFAULT_CHUNK_DURATION)

        if not api_key:
            raise ValueError("GLM ASR 需要 api_key，请设置 GLM_ASR_API_KEY 环境变量")

        chunk_duration = float(chunk_duration)
        if not math.isfinite(chunk_duration) or not 0 < chunk_duration <= 30:
            raise ValueError("ASR 分段时长须在 0 到 30 秒之间")

        # 工作目录覆盖提取、切分、请求失败路径，整段成功后才返回结果。
        with tempfile.TemporaryDirectory(prefix="glm_asr_") as work_dir:
            audio_wav = os.path.join(work_dir, "audio.wav")
            self._extract_audio(audio_path, audio_wav)
            total_duration = self._get_duration(audio_wav)
            chunk_paths = self._split_audio(audio_wav, chunk_duration)
            if not chunk_paths:
                raise ValueError("ASR 音频切分结果为空")

            all_segments: List[TranscriptSegment] = []
            full_text_parts: List[str] = []
            for idx, chunk_path in enumerate(chunk_paths):
                offset = idx * chunk_duration
                # 请求异常直接向上抛出，让任务重试；成功返回的空文本才表示静音。
                text = self._transcribe_chunk(
                    chunk_path, api_key, base_url, model, timeout
                ).strip()
                if text:
                    all_segments.append(TranscriptSegment(
                        start=offset,
                        end=min(offset + chunk_duration, total_duration),
                        text=text,
                    ))
                    full_text_parts.append(text)
                os.remove(chunk_path)

            return TranscriptResult(
                language="zh",
                segments=all_segments,
                full_text="".join(full_text_parts),
            )

    # ── ffmpeg 工具方法 ─────────────────────────────────────────────

    def _extract_audio(self, video_path: str, output_path: str) -> None:
        """ffmpeg: 视频 → 16kHz 单声道 PCM wav"""
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", video_path, "-vn",
                "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                output_path,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _get_duration(self, audio_path: str) -> float:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(result.stdout.strip())

    def _split_audio(self, audio_path: str, chunk_duration: float) -> List[str]:
        output_pattern = os.path.join(os.path.dirname(audio_path), "chunk_%06d.wav")
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", audio_path, "-acodec", "copy",
                "-f", "segment", "-segment_time", str(chunk_duration),
                "-reset_timestamps", "1", output_pattern,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return sorted(glob.glob(os.path.join(os.path.dirname(audio_path), "chunk_*.wav")))

    # ── API 调用 ────────────────────────────────────────────────────

    def _transcribe_chunk(
        self,
        chunk_path: str,
        api_key: str,
        base_url: str,
        model: str,
        timeout: int,
    ) -> str:
        """调用 GLM-ASR-2512，返回纯文本。429/5xx 指数退避重试。

        长视频 = 200-300 次连续调用，双任务并发曾触发 GLM 限流，
        所有 chunk 失败后空结果覆盖了已有好数据。
        """
        url = f"{base_url.rstrip('/')}/audio/transcriptions"
        last_error: Exception | None = None

        for attempt in range(4):
            try:
                with open(chunk_path, "rb") as f:
                    response = requests.post(
                        url,
                        headers={"Authorization": f"Bearer {api_key}"},
                        files={"file": f},
                        data={"model": model},
                        timeout=timeout,
                    )
            except requests.RequestException as e:
                last_error = e
            else:
                if response.status_code in (429, 500, 502, 503):
                    last_error = Exception(f"HTTP {response.status_code}")
                else:
                    response.raise_for_status()
                    data = response.json()
                    # GLM ASR 响应格式：{"text": "转录文本", "id": "...", "model": "..."}
                    text = data.get("text")
                    if not isinstance(text, str):
                        raise ValueError("GLM ASR 响应缺少文本字段")
                    return text
            if attempt < 3:
                time.sleep(10 * (2 ** attempt))  # 10/20/40s

        raise last_error or Exception("GLM ASR chunk failed")


ASRProviderRegistry.register("glm_asr", GLMChunkedASRProvider)
