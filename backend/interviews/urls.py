from django.urls import path

from .views import (
    InterviewFinishView,
    InterviewSessionDetailView,
    InterviewSessionListCreateView,
    InterviewTextTurnView,
    ResumeTuneView,
)


urlpatterns = [
    path("sessions/", InterviewSessionListCreateView.as_view(), name="interview-session-list-create"),
    path("sessions/<int:session_id>/", InterviewSessionDetailView.as_view(), name="interview-session-detail"),
    path("sessions/<int:session_id>/text-turn/", InterviewTextTurnView.as_view(), name="interview-text-turn"),
    path("sessions/<int:session_id>/finish/", InterviewFinishView.as_view(), name="interview-finish"),
    path("resume/tune/", ResumeTuneView.as_view(), name="interview-resume-tune"),
]
