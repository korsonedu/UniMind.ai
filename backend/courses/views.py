import json
import logging
import os
import subprocess
import tempfile
import threading
import uuid

from django.conf import settings
from django.core.files import File
from django.utils.decorators import method_decorator
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import generics, permissions
from users.permissions import IsAdmin, HasQuota

from .models import Course, Album, StartupMaterial, VideoProgress

from core.utils import apply_institution_filter


def _get_course_for_user(pk, user, request=None):
    """按机构隔离获取课程，无权限返回 None。"""
    qs = apply_institution_filter(Course.objects.all(), user, request)
    return qs.filter(pk=pk).first()
from .serializers import CourseSerializer, AlbumSerializer, StartupMaterialSerializer
from users.views import IsMember
from quizzes.utils import safe_int as _safe_int
from core.file_validation import validate_upload_file, IMAGE_MAX_BYTES, VIDEO_MAX_BYTES, DOC_MAX_BYTES, DANGEROUS_EXTENSIONS, ALLOWED_UPLOAD_TYPES
from core.rate_limit import user_rate_limit
from core.analytics import record_event
from users.quota import check_and_add_storage_usage

# 上传限流：20 次/小时/用户
_upload_rl = method_decorator(user_rate_limit("upload", 20, 3600), name="dispatch")

OSS_PART_SIZE = 10 * 1024 * 1024  # 10MB per part


logger = logging.getLogger(__name__)

def _extract_first_frame(video_path: str, course_title: str) -> str | None:
    """用 ffmpeg 提取视频第一帧，返回截图临时文件路径。失败返回 None。"""
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.close()
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-ss", "0",
                "-i", video_path,
                "-vframes", "1",
                "-q:v", "2",
                "-y",
                tmp.name,
            ],
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.error("ffmpeg failed for %s: %s", video_path, result.stderr.decode(errors="replace")[-500:])
        if result.returncode != 0 or not os.path.isfile(tmp.name) or os.path.getsize(tmp.name) == 0:
            return None
        return tmp.name
    except FileNotFoundError:
        logger.error("ffmpeg not found — install ffmpeg on the server")
        return None
    except Exception:
        logger.exception("ffmpeg error for %s", video_path)
        return None


def _extract_cover_async(course_id: int) -> None:
    """后台线程：ffmpeg 提取视频第一帧作为封面，避免阻塞请求线程。"""
    def _run():
        from courses.models import Course
        try:
            course = Course.objects.get(pk=course_id)
            if not course.video_file or course.cover_image:
                return
            frame_path = _extract_first_frame(course.video_file.path, course.title)
            if not frame_path:
                return
            try:
                with open(frame_path, "rb") as f:
                    filename = f"cover_{course.id}_{uuid.uuid4().hex[:8]}.jpg"
                    course.cover_image.save(filename, File(f), save=True)
            finally:
                try:
                    os.remove(frame_path)
                except OSError:
                    pass
        except Exception:
            logger.exception("Async cover extraction failed for course %s", course_id)

    threading.Thread(target=_run, daemon=True).start()


def _get_oss_bucket():
    import oss2
    auth = oss2.Auth(settings.OSS_ACCESS_KEY_ID, settings.OSS_ACCESS_KEY_SECRET)
    return oss2.Bucket(auth, settings.OSS_ENDPOINT, settings.OSS_BUCKET_NAME)


@_upload_rl
class OSSMultipartInitView(APIView):
    """初始化 OSS 分片上传，返回 upload_id + 各片签名 URL。"""
    permission_classes = [IsAdmin]

    def post(self, request):
        file_name = str(request.data.get("file_name", "")).strip()
        file_size = _safe_int(request.data.get("file_size"), 0)

        if not file_name:
            return Response({"error": "缺少文件名"}, status=400)
        if file_size <= 0:
            return Response({"error": "文件大小非法"}, status=400)

        ext = os.path.splitext(file_name)[1].lower()
        if ext in DANGEROUS_EXTENSIONS:
            return Response({"error": f"不允许上传 {ext} 类型的文件"}, status=400)
        if ext not in ALLOWED_UPLOAD_TYPES:
            return Response({"error": f"不允许上传 {ext} 类型的文件"}, status=400)

        institution_id = request.user.institution_id or "public"
        unique_name = f"{uuid.uuid4().hex}{ext}"
        object_key = f"institutions/{institution_id}/video/{unique_name}"

        bucket = _get_oss_bucket()
        result = bucket.init_multipart_upload(object_key)
        upload_id = result.upload_id

        total_parts = (file_size + OSS_PART_SIZE - 1) // OSS_PART_SIZE
        signed_urls = []
        for part_number in range(1, total_parts + 1):
            url = bucket.sign_url(
                "PUT", object_key, 3600,
                headers={
                    "x-oss-sequential-read": "true",
                },
                params={
                    "uploadId": upload_id,
                    "partNumber": str(part_number),
                },
            )
            signed_urls.append(url)

        return Response({
            "upload_id": upload_id,
            "object_key": object_key,
            "part_size": OSS_PART_SIZE,
            "total_parts": total_parts,
            "signed_urls": signed_urls,
        })


@_upload_rl
class OSSMultipartCompleteView(APIView):
    """确认 OSS 分片上传完成 + 创建课程记录。"""
    permission_classes = [IsAdmin, HasQuota]
    quota_resource = 'course'

    def post(self, request):
        upload_id = str(request.data.get("upload_id", "")).strip()
        object_key = str(request.data.get("object_key", "")).strip()
        parts_json = str(request.data.get("parts", "[]")).strip()

        if not upload_id or not object_key:
            return Response({"error": "缺少 upload_id 或 object_key"}, status=400)

        # 校验 object_key 归属当前用户机构
        user_inst_id = getattr(request.user, 'institution_id', None)
        expected_prefix = f"institutions/{user_inst_id or 'public'}/"
        if not object_key.startswith(expected_prefix):
            return Response({"error": "无权操作此文件"}, status=403)

        # 解析 parts: [{"number": 1, "etag": "..."}, ...]
        try:
            parts = json.loads(parts_json)
        except (json.JSONDecodeError, TypeError):
            return Response({"error": "parts 格式非法"}, status=400)
        if not isinstance(parts, list) or not parts:
            return Response({"error": "parts 不能为空"}, status=400)

        # 完成 OSS 分片合并
        import oss2
        bucket = _get_oss_bucket()
        try:
            oss_parts = []
            for p in parts:
                part_number = _safe_int(p.get("number"), 0)
                etag = str(p.get("etag", "")).strip()
                if part_number <= 0 or not etag:
                    return Response({"error": f"part 数据非法: {p}"}, status=400)
                oss_parts.append(oss2.models.PartInfo(part_number, etag))
            bucket.complete_multipart_upload(upload_id, object_key, oss_parts)
        except Exception as exc:
            logger.error("OSS complete_multipart_upload failed: %s", exc)
            return Response({"error": f"OSS 合并失败: {exc}"}, status=500)

        # 验证文件确实存在
        if not bucket.object_exists(object_key):
            return Response({"error": "文件在 OSS 上不存在"}, status=500)

        # 获取实际文件大小
        obj_meta = bucket.head_object(object_key)
        video_size = obj_meta.content_length if obj_meta else 0

        # 校验课程元数据
        title = str(request.data.get("title", "")).strip()
        if not title:
            return Response({"error": "课程标题必填"}, status=400)

        description = request.data.get("description", "")
        elo_reward = _safe_int(request.data.get("elo_reward"), 50)
        album_obj_id = request.data.get("album_obj")
        knowledge_point_id = request.data.get("knowledge_point")
        cover_image = request.FILES.get("cover_image")
        courseware = request.FILES.get("courseware")
        reference_materials = request.FILES.get("reference_materials")

        validate_upload_file(cover_image, max_size_bytes=IMAGE_MAX_BYTES)
        validate_upload_file(courseware, max_size_bytes=DOC_MAX_BYTES)
        validate_upload_file(reference_materials, max_size_bytes=DOC_MAX_BYTES)

        # 存储配额（原子化）
        inst = request.user.institution
        total_upload_size = video_size
        for f in (cover_image, courseware, reference_materials):
            if f:
                total_upload_size += f.size
        check_and_add_storage_usage(inst, total_upload_size)

        # 创建课程
        course = Course(
            title=title,
            description=description,
            elo_reward=elo_reward,
            author=request.user,
            institution=inst,
        )
        if str(album_obj_id or "").strip() and str(album_obj_id) != "0":
            course.album_obj_id = _safe_int(album_obj_id, None)
        if str(knowledge_point_id or "").strip() and str(knowledge_point_id) != "0":
            course.knowledge_point_id = _safe_int(knowledge_point_id, None)
        if cover_image:
            course.cover_image = cover_image
        if courseware:
            course.courseware = courseware
        if reference_materials:
            course.reference_materials = reference_materials

        # 将 OSS object_key 关联到 video_file 字段
        original_name = os.path.basename(object_key)
        course.video_file.name = object_key
        course.save()

        # Tags
        tags_json = request.data.get("tags", "")
        if tags_json:
            try:
                tag_names = json.loads(tags_json)
                from .views_tags import _assign_tags
                _assign_tags(course, tag_names, inst)
            except Exception:
                pass

        # 未上传封面 → 后台线程提取第一帧
        if not cover_image:
            _extract_cover_async(course.id)

        # 后台触发 ASR 转录
        try:
            from .services.task_dispatcher import dispatch_transcription
            dispatch_transcription(course.id)
        except Exception:
            pass

        return Response(CourseSerializer(course).data, status=201)


class VideoProgressUpdateView(APIView):
    permission_classes = [IsMember]

    def post(self, request, pk):
        try:
            course = _get_course_for_user(pk, request.user, request)
            if not course:
                return Response({'error': 'Course not found'}, status=404)
            pos = request.data.get('position', 0)
            finished = request.data.get('is_finished', False)
            
            progress, created = VideoProgress.objects.get_or_create(
                user=request.user,
                course=course
            )
            if created:
                record_event('course_view', user=request.user, properties={'course_id': course.id})

            # 如果之前没完成，现在标记为完成，则发放奖励
            elo_added = 0
            if finished and not progress.is_finished:
                from django.db.models import F
                from django.db import transaction
                with transaction.atomic():
                    user = request.user.__class__.objects.select_for_update().get(pk=request.user.pk)
                    # 双重检查：atomic 内再次确认未完成，防止并发重复发放
                    progress_check = VideoProgress.objects.select_for_update().get(pk=progress.pk)
                    if not progress_check.is_finished:
                        progress_check.is_finished = True
                        progress_check.save(update_fields=['is_finished'])
                        user.elo_score = F('elo_score') + course.elo_reward
                        user.save(update_fields=['elo_score'])
                        elo_added = course.elo_reward
                        record_event('course_complete', user=request.user, properties={'course_id': course.id})
                # refresh to get actual value instead of F expression
                request.user.refresh_from_db(fields=['elo_score'])
                progress.is_finished = True
            
            progress.last_position = pos
            progress.save()
            
            return Response({
                'status': 'ok', 
                'is_finished': progress.is_finished,
                'elo_added': elo_added,
                'new_score': request.user.elo_score
            })
        except Course.DoesNotExist:
            return Response({'error': 'Course not found'}, status=404)

@_upload_rl
class StartupMaterialListCreateView(generics.ListCreateAPIView):
    serializer_class = StartupMaterialSerializer
    def get_permissions(self):
        if self.request.method == 'POST': return [IsAdmin()]
        return [permissions.AllowAny()]

    def get_queryset(self):
        return apply_institution_filter(StartupMaterial.objects.all().order_by('-created_at'), self.request.user, self.request)

    def perform_create(self, serializer):
        validate_upload_file(self.request.FILES.get("file"))
        total_size = sum(f.size for f in self.request.FILES.values() if f)
        inst = self.request.user.institution
        check_and_add_storage_usage(inst, total_size)
        serializer.save(institution=inst)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = _safe_int(request.query_params.get('page'), 1)
        page_size = _safe_int(request.query_params.get('page_size'), 10)
        total = queryset.count()
        offset = (page - 1) * page_size
        paged = queryset[offset:offset + page_size]
        serializer = self.get_serializer(paged, many=True)
        return Response({
            'items': serializer.data,
            'total': total,
            'page': page,
            'total_pages': max(1, (total + page_size - 1) // page_size),
        })

class StartupMaterialDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = StartupMaterialSerializer
    def get_permissions(self):
        if self.request.method in ['PATCH', 'PUT', 'DELETE']: return [IsAdmin()]
        return [permissions.AllowAny()]

    def get_queryset(self):
        return apply_institution_filter(StartupMaterial.objects.all(), self.request.user, self.request)

@_upload_rl
class AlbumListCreateView(generics.ListCreateAPIView):
    serializer_class = AlbumSerializer
    def get_queryset(self):
        from django.db.models import Count
        qs = Album.objects.annotate(course_count=Count('courses')).prefetch_related('courses').order_by('-created_at')
        return apply_institution_filter(qs, self.request.user, self.request)
    def get_permissions(self):
        if self.request.method == 'POST': return [IsAdmin()]
        return [permissions.AllowAny()]

    def perform_create(self, serializer):
        validate_upload_file(self.request.FILES.get("cover_image"), max_size_bytes=IMAGE_MAX_BYTES)
        total_size = sum(f.size for f in self.request.FILES.values() if f)
        inst = self.request.user.institution
        check_and_add_storage_usage(inst, total_size)
        serializer.save(institution=inst)

class AlbumDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AlbumSerializer
    def get_permissions(self):
        if self.request.method in ['PATCH', 'PUT', 'DELETE']: return [IsAdmin()]
        return [permissions.AllowAny()]

    def get_queryset(self):
        return apply_institution_filter(Album.objects.all(), self.request.user, self.request)


class AlbumCoursesView(APIView):
    permission_classes = [IsMember]

    def get(self, request, album_id):
        album = apply_institution_filter(Album.objects.all(), request.user, request).filter(pk=album_id).first()
        if not album:
            return Response({'error': '专辑不存在'}, status=404)

        courses = album.courses.all().order_by('sort_order', '-created_at')
        return Response(CourseSerializer(courses, many=True).data)

@_upload_rl
class CourseListCreateView(generics.ListCreateAPIView):
    serializer_class = CourseSerializer
    quota_resource = 'course'

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdmin(), HasQuota()]
        return [IsMember()]

    def get_queryset(self):
        user = self.request.user
        qs = apply_institution_filter(Course.objects.all().order_by('-created_at'), user, self.request)
        q = self.request.query_params.get('search')
        kp = self.request.query_params.get('kp')
        if q: qs = qs.filter(title__icontains=q)
        if kp: qs = qs.filter(knowledge_point_id=kp)
        tag = self.request.query_params.getlist('tag')
        if tag:
            from courses.models import CourseTagRelation
            from django.db.models import Count
            matching_qs = CourseTagRelation.objects.filter(
                tag__slug__in=tag,
                tag__institution=self.request.user.institution,
            ).values('course_id').annotate(n=Count('id')).filter(n=len(tag))
            qs = qs.filter(id__in=[m['course_id'] for m in matching_qs])
        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = _safe_int(request.query_params.get('page'), 1)
        page_size = _safe_int(request.query_params.get('page_size'), 10)
        total = queryset.count()
        offset = (page - 1) * page_size
        paged = queryset[offset:offset + page_size]
        serializer = self.get_serializer(paged, many=True)
        return Response({
            'items': serializer.data,
            'total': total,
            'page': page,
            'total_pages': max(1, (total + page_size - 1) // page_size),
        })

    def perform_create(self, serializer):
        files = self.request.FILES
        validate_upload_file(files.get("cover_image"), max_size_bytes=IMAGE_MAX_BYTES)
        validate_upload_file(files.get("video_file"), max_size_bytes=VIDEO_MAX_BYTES)
        validate_upload_file(files.get("courseware"), max_size_bytes=DOC_MAX_BYTES)
        validate_upload_file(files.get("reference_materials"), max_size_bytes=DOC_MAX_BYTES)
        total_size = sum(f.size for f in files.values() if f)
        inst = self.request.user.institution
        check_and_add_storage_usage(inst, total_size)

        # 支持 OSS 直传：如果提供了 video_file_url，使用 OSS URL
        video_file_url = self.request.data.get('video_file_url')
        video_object_key = self.request.data.get('video_object_key')

        if video_file_url and video_object_key:
            # OSS 直传模式：URL 已经在 OSS 上
            course = serializer.save(author=self.request.user, institution=inst)
            # 更新视频文件字段为 OSS URL
            course.video_file = video_file_url
            course.save(update_fields=['video_file'])
        else:
            # 传统上传模式：文件通过后端上传
            course = serializer.save(author=self.request.user, institution=inst)

        # 未上传封面 → 后台线程提取第一帧
        if not course.cover_image and course.video_file:
            _extract_cover_async(course.id)

        # Assign tags from request
        tags_json = self.request.data.get('tags', '')
        if tags_json:
            try:
                tag_names = json.loads(tags_json)
                from .views_tags import _assign_tags
                _assign_tags(course, tag_names, self.request.user.institution)
            except Exception:
                pass

        # 后台触发 ASR 转录
        try:
            from .services.task_dispatcher import dispatch_transcription
            dispatch_transcription(course.id)
        except Exception:
            pass

class CourseDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Course.objects.all()
    serializer_class = CourseSerializer

    def get_queryset(self):
        return apply_institution_filter(super().get_queryset(), self.request.user, self.request)

    def get_permissions(self):
        if self.request.method in ['PATCH', 'PUT', 'DELETE']:
            return [IsAdmin()]
        return [IsMember()]


class CourseOutlineView(APIView):
    permission_classes = [IsMember]

    def get(self, request, pk):
        course = _get_course_for_user(pk, request.user, request)
        if not course:
            return Response({'error': '课程不存在'}, status=404)

        try:
            outline = course.outline
        except Exception:
            return Response({'status': 'not_available', 'items': []})

        items = list(outline.items.values('title', 'timestamp', 'description', 'index').order_by('index'))
        return Response({
            'status': outline.status,
            'items': items,
        })

    def post(self, request, pk):
        course = _get_course_for_user(pk, request.user, request)
        if not course:
            return Response({'error': '课程不存在'}, status=404)

        transcript = getattr(course, 'transcript', None)
        if not transcript or transcript.asr_status != 'completed':
            return Response({'error': '请先完成语音转录'}, status=400)

        from .models import CourseOutline
        outline, _ = CourseOutline.objects.get_or_create(course=course)
        if outline.status not in ('completed', 'generating'):
            from .services.task_dispatcher import dispatch_outline_generation
            dispatch_outline_generation(course.id)
        return Response({'status': 'processing'})


class CourseTranscriptView(APIView):
    permission_classes = [IsMember]

    def get(self, request, pk):
        course = _get_course_for_user(pk, request.user, request)
        if not course:
            return Response({'error': '课程不存在'}, status=404)

        try:
            transcript = course.transcript
        except Exception:
            return Response({'status': 'not_available', 'segments': [], 'full_text': ''})

        segments = list(transcript.segments.values('start_time', 'end_time', 'text', 'index').order_by('index'))
        return Response({
            'status': transcript.asr_status,
            'segments': segments,
            'full_text': transcript.full_text,
        })

    def post(self, request, pk):
        course = _get_course_for_user(pk, request.user, request)
        if not course:
            return Response({'error': '课程不存在'}, status=404)

        from .services.task_dispatcher import dispatch_transcription
        dispatch_transcription(course.id)
        return Response({'status': 'processing'})
