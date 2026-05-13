from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from users.models import User
from .models import InterviewSession, InterviewTurn, ResumeRecord


class InterviewFlowTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="member_interview", password="testpass123", is_member=True)
        self.client.force_authenticate(user=self.user)

    @patch("interviews.views.InterviewAIService.generate_interview_reply")
    @patch("interviews.views.InterviewAIService.annotate_candidate_turn")
    @patch("interviews.views.InterviewAIService.generate_post_interview_radar")
    def test_session_text_turn_and_finish(self, mock_radar, mock_annotate, mock_reply):
        mock_reply.return_value = "请你具体解释一下这个结论背后的机制。"
        mock_annotate.return_value = "回答结构还可以，但缺少关键前提条件。"
        mock_radar.return_value = {
            "radar_scores": {"theory": 82, "logic": 79, "stress": 75, "fluency": 80, "english": 68},
            "overall_feedback": "专业基础不错，建议提升应变细节。",
        }

        create_resp = self.client.post(
            "/api/interviews/sessions/",
            {"session_type": "professional", "interviewer_style": "friendly"},
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        session_id = create_resp.data["id"]

        turn_resp = self.client.post(
            f"/api/interviews/sessions/{session_id}/text-turn/",
            {"text": "我认为货币政策通过利率渠道影响投资和总需求。"},
            format="json",
        )
        self.assertEqual(turn_resp.status_code, status.HTTP_200_OK)
        self.assertIn("reply", turn_resp.data)

        candidate_turn = InterviewTurn.objects.filter(session_id=session_id, speaker="candidate").first()
        self.assertIsNotNone(candidate_turn)
        self.assertTrue((candidate_turn.feedback_for_turn or "").strip())

        finish_resp = self.client.post(f"/api/interviews/sessions/{session_id}/finish/", {}, format="json")
        self.assertEqual(finish_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(finish_resp.data.get("status"), "completed")
        self.assertIn("radar_scores", finish_resp.data)

    @patch("interviews.views.InterviewAIService.tune_resume")
    def test_resume_tune_creates_record_with_file(self, mock_tune):
        mock_tune.return_value = {
            "score": 86,
            "diagnostics": "内容较完整",
            "optimized_content": {"summary": "改进版"},
            "predicted_questions": ["为什么选择金融学？"],
        }
        file_obj = SimpleUploadedFile("resume.txt", b"My resume content", content_type="text/plain")
        resp = self.client.post("/api/interviews/resume/tune/", {"file": file_obj}, format="multipart")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        record_id = resp.data.get("record_id")
        self.assertTrue(record_id)
        row = ResumeRecord.objects.get(id=record_id, user=self.user)
        self.assertIn("resume", row.parsed_content.lower())
