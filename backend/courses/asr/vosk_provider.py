import logging
import os
import subprocess
import tempfile
import json
from typing import List

from .base import ASRProvider, ASRProviderRegistry, TranscriptResult, TranscriptSegment

logger = logging.getLogger(__name__)


class VoskASRProvider(ASRProvider):
    """Vosk 离线语音识别提供者。

    完全本地运行，无需联网，免费，支持中文，返回逐词时间戳。

    前置准备：
    1. pip install vosk
    2. 下载中文模型：
       wget https://alphacephei.com/vosk/models/vosk-model-cn-0.22.zip
       unzip vosk-model-cn-0.22.zip -d /path/to/models/
    3. 配置模型路径（环境变量或 settings）

    配置示例：
        ASR_DEFAULT_PROVIDER=vosk
        VOSK_MODEL_PATH=/path/to/vosk-model-cn-0.22
    """

    def transcribe(self, audio_path: str) -> TranscriptResult:
        try:
            import vosk
        except ImportError:
            raise ImportError(
                "vosk 未安装。请运行: pip install vosk\n"
                "然后下载中文模型: https://alphacephei.com/vosk/models"
            )

        model_path = self.config.get("model_path", "")
        if not model_path:
            raise ValueError("VOSK_MODEL_PATH 未设置，请指定模型路径")

        if not os.path.isdir(model_path):
            raise ValueError(f"Vosk 模型路径不存在: {model_path}")

        # 1. 提取音频为 16kHz 单声道 wav
        audio_wav = self._extract_audio(audio_path)

        try:
            # 2. 加载模型 + 识别
            model = vosk.Model(model_path)
            rec = vosk.KaldiRecognizer(model, 16000)

            with open(audio_wav, "rb") as f:
                while True:
                    data = f.read(4000)
                    if not data:
                        break
                    rec.AcceptWaveform(data)

            result = json.loads(rec.FinalResult())
        finally:
            try:
                os.remove(audio_wav)
            except OSError:
                pass

        # 3. 解析结果
        full_text = result.get("text", "")
        segments = self._build_segments(result, full_text)

        return TranscriptResult(
            language="zh",
            segments=segments,
            full_text=full_text,
        )

    def _build_segments(self, result: dict, full_text: str) -> List[TranscriptSegment]:
        """从 Vosk 结果构建分句段落。有逐词时间戳时精确分句，否则按标点分句均分时长。"""
        words = result.get("result", [])

        if words:
            return self._segments_from_words(words)

        # 无逐词时间戳 → 按标点分句，估算时间分布
        return self._segments_from_text(full_text)

    def _segments_from_words(self, words: list) -> List[TranscriptSegment]:
        segments: List[TranscriptSegment] = []
        current_start = words[0].get("start", 0)
        current_end = words[0].get("end", 0)
        current_words: List[str] = []

        for w in words:
            w_start = w.get("start", 0)
            w_end = w.get("end", 0)
            word_text = w.get("word", "")

            if current_words and w_start - current_end > 0.8:
                segments.append(TranscriptSegment(
                    start=current_start,
                    end=current_end,
                    text="".join(current_words),
                ))
                current_start = w_start
                current_words = []

            current_end = w_end
            current_words.append(word_text)

        if current_words:
            segments.append(TranscriptSegment(
                start=current_start,
                end=current_end,
                text="".join(current_words),
            ))
        return segments

    def _segments_from_text(self, full_text: str) -> List[TranscriptSegment]:
        """无时间戳时：按标点分句，每句约 3 秒均匀分布（字幕可读性优先）。"""
        import re
        sentences = re.split(r'(?<=[。！？，,\.!\?])', full_text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences:
            return []

        # 假设平均语速约 4 字/秒，每句至少 1 秒
        total_duration = max(len(full_text) / 4.0, len(sentences))
        time_per_char = total_duration / max(len(full_text), 1)

        segments = []
        offset = 0.0
        for s in sentences:
            dur = max(len(s) * time_per_char, 1.0)
            segments.append(TranscriptSegment(
                start=offset,
                end=offset + dur,
                text=s,
            ))
            offset += dur
        return segments

    def _extract_audio(self, video_path: str) -> str:
        """ffmpeg: 视频 → 16kHz 单声道 PCM wav"""
        fd, tmp_path = tempfile.mkstemp(suffix=".wav", prefix="vosk_audio_")
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


ASRProviderRegistry.register("vosk", VoskASRProvider)
