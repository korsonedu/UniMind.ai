"""
小米 MiMo-V2.5-ASR 提供者

配置示例（settings.ASR_PROVIDER_CONFIG）：
    "mimo_asr": {
        "api_key": "sk-xxx",
        "base_url": "https://api.xiaomimimo.com/v1",
        "model": "mimo-v2.5-asr",
        "language": "zh",
        "timeout": 120,
    }
"""

import logging
import requests
from .base import ASRProvider, ASRProviderRegistry, TranscriptResult, TranscriptSegment

logger = logging.getLogger(__name__)


class MiMoASRProvider(ASRProvider):
    """小米 MiMo-V2.5-ASR 提供者
    
    使用小米MiMo开放平台的ASR API，支持OpenAI兼容格式。
    """

    def transcribe(self, audio_path: str) -> TranscriptResult:
        api_key = self.config.get("api_key", "")
        base_url = self.config.get("base_url", "https://api.xiaomimimo.com/v1")
        model = self.config.get("model", "mimo-v2.5-asr")
        language = self.config.get("language", "zh")
        timeout = self.config.get("timeout", 120)

        url = f"{base_url.rstrip('/')}/audio/transcriptions"

        with open(audio_path, "rb") as f:
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": f},
                data={
                    "model": model,
                    "language": language,
                    "response_format": "verbose_json",
                },
                timeout=timeout,
            )
        response.raise_for_status()
        data = response.json()

        segments = []
        for seg in data.get("segments", []):
            segments.append(
                TranscriptSegment(
                    start=float(seg.get("start", 0)),
                    end=float(seg.get("end", 0)),
                    text=seg.get("text", ""),
                )
            )

        return TranscriptResult(
            language=data.get("language", language),
            segments=segments,
            full_text=data.get("text", ""),
        )


ASRProviderRegistry.register("mimo_asr", MiMoASRProvider)
