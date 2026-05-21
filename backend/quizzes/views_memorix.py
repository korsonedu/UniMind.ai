import datetime
import logging
import math
import os
from collections import defaultdict
from django.conf import settings
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView
from quizzes.models import (
    UserQuestionStatus, PersonalizedMockExam, ReviewLog, FSRSProfile,
)
from quizzes.serializers import UserQuestionStatusSerializer, QuizExamSerializer
from users.views import IsMember
from users.permissions import HasQuota
from users.quota import increment_quota
from quizzes.services.wrong_question_insights import build_wrong_question_insights
from quizzes.services.memorix_scheduler import get_memorix_session_plan, build_adaptive_question_ids
from quizzes.tasks import generate_personalized_pdf_mock_exam

logger = logging.getLogger(__name__)


def _build_media_abs_url(request, raw_path: str) -> str:
    text = str(raw_path or "").strip()
    if not text:
        return ""
    if text.startswith("http://") or text.startswith("https://"):
        return text
    normalized = text.replace("\\", "/")
    marker = "/media/"
    if marker in normalized:
        rel = normalized.split(marker, 1)[1]
    else:
        rel = normalized.lstrip("/")
    return request.build_absolute_uri(f"/media/{rel}")


class ToggleFavoriteView(APIView):
    permission_classes = [IsMember]
    def post(self, request):
        q_id = request.data.get('question_id')
        status_obj, _ = UserQuestionStatus.objects.get_or_create(user=request.user, question_id=q_id)
        from django.db.models import F
        UserQuestionStatus.objects.filter(id=status_obj.id).update(is_favorite=~F('is_favorite'))
        status_obj.refresh_from_db(fields=['is_favorite'])
        return Response({'is_favorite': status_obj.is_favorite})


class ToggleMasteredView(APIView):
    permission_classes = [IsMember]
    def post(self, request):
        q_id = request.data.get('question_id')
        status_obj, _ = UserQuestionStatus.objects.get_or_create(user=request.user, question_id=q_id)
        from django.db.models import F
        UserQuestionStatus.objects.filter(id=status_obj.id).update(is_mastered=~F('is_mastered'))
        status_obj.refresh_from_db(fields=['is_mastered'])
        return Response({'is_mastered': status_obj.is_mastered})


class WrongQuestionListView(generics.ListAPIView):
    serializer_class = UserQuestionStatusSerializer
    permission_classes = [IsMember]
    def get_queryset(self):
        return UserQuestionStatus.objects.filter(user=self.request.user, wrong_count__gt=0).order_by('-wrong_count')


class WrongQuestionInsightsView(APIView):
    permission_classes = [IsMember]

    def get(self, request):
        try:
            top_k = int(request.query_params.get('top_k', 3))
        except (ValueError, TypeError):
            top_k = 3
        top_k = max(1, min(top_k, 8))
        payload = build_wrong_question_insights(user=request.user, top_k=top_k)
        return Response(payload)


class FavoriteQuestionListView(generics.ListAPIView):
    serializer_class = UserQuestionStatusSerializer
    permission_classes = [IsMember]
    def get_queryset(self):
        return UserQuestionStatus.objects.filter(user=self.request.user, is_favorite=True)


class QuizStatsView(APIView):
    permission_classes = [IsMember]

    def get(self, request):
        user = request.user
        now = timezone.now()

        from quizzes.models import UserQuestionStatus, Question

        status_qs = UserQuestionStatus.objects.filter(user=user)

        review_count = status_qs.filter(next_review_at__lte=now).count()

        at_risk_count = status_qs.filter(
            stability__lt=7,
            next_review_at__lte=now + datetime.timedelta(days=3),
            next_review_at__gt=now
        ).count()

        attempted_ids = status_qs.values_list('question_id', flat=True)
        new_questions_count = Question.objects.exclude(id__in=attempted_ids).count()

        plan = get_memorix_session_plan(user=user, minutes=25)

        return Response({
            'review_goal': review_count,
            'new_questions': new_questions_count,
            'at_risk_count': at_risk_count,
            'recommended_questions': plan['recommended_questions'],
            'estimated_minutes': plan['estimated_minutes'],
            'weak_focus_count': plan['weak_focus_count'],
        })


class MemorixCurveView(APIView):
    permission_classes = [IsMember]

    def get(self, request):
        try:
            window_days = int(request.query_params.get("window_days", 90))
        except (ValueError, TypeError):
            window_days = 90
        window_days = max(30, min(window_days, 365))

        now = timezone.now()
        start_time = now - datetime.timedelta(days=window_days)
        logs = list(
            ReviewLog.objects.filter(user=request.user, review_time__gte=start_time)
            .order_by("review_time")
            .values("review_time", "grade", "predicted_retrievability")
        )

        profile = FSRSProfile.objects.filter(user=request.user).first()
        if not logs:
            return Response(
                {
                    "window_days": window_days,
                    "time_series": [],
                    "fit_curve": [],
                    "metrics": {
                        "review_count": 0,
                        "rmse": None,
                        "mae": None,
                        "avg_predicted": None,
                        "avg_actual": None,
                    },
                    "profile": {
                        "last_optimized_at": getattr(profile, "last_optimized_at", None),
                        "current_loss": getattr(profile, "current_loss", None),
                        "total_reviews_used": int(getattr(profile, "total_reviews_used", 0) or 0),
                    },
                }
            )

        daily = defaultdict(lambda: {"pred_sum": 0.0, "actual_sum": 0.0, "count": 0})
        bins = [{"pred_sum": 0.0, "actual_sum": 0.0, "count": 0} for _ in range(5)]
        abs_error_sum = 0.0
        sq_error_sum = 0.0
        pred_total = 0.0
        actual_total = 0.0

        for row in logs:
            pred = float(row.get("predicted_retrievability") or 0.0)
            pred = max(0.0, min(1.0, pred))
            actual = 1.0 if int(row.get("grade") or 1) > 1 else 0.0
            key = row["review_time"].date().isoformat()
            daily[key]["pred_sum"] += pred
            daily[key]["actual_sum"] += actual
            daily[key]["count"] += 1

            idx = min(4, int(pred * 5))
            bins[idx]["pred_sum"] += pred
            bins[idx]["actual_sum"] += actual
            bins[idx]["count"] += 1

            diff = actual - pred
            abs_error_sum += abs(diff)
            sq_error_sum += diff * diff
            pred_total += pred
            actual_total += actual

        time_series = []
        for day_key in sorted(daily.keys()):
            count = daily[day_key]["count"]
            time_series.append(
                {
                    "date": day_key,
                    "predicted": round(daily[day_key]["pred_sum"] / count, 4),
                    "actual": round(daily[day_key]["actual_sum"] / count, 4),
                    "count": count,
                }
            )

        fit_curve = []
        for index, bucket in enumerate(bins):
            if bucket["count"] <= 0:
                continue
            fit_curve.append(
                {
                    "bucket": f"{index * 0.2:.1f}-{(index + 1) * 0.2:.1f}",
                    "predicted": round(bucket["pred_sum"] / bucket["count"], 4),
                    "actual": round(bucket["actual_sum"] / bucket["count"], 4),
                    "count": bucket["count"],
                }
            )

        total = len(logs)
        rmse = math.sqrt(sq_error_sum / total) if total else None
        mae = abs_error_sum / total if total else None

        return Response(
            {
                "window_days": window_days,
                "time_series": time_series,
                "fit_curve": fit_curve,
                "metrics": {
                    "review_count": total,
                    "rmse": round(rmse, 4) if rmse is not None else None,
                    "mae": round(mae, 4) if mae is not None else None,
                    "avg_predicted": round(pred_total / total, 4) if total else None,
                    "avg_actual": round(actual_total / total, 4) if total else None,
                },
                "profile": {
                    "last_optimized_at": getattr(profile, "last_optimized_at", None),
                    "current_loss": getattr(profile, "current_loss", None),
                    "total_reviews_used": int(getattr(profile, "total_reviews_used", 0) or 0),
                    "weights_preview": (getattr(profile, "weights", []) or [])[:5],
                },
            }
        )


class MemorixOptimizationHistoryView(APIView):
    permission_classes = [IsMember]

    def get(self, request):
        from quizzes.models import FSRSOptimizationLog
        rows = FSRSOptimizationLog.objects.filter(user=request.user).order_by("-created_at")[:30]
        return Response(
            {
                "results": [
                    {
                        "id": row.id,
                        "previous_loss": row.previous_loss,
                        "new_loss": row.new_loss,
                        "improvement_ratio": round(float(row.improvement_ratio or 0.0), 6),
                        "reviews_used": row.reviews_used,
                        "accepted": bool(row.accepted),
                        "note": row.note,
                        "created_at": row.created_at,
                    }
                    for row in rows
                ]
            }
        )


class PersonalizedMockExamView(APIView):
    permission_classes = [IsMember, HasQuota]
    quota_resource = 'pdf_export'

    def get(self, request):
        rows = PersonalizedMockExam.objects.filter(user=request.user).order_by("-created_at")[:20]
        data = []
        for row in rows:
            data.append(
                {
                    "id": row.id,
                    "status": row.status,
                    "question_count": row.question_count,
                    "weak_coverage": row.weak_coverage,
                    "error_message": row.error_message,
                    "created_at": row.created_at,
                    "exam_pdf_url": _build_media_abs_url(request, row.exam_pdf),
                    "answer_pdf_url": _build_media_abs_url(request, row.answer_pdf),
                }
            )
        return Response({"results": data})

    def post(self, request):
        record = PersonalizedMockExam.objects.create(
            user=request.user,
            status='processing',
        )
        generate_personalized_pdf_mock_exam.delay(record_id=record.id)
        # 计入 PDF 导出配额
        if request.user.institution:
            increment_quota(request.user.institution, 'pdf_export')

        payload = {
            "id": record.id,
            "status": record.status,
            "question_count": record.question_count,
            "weak_coverage": record.weak_coverage,
            "error_message": record.error_message,
            "created_at": record.created_at,
            "exam_pdf_url": "",
            "answer_pdf_url": "",
        }
        return Response(payload, status=201)

    def delete(self, request):
        exam_id = request.query_params.get('id')
        if not exam_id:
            return Response({"error": "缺少 id 参数"}, status=400)
        row = get_object_or_404(PersonalizedMockExam, id=exam_id, user=request.user)
        for path_str in (row.exam_pdf, row.answer_pdf):
            if path_str and os.path.isfile(path_str):
                try:
                    os.remove(path_str)
                except OSError:
                    pass
        row.delete()
        return Response({"status": "deleted"})
