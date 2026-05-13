from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass
class TranscriptResult:
    language: str = "zh"
    segments: List[TranscriptSegment] = field(default_factory=list)
    full_text: str = ""


class ASRProvider(ABC):
    """可插拔 ASR 提供者抽象基类。

    用户只需实现 transcribe() 方法，返回 TranscriptResult。
    配置通过 settings.ASR_PROVIDER_CONFIG[provider_name] 传入。
    """

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}

    @abstractmethod
    def transcribe(self, audio_path: str) -> TranscriptResult:
        """对音频/视频文件执行语音识别，返回带时间戳的分段结果。"""
        ...


class ASRProviderRegistry:
    """ASR 提供者注册表。

    用法：
        ASRProviderRegistry.register('whisper', WhisperProvider)
        provider = ASRProviderRegistry.get_provider('whisper', config)
    """

    _providers: dict = {}

    @classmethod
    def register(cls, name: str, provider_cls: type) -> None:
        cls._providers[name] = provider_cls

    @classmethod
    def get_provider(cls, name: str, config: Optional[dict] = None) -> ASRProvider:
        provider_cls = cls._providers.get(name)
        if not provider_cls:
            raise ValueError(f"未知的 ASR 提供者: {name}")
        return provider_cls(config)

    @classmethod
    def get_default_provider(cls) -> ASRProvider:
        from django.conf import settings

        name = getattr(settings, "ASR_DEFAULT_PROVIDER", "dummy")
        config = getattr(settings, "ASR_PROVIDER_CONFIG", {}).get(name, {})
        return cls.get_provider(name, config)
