"""Qwen 文件转写与字幕人工修订保护测试。全部使用 mock，不访问真实网络。"""

from unittest.mock import MagicMock, patch

from django.core.files.storage import Storage
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from courses.asr import ASRProviderRegistry, TranscriptResult, TranscriptSegment
from courses.asr.qwen_filetrans_provider import QwenFileTransASRProvider
from courses.services.ai_course_service import AICourseService


class _RemoteStorage(Storage):
    def url(self, name):
        return f"https://oss.example.com/media/{name}"

    def path(self, name):
        raise NotImplementedError


class _LocalStorage(Storage):
    def url(self, name):
        return f"/media/{name}"


def _result():
    return TranscriptResult(
        segments=[
            TranscriptSegment(start=0.0, end=1.5, text="第一句"),
            TranscriptSegment(start=1.5, end=3.0, text="第二句"),
        ],
        full_text="第一句\n第二句",
    )


class _FakeURLProvider:
    supports_url = True

    def __init__(self, result=None):
        self.result = result or _result()
        self.urls = []

    def transcribe_url(self, url):
        self.urls.append(url)
        return self.result


class _ManualEditDuringRunProvider:
    supports_url = True

    def __init__(self, transcript_id):
        self.transcript_id = transcript_id

    def transcribe_url(self, url):
        from courses.models import VideoTranscript

        VideoTranscript.objects.filter(pk=self.transcript_id).update(
            is_manually_edited=True,
            manual_edited_at=timezone.now(),
            full_text="运行中人工修订",
            updated_at=timezone.now(),
        )
        return _result()


class QwenFileTransProviderTests(SimpleTestCase):
    CONFIG = {
        "api_key": "test-key",
        "base_url": "https://qwen.test/api/v1",
        "model": "qwen-test-model",
        "timeout": 5,
        "poll_interval": 0.01,
        "max_wait": 60,
    }
    AUDIO_URL = "https://oss.example.com/media/a.mp4?signature=secret"

    @staticmethod
    def _response(payload, status_code=200):
        response = MagicMock()
        response.status_code = status_code
        response.json.return_value = payload
        return response

    @patch("courses.asr.qwen_filetrans_provider.time.sleep")
    @patch("courses.asr.qwen_filetrans_provider.requests.get")
    @patch("courses.asr.qwen_filetrans_provider.requests.post")
    def test_submit_poll_download_and_convert_milliseconds(self, mock_post, mock_get, mock_sleep):
        mock_post.return_value = self._response(
            {"output": {"task_id": "task-1", "task_status": "PENDING"}}
        )
        mock_get.side_effect = [
            self._response({"output": {"task_status": "RUNNING"}}),
            self._response({
                "output": {
                    "task_status": "SUCCEEDED",
                    "results": [{
                        "subtask_status": "SUCCEEDED",
                        "transcription_url": "https://result.example/signed.json",
                    }],
                },
            }),
            self._response({
                "transcripts": [{
                    "sentences": [
                        {"begin_time": 0, "end_time": 1250, "text": "  你好  世界  ", "sentence_id": 1},
                        {"begin_time": 1250, "end_time": 3400, "text": "hello world", "sentence_id": 2},
                    ],
                }],
                "usage": {"input_tokens": 1617, "output_tokens": 363},
            }),
        ]

        provider = QwenFileTransASRProvider(self.CONFIG)
        with self.assertLogs("courses.asr.qwen_filetrans_provider", level="INFO") as logs:
            result = provider.transcribe_url(self.AUDIO_URL)

        post_args, post_kwargs = mock_post.call_args
        self.assertEqual(post_args[0], "https://qwen.test/api/v1/services/audio/asr/transcription")
        self.assertEqual(post_kwargs["headers"]["X-DashScope-Async"], "enable")
        self.assertEqual(post_kwargs["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(post_kwargs["json"], {
            "model": "qwen-test-model",
            "input": {"file_urls": [self.AUDIO_URL]},
            "parameters": {},
        })
        self.assertEqual(mock_get.call_args_list[0].args[0], "https://qwen.test/api/v1/tasks/task-1")

        self.assertEqual([(s.start, s.end) for s in result.segments], [(0.0, 1.25), (1.25, 3.4)])
        self.assertEqual([s.text for s in result.segments], ["你好世界", "hello world"])
        self.assertEqual(result.full_text, "你好世界\nhello world")

        log_output = "\n".join(logs.output)
        self.assertIn("task-1", log_output)
        self.assertIn("1617", log_output)
        self.assertNotIn("oss.example", log_output)
        self.assertNotIn("result.example", log_output)

    @patch("courses.asr.qwen_filetrans_provider.time.sleep")
    @patch("courses.asr.qwen_filetrans_provider.requests.get")
    @patch("courses.asr.qwen_filetrans_provider.requests.post")
    def test_empty_sentences_raise(self, mock_post, mock_get, mock_sleep):
        mock_post.return_value = self._response({"output": {"task_id": "task-empty"}})
        mock_get.side_effect = [
            self._response({
                "output": {
                    "task_status": "SUCCEEDED",
                    "results": [{"transcription_url": "https://result.example/empty.json"}],
                },
            }),
            self._response({"transcripts": [{"sentences": []}]}),
        ]

        provider = QwenFileTransASRProvider(self.CONFIG)
        with self.assertRaises(ValueError) as ctx:
            provider.transcribe_url(self.AUDIO_URL)
        self.assertIn("为空", str(ctx.exception))
        self.assertNotIn("result.example", str(ctx.exception))

    @patch("courses.asr.qwen_filetrans_provider.time.sleep")
    @patch("courses.asr.qwen_filetrans_provider.requests.get")
    @patch("courses.asr.qwen_filetrans_provider.requests.post")
    def test_failed_task_reports_api_code_and_message(self, mock_post, mock_get, mock_sleep):
        mock_post.return_value = self._response({"output": {"task_id": "task-2"}})
        mock_get.return_value = self._response({
            "output": {
                "task_status": "FAILED",
                "results": [{"code": "InvalidFile", "message": "download failed"}],
            },
        })

        provider = QwenFileTransASRProvider(self.CONFIG)
        with self.assertRaises(RuntimeError) as ctx:
            provider.transcribe_url(self.AUDIO_URL)
        self.assertIn("InvalidFile", str(ctx.exception))
        self.assertIn("download failed", str(ctx.exception))
        self.assertEqual(mock_get.call_count, 1)

    @patch("courses.asr.qwen_filetrans_provider.time.sleep")
    @patch("courses.asr.qwen_filetrans_provider.requests.get")
    @patch("courses.asr.qwen_filetrans_provider.requests.post")
    def test_failed_subtask_is_rejected_before_download(self, mock_post, mock_get, mock_sleep):
        mock_post.return_value = self._response({"output": {"task_id": "task-3"}})
        mock_get.return_value = self._response({
            "output": {
                "task_status": "SUCCEEDED",
                "results": [{
                    "subtask_status": "FAILED",
                    "code": "InvalidURL",
                    "message": "cannot fetch audio",
                    "transcription_url": "https://result.example/not-used.json",
                }],
            },
        })

        provider = QwenFileTransASRProvider(self.CONFIG)
        with self.assertRaises(RuntimeError) as ctx:
            provider.transcribe_url(self.AUDIO_URL)
        self.assertIn("InvalidURL", str(ctx.exception))
        self.assertEqual(mock_get.call_count, 1)

    @patch("courses.asr.qwen_filetrans_provider.time.sleep")
    @patch("courses.asr.qwen_filetrans_provider.requests.get")
    @patch("courses.asr.qwen_filetrans_provider.requests.post")
    def test_submit_retries_on_429(self, mock_post, mock_get, mock_sleep):
        mock_post.side_effect = [
            self._response({"code": "Throttling", "message": "too many requests"}, status_code=429),
            self._response({"output": {"task_id": "task-4"}}),
        ]
        mock_get.side_effect = [
            self._response({
                "output": {
                    "task_status": "SUCCEEDED",
                    "results": [{"transcription_url": "https://result.example/ok.json"}],
                },
            }),
            self._response({
                "transcripts": [{"sentences": [{"begin_time": 0, "end_time": 1000, "text": "重试成功"}]}],
            }),
        ]

        provider = QwenFileTransASRProvider(self.CONFIG)
        result = provider.transcribe_url(self.AUDIO_URL)

        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_any_call(2)
        self.assertEqual(result.full_text, "重试成功")


class TranscriptManualEditProtectionTests(TestCase):
    def setUp(self):
        from courses.models import Course, VideoTranscript

        self.course = Course.objects.create(title="测试课程", video_file="videos/lesson.mp4")
        self.course.video_file.storage = _RemoteStorage()
        self.transcript = VideoTranscript.objects.create(course=self.course)

    def test_manual_edit_is_not_overwritten_by_default(self):
        from courses.models import VideoTranscript

        VideoTranscript.objects.filter(pk=self.transcript.pk).update(
            is_manually_edited=True,
            manual_edited_at=timezone.now(),
            full_text="人工修订",
            asr_status="completed",
        )
        provider = _FakeURLProvider()

        with patch.object(ASRProviderRegistry, "get_default_provider", return_value=provider):
            transcript = AICourseService().transcribe_video(self.course)

        transcript.refresh_from_db()
        self.assertEqual(provider.urls, [])
        self.assertEqual(transcript.full_text, "人工修订")
        self.assertEqual(transcript.asr_status, "completed")

    def test_force_overwrites_manual_edit_and_resets_flags(self):
        from courses.models import VideoTranscript

        VideoTranscript.objects.filter(pk=self.transcript.pk).update(
            is_manually_edited=True,
            manual_edited_at=timezone.now(),
            full_text="人工修订",
            asr_status="completed",
            revision=3,
        )
        provider = _FakeURLProvider()

        with patch.object(ASRProviderRegistry, "get_default_provider", return_value=provider):
            transcript = AICourseService().transcribe_video(self.course, force=True)

        transcript.refresh_from_db()
        self.assertEqual(provider.urls, ["https://oss.example.com/media/videos/lesson.mp4"])
        self.assertEqual(transcript.asr_status, "completed")
        self.assertFalse(transcript.is_manually_edited)
        self.assertIsNone(transcript.manual_edited_at)
        self.assertIsNone(transcript.manual_edited_by)
        self.assertEqual(transcript.revision, 4)
        self.assertEqual(transcript.full_text, "第一句\n第二句")
        self.assertEqual(
            list(transcript.segments.order_by("index").values_list("text", flat=True)),
            ["第一句", "第二句"],
        )

    def test_manual_edit_during_asr_is_not_overwritten(self):
        provider = _ManualEditDuringRunProvider(self.transcript.pk)

        with patch.object(ASRProviderRegistry, "get_default_provider", return_value=provider):
            transcript = AICourseService().transcribe_video(self.course)

        transcript.refresh_from_db()
        self.assertEqual(transcript.full_text, "运行中人工修订")
        self.assertTrue(transcript.is_manually_edited)
        self.assertEqual(transcript.segments.count(), 0)

    def test_local_non_http_url_is_rejected(self):
        from courses.models import Course

        course = Course.objects.create(title="本地课程", video_file="videos/local.mp4")
        course.video_file.storage = _LocalStorage()
        provider = _FakeURLProvider()

        with patch.object(ASRProviderRegistry, "get_default_provider", return_value=provider):
            with self.assertLogs("courses.services.ai_course_service", level="ERROR"):
                with self.assertRaises(ValueError) as ctx:
                    AICourseService().transcribe_video(course)

        self.assertIn("需要配置 OSS", str(ctx.exception))
        self.assertEqual(provider.urls, [])
