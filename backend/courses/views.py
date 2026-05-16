import fcntl
import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path

from django.conf import settings
from django.core.files import File
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import generics, permissions
from users.permissions import IsAdmin

from .models import Course, Album, StartupMaterial, VideoProgress
from .serializers import CourseSerializer, AlbumSerializer, StartupMaterialSerializer
from users.views import IsMember
from quizzes.utils import safe_int as _safe_int


CHUNK_DIR = Path(settings.MEDIA_ROOT) / "chunk_uploads"
MAX_CHUNK_SIZE_BYTES = 20 * 1024 * 1024  # 20MB per chunk


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
        if result.returncode != 0 or not os.path.isfile(tmp.name) or os.path.getsize(tmp.name) == 0:
            return None
        return tmp.name
    except Exception:
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


def _upload_dir(upload_id: str) -> Path:
    return CHUNK_DIR / upload_id


def _meta_path(upload_id: str) -> Path:
    return _upload_dir(upload_id) / "meta.json"


def _chunk_path(upload_id: str, chunk_index: int) -> Path:
    return _upload_dir(upload_id) / f"chunk_{chunk_index:08d}.part"


def _load_meta(upload_id: str):
    meta_file = _meta_path(upload_id)
    if not meta_file.exists():
        return None
    with meta_file.open("r", encoding="utf-8") as f:
        return json.load(f)


def _add_chunk_to_meta(upload_id: str, chunk_index: int) -> dict:
    """原子化添加分片索引 — 使用文件锁防止并发覆写。"""
    meta_path = _meta_path(upload_id)
    with open(meta_path, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        meta = json.load(f)
        uploaded_chunks = set(meta.get("uploaded_chunks", []))
        uploaded_chunks.add(chunk_index)
        meta["uploaded_chunks"] = sorted(uploaded_chunks)
        f.seek(0)
        f.truncate()
        json.dump(meta, f, ensure_ascii=False)
        return meta


class ChunkedUploadInitView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request):
        file_name = str(request.data.get("file_name", "")).strip()
        total_size = _safe_int(request.data.get("total_size"), 0)
        chunk_size = _safe_int(request.data.get("chunk_size"), 0)
        total_chunks = _safe_int(request.data.get("total_chunks"), 0)
        mime_type = str(request.data.get("mime_type", "")).strip()

        if not file_name:
            return Response({"error": "缺少文件名"}, status=400)
        if total_size <= 0 or chunk_size <= 0 or total_chunks <= 0:
            return Response({"error": "分片参数非法"}, status=400)
        if chunk_size > MAX_CHUNK_SIZE_BYTES:
            return Response({"error": f"单片过大，单片上限 {MAX_CHUNK_SIZE_BYTES // (1024 * 1024)}MB"}, status=400)

        upload_id = uuid.uuid4().hex
        upload_path = _upload_dir(upload_id)
        upload_path.mkdir(parents=True, exist_ok=True)

        meta = {
            "upload_id": upload_id,
            "file_name": file_name,
            "total_size": total_size,
            "chunk_size": chunk_size,
            "total_chunks": total_chunks,
            "mime_type": mime_type,
            "uploaded_chunks": [],
            "user_id": request.user.id,
        }
        with _meta_path(upload_id).open("w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)

        return Response(
            {
                "upload_id": upload_id,
                "max_chunk_size": MAX_CHUNK_SIZE_BYTES,
            }
        )


class ChunkedUploadChunkView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, upload_id):
        meta = _load_meta(upload_id)
        if not meta:
            return Response({"error": "上传会话不存在或已失效"}, status=404)
        if meta.get("user_id") != request.user.id:
            return Response({"error": "无权限访问该上传会话"}, status=403)

        chunk_index = _safe_int(request.data.get("chunk_index"), -1)
        chunk = request.FILES.get("chunk")

        if chunk is None:
            return Response({"error": "缺少分片文件"}, status=400)
        if chunk_index < 0 or chunk_index >= _safe_int(meta.get("total_chunks"), 0):
            return Response({"error": "分片索引非法"}, status=400)
        if chunk.size > MAX_CHUNK_SIZE_BYTES:
            return Response({"error": "分片超出大小限制"}, status=400)

        chunk_file = _chunk_path(upload_id, chunk_index)
        with chunk_file.open("wb") as f:
            for part in chunk.chunks():
                f.write(part)

        updated_meta = _add_chunk_to_meta(upload_id, chunk_index)

        return Response(
            {
                "status": "ok",
                "uploaded_count": len(updated_meta["uploaded_chunks"]),
                "total_chunks": updated_meta["total_chunks"],
            }
        )


class ChunkedUploadCompleteView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, upload_id):
        meta = _load_meta(upload_id)
        if not meta:
            return Response({"error": "上传会话不存在或已失效"}, status=404)
        if meta.get("user_id") != request.user.id:
            return Response({"error": "无权限访问该上传会话"}, status=403)

        total_chunks = _safe_int(meta.get("total_chunks"), 0)
        uploaded_chunks = set(meta.get("uploaded_chunks", []))
        missing = [i for i in range(total_chunks) if i not in uploaded_chunks]
        if missing:
            return Response({"error": f"仍有分片缺失，缺失数：{len(missing)}"}, status=400)

        title = str(request.data.get("title", "")).strip()
        if not title:
            return Response({"error": "课程标题必填"}, status=400)

        description = request.data.get("description", "")
        elo_reward = _safe_int(request.data.get("elo_reward"), 50)
        album_obj_id = request.data.get("album_obj")
        knowledge_point_id = request.data.get("knowledge_point")
        cover_image = request.FILES.get("cover_image")
        courseware = request.FILES.get("courseware")

        upload_path = _upload_dir(upload_id)
        merged_path = upload_path / "merged_video.bin"

        try:
            with merged_path.open("wb") as merged:
                for chunk_index in range(total_chunks):
                    chunk_file = _chunk_path(upload_id, chunk_index)
                    with chunk_file.open("rb") as cf:
                        shutil.copyfileobj(cf, merged, length=8 * 1024 * 1024)

            original_name = os.path.basename(meta.get("file_name") or "video.mp4")
            course = Course(
                title=title,
                description=description,
                elo_reward=elo_reward,
                author=request.user,
                institution=request.user.institution,
            )
            if str(album_obj_id or "").strip() and str(album_obj_id) != "0":
                course.album_obj_id = _safe_int(album_obj_id, None)
            if str(knowledge_point_id or "").strip() and str(knowledge_point_id) != "0":
                course.knowledge_point_id = _safe_int(knowledge_point_id, None)
            if cover_image:
                course.cover_image = cover_image
            if courseware:
                course.courseware = courseware

            with merged_path.open("rb") as merged_file:
                course.video_file.save(original_name, File(merged_file), save=False)
            course.save()
        except Exception as exc:
            return Response({"error": f"合并失败：{exc}"}, status=500)
        finally:
            shutil.rmtree(upload_path, ignore_errors=True)

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
            course = Course.objects.get(pk=pk)
            pos = request.data.get('position', 0)
            finished = request.data.get('is_finished', False)
            
            progress, created = VideoProgress.objects.get_or_create(
                user=request.user,
                course=course
            )
            
            # 如果之前没完成，现在标记为完成，则发放奖励
            elo_added = 0
            if finished and not progress.is_finished:
                progress.is_finished = True
                user = request.user
                user.elo_score += course.elo_reward
                user.save()
                elo_added = course.elo_reward
            
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
    queryset = StartupMaterial.objects.all().order_by('-created_at')
    serializer_class = StartupMaterialSerializer
    def get_permissions(self):
        if self.request.method == 'POST': return [IsAdmin()]
        return [permissions.AllowAny()]

class StartupMaterialDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = StartupMaterial.objects.all()
    serializer_class = StartupMaterialSerializer
    def get_permissions(self):
        if self.request.method in ['PATCH', 'PUT', 'DELETE']: return [IsAdmin()]
        return [permissions.AllowAny()]

class AlbumListCreateView(generics.ListCreateAPIView):
    queryset = Album.objects.all().order_by('-created_at')
    serializer_class = AlbumSerializer
    def get_permissions(self):
        if self.request.method == 'POST': return [IsAdmin()]
        return [permissions.AllowAny()]

class AlbumDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Album.objects.all()
    serializer_class = AlbumSerializer
    def get_permissions(self):
        if self.request.method in ['PATCH', 'PUT', 'DELETE']: return [IsAdmin()]
        return [permissions.AllowAny()]

class CourseListCreateView(generics.ListCreateAPIView):
    serializer_class = CourseSerializer
    
    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdmin()]
        return [IsMember()]

    def get_queryset(self):
        user = self.request.user
        qs = Course.objects.all().order_by('-created_at')
        from users.permissions import is_platform_admin
        from django.db.models import Q
        if not is_platform_admin(user):
            inst = getattr(user, 'institution', None)
            if inst:
                qs = qs.filter(Q(institution=inst) | Q(institution__isnull=True))
            else:
                qs = qs.filter(institution__isnull=True)
        q = self.request.query_params.get('search')
        kp = self.request.query_params.get('kp')
        if q: qs = qs.filter(title__icontains=q)
        if kp: qs = qs.filter(knowledge_point_id=kp)
        return qs

    def perform_create(self, serializer):
        course = serializer.save(author=self.request.user, institution=self.request.user.institution)

        # 未上传封面 → 后台线程提取第一帧
        if not course.cover_image and course.video_file:
            _extract_cover_async(course.id)

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
        user = self.request.user
        qs = super().get_queryset()
        from users.permissions import is_platform_admin
        from django.db.models import Q
        if not is_platform_admin(user):
            inst = getattr(user, 'institution', None)
            if inst:
                qs = qs.filter(Q(institution=inst) | Q(institution__isnull=True))
            else:
                qs = qs.filter(institution__isnull=True)
        return qs

    def get_permissions(self):
        if self.request.method in ['PATCH', 'PUT', 'DELETE']:
            return [IsAdmin()]
        return [IsMember()]

class AwardEloView(APIView):
    """完成课程后领取 ELO 奖励，每门课仅一次。"""
    permission_classes = [IsMember]

    def post(self, request, pk):
        try:
            course = Course.objects.get(pk=pk)
        except Course.DoesNotExist:
            return Response({'error': '课程不存在'}, status=404)

        progress = VideoProgress.objects.filter(
            user=request.user, course=course, is_finished=True,
        ).first()
        if not progress:
            return Response({'error': '请先完成课程学习'}, status=400)
        if progress.elo_claimed_at:
            return Response({'error': '已领取过该课程奖励'}, status=409)

        from django.utils import timezone
        from django.db.models import F
        User.objects.filter(id=request.user.id).update(elo_score=F('elo_score') + course.elo_reward)
        VideoProgress.objects.filter(pk=progress.pk).update(elo_claimed_at=timezone.now())

        request.user.refresh_from_db()
        return Response({
            'status': 'success',
            'elo_added': course.elo_reward,
            'new_score': request.user.elo_score,
        })


class CourseOutlineView(APIView):
    permission_classes = [IsMember]

    def get(self, request, pk):
        try:
            course = Course.objects.get(pk=pk)
        except Course.DoesNotExist:
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
        try:
            course = Course.objects.get(pk=pk)
        except Course.DoesNotExist:
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
        try:
            course = Course.objects.get(pk=pk)
        except Course.DoesNotExist:
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
        try:
            course = Course.objects.get(pk=pk)
        except Course.DoesNotExist:
            return Response({'error': '课程不存在'}, status=404)

        from .services.task_dispatcher import dispatch_transcription
        dispatch_transcription(course.id)
        return Response({'status': 'processing'})
