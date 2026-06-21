import json
import logging
import os
import subprocess
import tempfile
import threading
import uuid

from django.conf import settings
from django.core.files import File
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.decorators import method_decorator
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import generics, permissions
from rest_framework.permissions import IsAuthenticated
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


def _load_prompt(template_name: str) -> str:
    """从 prompts/courses/ 目录加载 prompt 模板文件。"""
    path = os.path.join(settings.BASE_DIR, 'prompts', 'courses', template_name)
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


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
            album_id = _safe_int(album_obj_id, None)
            if inst and album_id:
                from courses.models import Album
                album = Album.objects.filter(id=album_id).first()
                if not album or album.institution_id != inst.id:
                    return Response({"error": "专辑不属于当前机构"}, status=403)
            course.album_obj_id = album_id
        if str(knowledge_point_id or "").strip() and str(knowledge_point_id) != "0":
            kp_id = _safe_int(knowledge_point_id, None)
            if inst and kp_id:
                from quizzes.models import KnowledgePoint
                kp = KnowledgePoint.objects.filter(id=kp_id).first()
                if not kp:
                    return Response({"error": "知识点不存在"}, status=400)
                if kp.institution_id and kp.institution_id != inst.id:
                    return Response({"error": "知识点不属于当前机构"}, status=403)
            course.knowledge_point_id = kp_id
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
            
            from django.db import transaction
            elo_added = 0
            with transaction.atomic():
                progress, created = VideoProgress.objects.get_or_create(
                    user=request.user,
                    course=course
                )
                if created:
                    record_event('course_view', user=request.user, properties={'course_id': course.id})

                # 如果之前没完成，现在标记为完成，则发放奖励
                if finished and not progress.is_finished:
                    from django.db.models import F
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
                if finished:
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
        class_id = self.request.query_params.get('class_id')
        if class_id:
            try:
                from users.models import ClassCourse
                course_ids = ClassCourse.objects.filter(
                    class_obj_id=int(class_id)
                ).values_list('course_id', flat=True)
                qs = qs.filter(id__in=course_ids)
            except (ValueError, TypeError):
                pass
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


# ── Teaching Plan & Lesson Plan ──

from courses.models import TeachingPlan, LessonPlan
from courses.serializers import TeachingPlanSerializer, LessonPlanSerializer


class TeachingPlanListCreateView(APIView):
    """GET/POST /api/courses/teaching-plans/ — 教学计划列表+创建。"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        institution = getattr(user, 'institution', None)
        if not institution:
            return Response({'error': '无机构归属'}, status=403)

        role = getattr(user, 'institution_role', '')
        if role == 'student':
            # 学生只看自己班级的教学计划
            student_classes = user.classes.all()
            qs = TeachingPlan.objects.filter(class_obj__in=student_classes).select_related('class_obj').prefetch_related('lesson_plans')
        elif role in ('teacher', 'owner', 'registrar'):
            qs = TeachingPlan.objects.filter(institution=institution).select_related('class_obj').prefetch_related('lesson_plans')
        else:
            return Response({'error': '无权限'}, status=403)

        class_id = request.query_params.get('class_id')
        if class_id:
            qs = qs.filter(class_obj_id=int(class_id))

        data = TeachingPlanSerializer(qs.order_by('-created_at'), many=True).data
        return Response(data)

    def post(self, request):
        user = request.user
        institution = getattr(user, 'institution', None)
        if not institution:
            return Response({'error': '无机构归属'}, status=403)

        role = getattr(user, 'institution_role', '')
        if role not in ('teacher', 'owner'):
            return Response({'error': '仅教师/机构主可创建'}, status=403)

        serializer = TeachingPlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = serializer.save(institution=institution, created_by=user)
        return Response(TeachingPlanSerializer(plan).data, status=201)


class TeachingPlanDetailView(APIView):
    """GET/PUT/DELETE /api/courses/teaching-plans/<id>/ — 教学计划详情。"""
    permission_classes = [IsAuthenticated]

    def _get_plan(self, pk, user):
        institution = getattr(user, 'institution', None)
        if not institution:
            return None
        try:
            plan = TeachingPlan.objects.get(id=pk)
        except TeachingPlan.DoesNotExist:
            return None
        if plan.institution_id != institution.id:
            return None
        return plan

    def get(self, request, pk):
        plan = self._get_plan(pk, request.user)
        if not plan:
            return Response({'error': '教学计划不存在'}, status=404)
        return Response(TeachingPlanSerializer(plan).data)

    def put(self, request, pk):
        plan = self._get_plan(pk, request.user)
        if not plan:
            return Response({'error': '教学计划不存在'}, status=404)
        serializer = TeachingPlanSerializer(plan, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        plan = self._get_plan(pk, request.user)
        if not plan:
            return Response({'error': '教学计划不存在'}, status=404)
        plan.delete()
        return Response({'deleted': True})


class LessonPlanListCreateView(APIView):
    """GET/POST /api/courses/lesson-plans/ — 教案列表+创建。"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        institution = getattr(user, 'institution', None)
        if not institution:
            return Response({'error': '无机构归属'}, status=403)

        qs = LessonPlan.objects.filter(institution=institution)

        plan_id = request.query_params.get('teaching_plan_id')
        if plan_id:
            qs = qs.filter(teaching_plan_id=int(plan_id))

        return Response(LessonPlanSerializer(qs.order_by('week_number', 'order'), many=True).data)

    def post(self, request):
        user = request.user
        institution = getattr(user, 'institution', None)
        if not institution:
            return Response({'error': '无机构归属'}, status=403)

        role = getattr(user, 'institution_role', '')
        if role not in ('teacher', 'owner'):
            return Response({'error': '仅教师/机构主可创建'}, status=403)

        serializer = LessonPlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plan = serializer.save(institution=institution, created_by=user)
        return Response(LessonPlanSerializer(plan).data, status=201)


class LessonPlanDetailView(APIView):
    """GET/PUT/DELETE /api/courses/lesson-plans/<id>/ — 教案详情。"""
    permission_classes = [IsAuthenticated]

    def _get_plan(self, pk, user):
        institution = getattr(user, 'institution', None)
        if not institution:
            return None
        try:
            plan = LessonPlan.objects.get(id=pk)
        except LessonPlan.DoesNotExist:
            return None
        if plan.institution_id != institution.id:
            return None
        return plan

    def get(self, request, pk):
        plan = self._get_plan(pk, request.user)
        if not plan:
            return Response({'error': '教案不存在'}, status=404)
        return Response(LessonPlanSerializer(plan).data)

    def put(self, request, pk):
        plan = self._get_plan(pk, request.user)
        if not plan:
            return Response({'error': '教案不存在'}, status=404)
        serializer = LessonPlanSerializer(plan, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        plan = self._get_plan(pk, request.user)
        if not plan:
            return Response({'error': '教案不存在'}, status=404)
        plan.delete()
        return Response({'deleted': True})


class AIGenerateLessonPlanView(APIView):
    """POST /api/courses/lesson-plans/ai-generate/ — AI 生成教案详细内容（结构化）。"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        institution = getattr(user, 'institution', None)
        if not institution:
            return Response({'error': '无机构归属'}, status=403)

        role = getattr(user, 'institution_role', '')
        if role not in ('teacher', 'owner'):
            return Response({'error': '仅教师/机构主可操作'}, status=403)

        plan_id = request.data.get('lesson_plan_id')
        if not plan_id:
            return Response({'error': '缺少 lesson_plan_id'}, status=400)

        try:
            lesson = LessonPlan.objects.select_related('teaching_plan').get(
                id=int(plan_id), institution=institution
            )
        except LessonPlan.DoesNotExist:
            return Response({'error': '教案不存在'}, status=404)

        from ai_engine import AIService

        tp = lesson.teaching_plan
        subject = tp.subject if tp else ''
        week_plan = None
        if tp and tp.weekly_plans and lesson.week_number:
            week_plan = next((w for w in tp.weekly_plans if w.get('week') == lesson.week_number), None)

        week_context = ''
        if week_plan:
            week_context = f'本周主题：{week_plan.get("topic", "")}\n周教学目标：{week_plan.get("objectives", "")}'

        kp_names = list(lesson.knowledge_points.values_list('name', flat=True))

        system_prompt = _load_prompt('lesson_plan_generate.txt')
        user_prompt = (
            f'学科：{subject}\n课题：{lesson.title}\n'
            f'教学目标：{lesson.objectives}\n'
            f'知识点：{", ".join(kp_names) if kp_names else "无"}\n'
            f'课时：{lesson.duration_minutes}分钟\n'
            f'{week_context}\n'
            f'请生成完整的结构化教案，activities 包含完整的教学过程（导入-新授-巩固-小结）。'
        )

        # ── Memorix 学情注入 ──
        if tp and tp.class_obj:
            try:
                from .services.analytics_service import get_class_kp_analytics
                analytics = get_class_kp_analytics(tp)
                lesson_kp_perf = [p for p in analytics.get('performance', [])
                                  if kp_names and p['kp_name'] in kp_names]
                if lesson_kp_perf:
                    user_prompt += '\n\n学生对该知识点的掌握情况：\n'
                    for p in lesson_kp_perf[:3]:
                        mastery = p.get('mastery_avg', '?')
                        user_prompt += f'- {p["kp_name"]}: 正确率{p["correct_rate"]}%、平均掌握度{mastery}\n'
                    weak = [p for p in lesson_kp_perf if p['correct_rate'] < 60]
                    if weak:
                        user_prompt += '建议：学生基础薄弱，请增加概念讲解和基础练习的时间比例。'
            except Exception:
                pass

        try:
            result = AIService.chat(
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt},
                ],
                temperature=0.7,
                max_tokens=2048,
                response_format={'type': 'json_object'},
            )
            content = result.get('content', '{}')
            import json as _json
            ai_data = _json.loads(content)
        except Exception:
            logger.exception('AI lesson plan generation failed')
            return Response({'error': 'AI 生成失败，请稍后重试'}, status=500)

        # Merge AI output into lesson plan
        if ai_data.get('objectives'):
            lesson.objectives = ai_data['objectives']
        if ai_data.get('activities'):
            lesson.activities = ai_data['activities']
        if ai_data.get('materials'):
            lesson.materials = ai_data['materials']
        lesson.ai_generated = {
            'generated_at': timezone.now().isoformat(),
            'content': content,
            'model': result.get('model', 'unknown'),
        }
        lesson.save()

        return Response({
            'lesson_plan': LessonPlanSerializer(lesson).data,
            'ai_generated': lesson.ai_generated,
        })


class AIGenerateWeeklyPlansView(APIView):
    """POST /api/courses/teaching-plans/<id>/ai-generate-weeks/ — AI 生成整学期周计划。"""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        institution = getattr(user, 'institution', None)
        if not institution:
            return Response({'error': '无机构归属'}, status=403)

        role = getattr(user, 'institution_role', '')
        if role not in ('teacher', 'owner'):
            return Response({'error': '仅教师/机构主可操作'}, status=403)

        try:
            plan = TeachingPlan.objects.get(id=pk, institution=institution)
        except TeachingPlan.DoesNotExist:
            return Response({'error': '教学计划不存在'}, status=404)

        from ai_engine import AIService

        system_prompt = _load_prompt('weekly_plans_generate.txt')
        user_prompt = (
            f'学科：{plan.subject}\n'
            f'学期：{plan.semester}\n'
            f'总周数：{plan.week_count}\n'
            f'计划名称：{plan.title}\n'
            f'描述：{plan.description}\n'
            f'请为这 {plan.week_count} 周逐一设计主题和教学目标。'
        )

        # ── Memorix 学情注入 ──
        try:
            from .services.analytics_service import get_class_kp_analytics, format_analytics_for_ai_prompt
            analytics = get_class_kp_analytics(plan)
            context = format_analytics_for_ai_prompt(analytics)
            if context:
                user_prompt += '\n\n' + context
                system_prompt += '\n教学顺序必须遵循前驱关系，薄弱知识点需分配更多周数，学期中段和末尾各留1-2周复习。'
        except Exception:
            pass

        try:
            result = AIService.chat(
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt},
                ],
                temperature=0.8,
                max_tokens=4096,
                response_format={'type': 'json_object'},
            )
            content = result.get('content', '{}')
            import json as _json
            ai_data = _json.loads(content)
            weekly_plans = ai_data.get('weekly_plans', [])
        except Exception:
            logger.exception('AI weekly plan generation failed')
            return Response({'error': 'AI 生成失败，请稍后重试'}, status=500)

        # Merge with existing manual entries — AI only fills empty weeks
        existing = {w['week']: w for w in (plan.weekly_plans or [])}
        for wp in weekly_plans:
            week_num = wp.get('week', 0)
            if week_num and week_num not in existing:
                existing[week_num] = {
                    'week': week_num,
                    'topic': wp.get('topic', ''),
                    'objectives': wp.get('objectives', ''),
                    'materials': wp.get('materials', ''),
                    'kp_ids': wp.get('kp_ids', []),
                }

        plan.weekly_plans = sorted(existing.values(), key=lambda w: w['week'])
        plan.save(update_fields=['weekly_plans'])

        return Response({
            'weekly_plans': plan.weekly_plans,
            'message': f'已生成 {len(weekly_plans)} 周计划',
        })


class AIGenerateWeekLessonsView(APIView):
    """POST /api/courses/teaching-plans/<id>/ai-generate-lessons/ — AI 为指定周批量生成教案。"""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        institution = getattr(user, 'institution', None)
        if not institution:
            return Response({'error': '无机构归属'}, status=403)

        role = getattr(user, 'institution_role', '')
        if role not in ('teacher', 'owner'):
            return Response({'error': '仅教师/机构主可操作'}, status=403)

        try:
            plan = TeachingPlan.objects.get(id=pk, institution=institution)
        except TeachingPlan.DoesNotExist:
            return Response({'error': '教学计划不存在'}, status=404)

        week_number = request.data.get('week_number')
        if not week_number:
            return Response({'error': '缺少 week_number'}, status=400)
        week_number = int(week_number)

        week_plan = None
        if plan.weekly_plans:
            week_plan = next((w for w in plan.weekly_plans if w.get('week') == week_number), None)

        topic = week_plan.get('topic', '') if week_plan else ''
        objectives = week_plan.get('objectives', '') if week_plan else ''

        from ai_engine import AIService

        system_prompt = _load_prompt('week_lessons_generate.txt')
        user_prompt = (
            f'学科：{plan.subject}\n'
            f'本周主题：{topic}\n'
            f'周教学目标：{objectives}\n'
            f'请设计 2-4 节课的教案，覆盖本周主题的核心内容。'
        )

        # ── Memorix 学情注入 ──
        try:
            from .services.analytics_service import get_class_kp_analytics, format_analytics_for_ai_prompt
            analytics = get_class_kp_analytics(plan)
            week_kp_ids = (week_plan or {}).get('kp_ids', [])
            if week_kp_ids:
                week_perf = [p for p in analytics.get('performance', []) if p['kp_id'] in week_kp_ids]
                if week_perf:
                    weak_in_week = [p for p in week_perf if p['correct_rate'] < 70]
                    if weak_in_week:
                        user_prompt += '\n\n本周知识点学情：\n'
                        for p in weak_in_week:
                            user_prompt += f'- {p["kp_name"]}: 班级正确率仅{p["correct_rate"]}%，需要更多基础讲解和练习\n'
        except Exception:
            pass

        try:
            result = AIService.chat(
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt},
                ],
                temperature=0.8,
                max_tokens=4096,
                response_format={'type': 'json_object'},
            )
            content = result.get('content', '{}')
            import json as _json
            ai_data = _json.loads(content)
            lessons_data = ai_data.get('lessons', [])
        except Exception:
            logger.exception('AI week lessons generation failed')
            return Response({'error': 'AI 生成失败，请稍后重试'}, status=500)

        # Create lesson plans — delete existing AI-generated ones for this week first
        created = []
        for i, ldata in enumerate(lessons_data):
            lesson = LessonPlan.objects.create(
                teaching_plan=plan,
                institution=institution,
                title=ldata.get('title', f'第{week_number}周-第{i+1}课'),
                objectives=ldata.get('objectives', ''),
                activities=ldata.get('activities'),
                materials=ldata.get('materials'),
                duration_minutes=ldata.get('duration_minutes', 45),
                week_number=week_number,
                order=i,
                created_by=user,
                ai_generated={
                    'generated_at': timezone.now().isoformat(),
                    'content': content,
                    'model': result.get('model', 'unknown'),
                },
            )
            created.append(LessonPlanSerializer(lesson).data)

        return Response({
            'lessons': created,
            'message': f'第 {week_number} 周已生成 {len(created)} 节教案',
        })


class LessonPlanPDFView(APIView):
    """GET /api/courses/teaching-plans/<pk>/pdf/ — 导出教学计划为 PDF。"""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        plan = get_object_or_404(TeachingPlan, pk=pk)
        # Check institution access
        inst = getattr(request.user, 'institution', None)
        if inst and plan.institution_id != inst.id:
            return Response({'error': '无权访问'}, status=403)

        lesson_plans = plan.lesson_plans.all().order_by('week_number', 'order')
        html = render_to_string('lesson_plan_pdf.html', {
            'plan': plan,
            'lesson_plans': lesson_plans,
            'weekly_plans': plan.weekly_plans or [],
            'generated_at': timezone.now(),
        })

        from quizzes.services.pdf_generator import _html_to_pdf
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            pdf_path = tmp.name
        try:
            _html_to_pdf(html, pdf_path)
            with open(pdf_path, 'rb') as f:
                pdf_bytes = f.read()
        finally:
            os.unlink(pdf_path)

        filename = f'教学计划-{plan.title}-{plan.semester}.pdf'
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class TeachingPlanAnalyticsView(APIView):
    """GET /api/courses/teaching-plans/<id>/analytics/ — 班级学情分析 + AI 教学建议。"""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        user = request.user
        institution = getattr(user, 'institution', None)
        if not institution:
            return Response({'error': '无机构归属'}, status=403)

        role = getattr(user, 'institution_role', '')
        if role not in ('teacher', 'owner'):
            return Response({'error': '仅教师/机构主可查看'}, status=403)

        try:
            plan = TeachingPlan.objects.select_related('class_obj').get(id=pk, institution=institution)
        except TeachingPlan.DoesNotExist:
            return Response({'error': '教学计划不存在'}, status=404)

        # 获取 Memorix 学情数据
        from .services.analytics_service import get_class_kp_analytics
        analytics = get_class_kp_analytics(plan)

        # AI 生成教学建议
        ai_suggestions = None
        if analytics['student_count'] > 0 and (analytics['weak_kps'] or analytics['prerequisite_chains']):
            try:
                from ai_engine import AIService
                prompt = (
                    f'学科：{plan.subject}\n'
                    f'班级：{plan.class_obj.name}，{analytics["student_count"]}名学生\n'
                    f'教学周数：{plan.week_count}\n\n'
                )
                if analytics['weak_kps']:
                    prompt += '薄弱知识点：\n'
                    for kp in analytics['weak_kps']:
                        prompt += f'- {kp["kp_name"]}: 正确率{kp["correct_rate"]}%\n'
                if analytics['prerequisite_chains']:
                    prompt += '\n知识点前驱关系（必须按先后顺序教学）：\n'
                    for pc in analytics['prerequisite_chains'][:3]:
                        prompt += '- ' + ' → '.join(n['kp_name'] for n in pc['chain']) + '\n'
                if analytics['forgetting_risk']:
                    prompt += '\n高遗忘风险知识点：\n'
                    for r in analytics['forgetting_risk'][:5]:
                        prompt += f'- {r["kp_name"]}: 遗忘风险{r["avg_retrievability"]}\n'

                result = AIService.chat(
                    messages=[
                        {'role': 'system', 'content': '你是教学分析专家。根据班级学情数据，给出简明的教学建议。'},
                        {'role': 'user', 'content': prompt + '\n请给出：1) 应优先安排哪些知识点 2) 建议的教学顺序调整 3) 是否需要插入复习周'},
                    ],
                    temperature=0.5,
                    max_tokens=1024,
                )
                ai_suggestions = result.get('content', '')
            except Exception:
                logger.exception('AI suggestions generation failed')

        return Response({
            'subject': plan.subject,
            'class_name': plan.class_obj.name,
            'student_count': analytics['student_count'],
            'performance': analytics['performance'],
            'weak_kps': analytics['weak_kps'],
            'prerequisite_chains': analytics['prerequisite_chains'],
            'forgetting_risk': analytics['forgetting_risk'],
            'ai_suggestions': ai_suggestions,
        })
