import datetime
import logging
from django.utils import timezone
from django.db.models import Max
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView
from quizzes.models import ContentPipelineTask, PromptTemplateVersion
from quizzes.serializers import ContentPipelineTaskSerializer
from users.permissions import IsAdmin
from core.prompt_manager import PromptManager

logger = logging.getLogger(__name__)


class AdminContentPipelineTaskListCreateView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        from users.permissions import is_platform_admin
        from django.db.models import Q
        qs = ContentPipelineTask.objects.select_related("created_by", "assignee").all()
        if not is_platform_admin(request.user):
            inst = getattr(request.user, 'institution', None)
            if inst:
                qs = qs.filter(Q(created_by__institution=inst) | Q(created_by__institution__isnull=True))
            else:
                qs = qs.filter(created_by__institution__isnull=True)
        status_filter = str(request.query_params.get("status", "")).strip()
        task_type = str(request.query_params.get("task_type", "")).strip()
        search = str(request.query_params.get("search", "")).strip()

        if status_filter and status_filter != "all":
            qs = qs.filter(status=status_filter)
        if task_type and task_type != "all":
            qs = qs.filter(task_type=task_type)
        if search:
            qs = qs.filter(title__icontains=search)

        total = qs.count()
        try:
            page = max(int(request.query_params.get("page", 1) or 1), 1)
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = min(max(int(request.query_params.get("page_size", 20) or 20), 1), 100)
        except (TypeError, ValueError):
            page_size = 20
        offset = (page - 1) * page_size
        items = qs[offset:offset + page_size]

        return Response({
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size,
            "results": ContentPipelineTaskSerializer(items, many=True).data,
        })

    def post(self, request):
        serializer = ContentPipelineTaskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = serializer.save(
            created_by=request.user,
            request_id=getattr(request, "request_id", ""),
        )
        if task.status == "running" and not task.started_at:
            task.started_at = timezone.now()
            task.save(update_fields=["started_at", "updated_at"])
        if task.status in {"completed", "failed", "cancelled"} and not task.finished_at:
            task.finished_at = timezone.now()
            task.save(update_fields=["finished_at", "updated_at"])
        return Response(ContentPipelineTaskSerializer(task).data, status=201)


class AdminContentPipelineTaskDetailView(APIView):
    permission_classes = [IsAdmin]

    def get_object(self, pk):
        return get_object_or_404(ContentPipelineTask.objects.select_related("created_by", "assignee"), pk=pk)

    def get(self, request, pk):
        task = self.get_object(pk)
        return Response(ContentPipelineTaskSerializer(task).data)

    def patch(self, request, pk):
        task = self.get_object(pk)
        serializer = ContentPipelineTaskSerializer(task, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        task = serializer.save()

        if task.status == "running" and not task.started_at:
            task.started_at = timezone.now()
        if task.status in {"completed", "failed", "cancelled"} and not task.finished_at:
            task.finished_at = timezone.now()
        if task.status == "completed":
            task.progress = 100
        task.save(update_fields=["started_at", "finished_at", "progress", "updated_at"])
        return Response(ContentPipelineTaskSerializer(task).data)

    def delete(self, request, pk):
        task = self.get_object(pk)
        task.delete()
        return Response(status=204)


class AdminContentPipelineMetricsView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        try:
            days = int(request.query_params.get("days", 14))
        except (TypeError, ValueError):
            days = 14
        days = max(1, min(days, 90))

        since = timezone.now() - datetime.timedelta(days=days)
        qs = ContentPipelineTask.objects.filter(
            task_type="ai_generate",
            created_at__gte=since,
        ).only("status", "result", "error_message", "created_at")

        total = qs.count()
        status_counter = {
            "completed": 0,
            "failed": 0,
            "running": 0,
            "review": 0,
            "pending": 0,
            "cancelled": 0,
            "draft": 0,
        }
        error_counter = {}
        daily_counter = {}

        tasks_with_pipeline = 0
        schema_ok_count = 0
        review_passed_sum = 0
        review_rejected_sum = 0
        author_windows_sum = 0
        author_candidates_sum = 0

        for task in qs:
            status = str(task.status or "").strip()
            if status in status_counter:
                status_counter[status] += 1

            day_key = task.created_at.astimezone(timezone.get_current_timezone()).strftime("%Y-%m-%d")
            day_item = daily_counter.setdefault(day_key, {"date": day_key, "total": 0, "completed": 0, "failed": 0})
            day_item["total"] += 1
            if status == "completed":
                day_item["completed"] += 1
            elif status == "failed":
                day_item["failed"] += 1

            if status == "failed":
                err = str(task.error_message or "未知错误").strip()[:120]
                error_counter[err] = error_counter.get(err, 0) + 1

            result = task.result if isinstance(task.result, dict) else {}
            pipeline = result.get("pipeline") if isinstance(result, dict) else None
            if not isinstance(pipeline, dict):
                continue

            tasks_with_pipeline += 1
            if pipeline.get("schema_ok") is True:
                schema_ok_count += 1
            review_passed_sum += int(pipeline.get("review_passed") or 0)
            review_rejected_sum += int(pipeline.get("review_rejected") or 0)
            author_windows_sum += int(pipeline.get("author_windows") or 0)
            author_candidates_sum += int(pipeline.get("author_candidates") or 0)

        completed = status_counter["completed"]
        failed = status_counter["failed"]
        completion_rate = round((completed / total) * 100, 2) if total else 0.0
        fail_rate = round((failed / total) * 100, 2) if total else 0.0

        review_total = review_passed_sum + review_rejected_sum
        review_reject_rate = round((review_rejected_sum / review_total) * 100, 2) if review_total else 0.0
        schema_ok_rate = round((schema_ok_count / tasks_with_pipeline) * 100, 2) if tasks_with_pipeline else 0.0

        top_errors = sorted(
            [{"error": key, "count": val} for key, val in error_counter.items()],
            key=lambda item: item["count"],
            reverse=True,
        )[:5]
        daily = [daily_counter[key] for key in sorted(daily_counter.keys())]

        return Response(
            {
                "window_days": days,
                "overview": {
                    "total": total,
                    "completed": completed,
                    "failed": failed,
                    "running": status_counter["running"],
                    "review": status_counter["review"],
                    "pending": status_counter["pending"],
                    "cancelled": status_counter["cancelled"],
                    "draft": status_counter["draft"],
                    "completion_rate": completion_rate,
                    "fail_rate": fail_rate,
                },
                "pipeline_quality": {
                    "tasks_with_pipeline": tasks_with_pipeline,
                    "schema_ok_rate": schema_ok_rate,
                    "review_reject_rate": review_reject_rate,
                    "avg_author_windows": round(author_windows_sum / tasks_with_pipeline, 2) if tasks_with_pipeline else 0.0,
                    "avg_author_candidates": round(author_candidates_sum / tasks_with_pipeline, 2) if tasks_with_pipeline else 0.0,
                    "avg_review_passed": round(review_passed_sum / tasks_with_pipeline, 2) if tasks_with_pipeline else 0.0,
                },
                "top_errors": top_errors,
                "daily": daily,
            }
        )


class AdminContentPipelineTaskRetryView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, pk):
        from users.permissions import is_platform_admin
        from django.db.models import Q
        if is_platform_admin(request.user):
            source = get_object_or_404(ContentPipelineTask, pk=pk)
        else:
            inst = request.user.institution
            if inst:
                source = get_object_or_404(ContentPipelineTask, Q(pk=pk) & (Q(created_by__institution=inst) | Q(created_by__institution__isnull=True)))
            else:
                source = get_object_or_404(ContentPipelineTask, pk=pk, created_by__institution__isnull=True)
        new_task = ContentPipelineTask.objects.create(
            task_type=source.task_type,
            status="pending",
            title=f"[重试] {source.title}",
            description=source.description,
            payload=source.payload or {},
            created_by=request.user,
            assignee=source.assignee,
            request_id=getattr(request, "request_id", ""),
        )
        return Response(ContentPipelineTaskSerializer(new_task).data, status=201)


class AdminPromptTemplateListView(APIView):
    """列出某 namespace 下的所有 prompt 模板文件。"""
    permission_classes = [IsAdmin]

    def get(self, request):
        namespace = str(request.query_params.get("namespace", "quizzes")).strip() or "quizzes"
        try:
            names = PromptManager.list_prompts(namespace)
        except Exception:
            names = []

        version_map = {}
        try:
            for t in PromptTemplateVersion.objects.filter(
                namespace=namespace, template_name__in=names
            ).values("template_name").annotate(max_ver=Max("version")):
                version_map[t["template_name"]] = t["max_ver"]
        except Exception:
            pass

        items = [
            {"namespace": namespace, "template_name": n,
             "latest_version": version_map.get(n, 1)}
            for n in names
        ]
        return Response({"namespace": namespace, "results": items})


class AdminPromptTemplateDetailView(APIView):
    """读取/保存单个 prompt 模板文件。"""
    permission_classes = [IsAdmin]

    def get(self, request):
        namespace = str(request.query_params.get("namespace", "quizzes")).strip() or "quizzes"
        template_name = str(request.query_params.get("template_name", "")).strip()
        if not template_name:
            return Response({"error": "缺少 template_name"}, status=400)
        path = PromptManager._resolve_path(namespace, template_name)
        if not path:
            return Response({"error": "模板不存在"}, status=404)
        content = PromptManager.get_prompt(namespace, template_name)

        # 读取版本历史
        history = []
        try:
            rows = PromptTemplateVersion.objects.filter(
                namespace=namespace, template_name=template_name
            ).order_by("-version", "-id")[:20]
            history = [
                {"id": r.id, "version": r.version, "change_note": r.change_note,
                 "created_by_username": getattr(r.created_by, "username", ""),
                 "created_at": r.created_at}
                for r in rows
            ]
        except Exception:
            pass

        return Response({
            "namespace": namespace,
            "template_name": template_name,
            "content": content,
            "latest_version": history[0]["version"] if history else 1,
            "history": history,
        })

    def put(self, request):
        namespace = str(request.data.get("namespace", "quizzes")).strip() or "quizzes"
        template_name = str(request.data.get("template_name", "")).strip()
        content = str(request.data.get("content", ""))
        change_note = str(request.data.get("change_note", "")).strip()
        if not template_name:
            return Response({"error": "缺少 template_name"}, status=400)

        path = PromptManager._resolve_path(namespace, template_name)
        if not path:
            return Response({"error": "模板不存在"}, status=404)

        # 先创建版本记录，再写文件（DB 失败时文件不会脏写）
        try:
            latest = PromptTemplateVersion.objects.filter(
                namespace=namespace, template_name=template_name
            ).order_by("-version").values_list("version", flat=True).first()
            next_ver = (latest or 0) + 1
            row = PromptTemplateVersion.objects.create(
                namespace=namespace,
                template_name=template_name,
                version=next_ver,
                content=content,
                change_note=change_note,
                created_by=request.user if request.user.is_authenticated else None,
            )
            saved = {"id": row.id, "version": next_ver, "change_note": change_note}
        except Exception:
            saved = {"version": 1, "change_note": change_note}

        path.write_text(content, encoding='utf-8')

        return Response({"saved": saved, "detail": {
            "namespace": namespace, "template_name": template_name,
            "content": content, "latest_version": saved["version"],
        }})


class AdminPromptTemplateRollbackView(APIView):
    """回滚 prompt 模板到指定版本。"""
    permission_classes = [IsAdmin]

    def post(self, request):
        namespace = str(request.data.get("namespace", "quizzes")).strip() or "quizzes"
        template_name = str(request.data.get("template_name", "")).strip()
        version_id = request.data.get("version_id")
        if not template_name or version_id is None:
            return Response({"error": "缺少回滚参数"}, status=400)

        target = PromptTemplateVersion.objects.filter(
            namespace=namespace, template_name=template_name, id=int(version_id)
        ).first()
        if not target:
            return Response({"error": "目标版本不存在"}, status=404)

        path = PromptManager._resolve_path(namespace, template_name)
        if not path:
            return Response({"error": "模板文件不存在"}, status=404)

        # 先创建新版本记录，再写文件
        latest = PromptTemplateVersion.objects.filter(
            namespace=namespace, template_name=template_name
        ).order_by("-version").values_list("version", flat=True).first()
        next_ver = (latest or 0) + 1
        row = PromptTemplateVersion.objects.create(
            namespace=namespace,
            template_name=template_name,
            version=next_ver,
            content=target.content,
            change_note=f"回滚至 v{target.version}",
            created_by=request.user if request.user.is_authenticated else None,
        )
        path.write_text(target.content, encoding='utf-8')
        return Response({
            "rollback": {"id": row.id, "version": next_ver, "rollback_source_version": target.version},
            "detail": {"namespace": namespace, "template_name": template_name, "content": target.content},
        })
