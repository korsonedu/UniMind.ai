import logging
from celery import shared_task

logger = logging.getLogger(__name__)


# 长视频转录实测：56 分钟视频 ≈ 428s（314 chunks × GLM ASR 串行调用）。
# 660s 硬超时会导致 78 分钟视频卡边被杀（SIGKILL 无清理，transcript 永久卡 processing）。
@shared_task(bind=True, max_retries=2, default_retry_delay=30, soft_time_limit=5100, time_limit=5400)
def transcribe_course_task(self, course_id: int):
    from courses.models import Course
    from courses.services.ai_course_service import AICourseService

    course = Course.objects.filter(id=course_id).first()
    if not course:
        return None
    try:
        AICourseService().transcribe_video(course)
    except Exception as exc:
        logger.exception("Celery transcription failed for course %s", course_id)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=30, soft_time_limit=60, time_limit=90)
def extract_cover_task(self, course_id: int):
    import os, subprocess, tempfile, uuid
    from django.core.files import File
    from courses.models import Course

    course = Course.objects.filter(id=course_id).first()
    if not course or not course.video_file or course.cover_image:
        return None
    try:
        try:
            video_src = course.video_file.path
        except NotImplementedError:
            video_src = course.video_file.url

        tmp = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
        tmp.close()
        result = subprocess.run([
            'ffmpeg', '-ss', '0', '-i', video_src,
            '-vframes', '1', '-q:v', '2', '-y', tmp.name,
        ], capture_output=True, timeout=30)
        if result.returncode != 0 or not os.path.isfile(tmp.name) or os.path.getsize(tmp.name) == 0:
            return None
        try:
            with open(tmp.name, 'rb') as f:
                filename = f'cover_{course.id}_{uuid.uuid4().hex[:8]}.jpg'
                course.cover_image.save(filename, File(f), save=True)
        finally:
            try:
                os.remove(tmp.name)
            except OSError:
                pass
    except Exception as exc:
        logger.exception('Celery cover extraction failed for course %s', course_id)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=30, soft_time_limit=300, time_limit=600)
def generate_outline_task(self, course_id: int):
    from courses.services.ai_course_service import AICourseService

    try:
        AICourseService().generate_outline(course_id)
    except Exception as exc:
        logger.exception("Celery outline generation failed for course %s", course_id)
        raise self.retry(exc=exc)
