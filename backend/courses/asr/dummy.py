import time
from .base import ASRProvider, ASRProviderRegistry, TranscriptResult, TranscriptSegment


class DummyASRProvider(ASRProvider):
    """占位 ASR 提供者——用户替换为真实 API 后即可启用语音转文字。

    接入方式：
    1. 在 settings.ASR_PROVIDER_CONFIG 中添加你的 provider 配置
    2. 设置 ASR_DEFAULT_PROVIDER 环境变量指向你的 provider
    """

    def transcribe(self, audio_path: str) -> TranscriptResult:
        time.sleep(0.1)
        return TranscriptResult(
            language="zh",
            segments=[
                TranscriptSegment(
                    start=0.0,
                    end=0.0,
                    text="[占位文本：请配置 ASR 提供者以启用语音转文字功能]",
                )
            ],
            full_text="[占位文本：请配置 ASR 提供者以启用语音转文字功能]",
        )


ASRProviderRegistry.register("dummy", DummyASRProvider)
