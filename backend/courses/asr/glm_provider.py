import logging
import os
import subprocess
import tempfile
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

        # 1. 提取音频
        audio_wav = self._extract_audio(audio_path)
        # 2. 获取时长
        total_duration = self._get_duration(audio_wav)
        # 3. 切分
        chunk_paths = self._split_audio(audio_wav, chunk_duration, total_duration)

        # 4. 逐段转录
        all_segments: List[TranscriptSegment] = []
        full_text_parts: List[str] = []

        for idx, chunk_path in enumerate(chunk_paths):
            offset = idx * chunk_duration
            try:
                text = self._transcribe_chunk(
                    chunk_path, api_key, base_url, model, timeout
                )
                if text.strip():
                    all_segments.append(
                        TranscriptSegment(
                            start=offset,
                            end=min(offset + chunk_duration, total_duration),
                            text=text.strip(),
                        )
                    )
                    full_text_parts.append(text)
            except Exception as e:
                logger.warning("GLM ASR chunk %d failed: %s", idx, e)
            finally:
                try:
                    os.remove(chunk_path)
                except OSError:
                    pass

        # 5. 清理
        try:
            os.remove(audio_wav)
        except OSError:
            pass

        return TranscriptResult(
            language="zh",
            segments=all_segments,
            full_text="".join(full_text_parts),
        )

    # ── ffmpeg 工具方法 ─────────────────────────────────────────────

    def _extract_audio(self, video_path: str) -> str:
        """ffmpeg: 视频 → 16kHz 单声道 PCM wav"""
        fd, tmp_path = tempfile.mkstemp(suffix=".wav", prefix="glm_audio_")
        os.close(fd)
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", video_path,
                "-vn",
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                tmp_path,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return tmp_path

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

    def _split_audio(self, audio_path: str, chunk_duration: int, total_duration: float) -> List[str]:
        chunk_paths = []
        num_chunks = int(total_duration / chunk_duration) + 1
        for i in range(num_chunks):
            start = i * chunk_duration
            fd, chunk_path = tempfile.mkstemp(suffix=".wav", prefix=f"glm_chunk_{i}_")
            os.close(fd)
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", audio_path,
                    "-ss", str(start),
                    "-t", str(chunk_duration),
                    "-acodec", "copy",
                    chunk_path,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            chunk_paths.append(chunk_path)
        return chunk_paths

    # ── API 调用 ────────────────────────────────────────────────────

    def _transcribe_chunk(
        self,
        chunk_path: str,
        api_key: str,
        base_url: str,
        model: str,
        timeout: int,
    ) -> str:
        """调用 GLM-ASR-2512，返回纯文本。"""
        url = f"{base_url.rstrip('/')}/audio/transcriptions"

        with open(chunk_path, "rb") as f:
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": f},
                data={"model": model},
                timeout=timeout,
            )
        response.raise_for_status()
        data = response.json()
        # GLM ASR 响应格式：{"text": "转录文本", "id": "...", "model": "..."}
        return data.get("text", "")


ASRProviderRegistry.register("glm_asr", GLMChunkedASRProvider)
