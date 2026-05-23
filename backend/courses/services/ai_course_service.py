import json
import logging
import random
from typing import Any, Dict, List, Optional

from ai_engine.ai_service import AIService
from ai_engine.tools import OUTLINE_ITEMS_SCHEMA, QUESTION_LIST_SCHEMA
from courses.asr import ASRProviderRegistry
from courses.models import (
    Course,
    CourseOutline,
    CourseVideoQuestion,
    OutlineItem,
    TranscriptSegment,
    VideoTranscript,
)

logger = logging.getLogger(__name__)


class AICourseService:
    """编排课程视频的 AI 转录 + 大纲 + 出题流水线。"""

    def __init__(self, ai_service_cls=None):
        self.ai = ai_service_cls or AIService

    # ── 转录 ──────────────────────────────────────────────────────────

    def transcribe_video(self, course: Course) -> VideoTranscript:
        transcript, _ = VideoTranscript.objects.get_or_create(course=course)
        transcript.asr_status = 'processing'
        transcript.save(update_fields=['asr_status', 'updated_at'])

        try:
            from django.conf import settings
            provider = ASRProviderRegistry.get_default_provider()
            provider_name = getattr(settings, 'ASR_DEFAULT_PROVIDER', 'dummy')
            result = provider.transcribe(course.video_file.path)

            transcript.full_text = result.full_text
            transcript.language = result.language
            transcript.asr_provider = provider_name
            transcript.asr_status = 'completed'
            transcript.save()

            transcript.segments.all().delete()
            TranscriptSegment.objects.bulk_create([
                TranscriptSegment(
                    transcript=transcript,
                    start_time=seg.start,
                    end_time=seg.end,
                    text=seg.text,
                    index=idx,
                )
                for idx, seg in enumerate(result.segments)
            ])

            self._schedule_outline_generation(course.id)
            return transcript
        except Exception as e:
            transcript.asr_status = 'failed'
            transcript.error_message = str(e)[:500]
            transcript.save(update_fields=['asr_status', 'error_message', 'updated_at'])
            logger.exception("ASR failed for course %s", course.id)
            raise

    def _schedule_outline_generation(self, course_id: int) -> None:
        from courses.services.task_dispatcher import dispatch_outline_generation
        dispatch_outline_generation(course_id)

    def _schedule_question_generation(self, course_id: int) -> None:
        import threading
        def _run():
            try:
                from courses.models import Course
                course = Course.objects.get(pk=course_id)
                self.generate_questions_from_transcript(course)
            except Exception:
                logger.exception("Question generation failed for course %s", course_id)
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    # ── 大纲生成 ──────────────────────────────────────────────────────

    @staticmethod
    def _format_transcript_with_timestamps(transcript) -> str:
        """将带时间戳的转录分段格式化为 AI 可读取的文本。

        输出格式: [MM:SS] 文本内容
        每个分段独立一行，AI 可以直接按行引用时间戳。
        """
        segments = transcript.segments.order_by('index')
        lines: List[str] = []
        for seg in segments:
            m = int(seg.start_time // 60)
            s = int(seg.start_time % 60)
            lines.append(f"[{m:02d}:{s:02d}] {seg.text}")
        return "\n".join(lines)

    def generate_outline(self, course_id: int) -> List[Dict[str, Any]]:
        course = Course.objects.get(pk=course_id)
        transcript = getattr(course, 'transcript', None)
        if not transcript or transcript.asr_status != 'completed':
            raise ValueError("转录不可用或尚未完成")

        outline, _ = CourseOutline.objects.get_or_create(course=course)
        outline.status = 'generating'
        outline.save(update_fields=['status', 'updated_at'])

        try:
            # 构建带时间戳的分段文本，让 AI 能拿到真实的时序信息
            transcript_with_timestamps = self._format_transcript_with_timestamps(transcript)
            items = self._request_outline_items(transcript_with_timestamps)
            outline.items.all().delete()
            OutlineItem.objects.bulk_create([
                OutlineItem(
                    outline=outline,
                    title=item.get('title') or item.get('chapter') or '',
                    timestamp=float(
                        item.get('timestamp_seconds')
                        or item.get('timestamp')
                        or item.get('time')
                        or item.get('start')
                        or 0
                    ),
                    description=item.get('description') or item.get('summary') or '',
                    index=idx,
                )
                for idx, item in enumerate(items)
            ])
            outline.status = 'completed'
            outline.save(update_fields=['status', 'updated_at'])

            # 大纲完成后自动触发出题
            self._schedule_question_generation(course_id)

            return items
        except Exception as e:
            outline.status = 'failed'
            outline.save(update_fields=['status', 'updated_at'])
            logger.exception("Outline generation failed for course %s", course_id)
            raise

    def _request_outline_items(self, transcript_text: str) -> List[Dict[str, Any]]:
        template = self.ai.get_template('courses', 'transcript_outline_prompt.txt') or ''
        prompt = self.ai.format_template(template, transcript_text=transcript_text)

        result = self.ai.structured_output(
            system_prompt="",
            user_prompt=prompt,
            schema=OUTLINE_ITEMS_SCHEMA,
            tool_name="submit_outline",
            tool_description="提交课程大纲条目",
            temperature=0.3,
            max_tokens=4096,
            raise_on_error=True,
            operation='courses.generate_outline',
        )

        if isinstance(result, list):
            return result

        # fallback to old extract_json path
        response = self.ai.call_ai(
            messages=[
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=4096,
            raise_on_error=True,
            operation='courses.generate_outline',
        )
        content = self.ai.extract_content(response)
        parsed = self.ai.extract_json(content)

        if not isinstance(parsed, list):
            raise ValueError(f"大纲结果不是数组: {type(parsed)}")
        return parsed

    # ── 题目生成 ──────────────────────────────────────────────────────

    def generate_questions_from_transcript(
        self,
        course: Course,
        num_obj: int = 3,
        num_short: int = 1,
        num_essay: int = 1,
    ) -> List[Dict[str, Any]]:
        transcript = getattr(course, 'transcript', None)
        if not transcript or not transcript.full_text:
            raise ValueError("转录不可用")

        # 构建知识点上下文
        kp_context = ""
        kp_id = course.knowledge_point_id
        if kp_id:
            from quizzes.models import KnowledgePoint
            kp = KnowledgePoint.objects.filter(id=kp_id).first()
            if kp:
                kp_context = f"\n\n【关联知识点】{kp.name}\n知识范围说明：{kp.description or '请基于课程视频内容判断相关考点'}\n"

        prompt = (
            f"你是学科命题专家。请根据以下课程视频的文字记录，"
            f"生成 {num_obj} 道单项选择题、{num_short} 道简答题"
            f"{'、' + str(num_essay) + '道论述题' if num_essay else ''}。"
            f"题目应紧扣视频讲解的核心概念和逻辑推演。"
            f"{kp_context}"
            f"\n\n视频记录：\n{transcript.full_text}"
        )

        try:
            result = self.ai.structured_output(
                system_prompt=(
                    "你是学科出题专家。根据视频内容出题，调用 submit_questions 提交题目列表。"
                ),
                user_prompt=prompt,
                schema=QUESTION_LIST_SCHEMA,
                tool_name="submit_questions",
                tool_description="提交生成的题目列表",
                temperature=0.3,
                max_tokens=4096,
                raise_on_error=True,
                operation="courses.generate_questions",
            )
            if isinstance(result, list):
                questions = result
            else:
                # fallback to old extract_json path
                response = self.ai.simple_chat(
                    system_prompt=(
                        "你是学科出题专家。只输出 JSON 数组，每个元素包含 "
                        "q_type(objective/subjective)、subjective_type(noun/short/essay/calculate)、"
                        "question、options(客观题 ABCD 选项)、answer、grading_points、"
                        "difficulty_level(entry/easy/normal/hard/extreme) 字段。"
                    ),
                    user_prompt=prompt,
                    temperature=0.3,
                    max_tokens=4096,
                    raise_on_error=True,
                    operation="courses.generate_questions",
                )
                content = self.ai.extract_content(response)
                parsed = self.ai.extract_json(content)
                if isinstance(parsed, list):
                    questions = parsed
                else:
                    questions = []
        except Exception:
            logger.exception(
                "AI question generation failed for course %s, will rely on global fallback",
                course.id,
            )
            return []

        for q_data in questions:
            CourseVideoQuestion.objects.create(
                course=course,
                question_data=q_data,
            )

        return questions

    def get_or_generate_question_data(
        self, course: Course, count: int = 5
    ) -> List[Dict[str, Any]]:
        """返回题目数据（不入库）。优先用缓存，否则 AI 生成。"""
        cached = list(
            CourseVideoQuestion.objects.filter(
                course=course, is_active=True
            ).values_list('question_data', flat=True)[:count]
        )
        if len(cached) >= count:
            return cached

        generated = self.generate_questions_from_transcript(course)
        return [
            vq.question_data
            for vq in CourseVideoQuestion.objects.filter(
                course=course, is_active=True
            )[:count]
        ] if generated else []
