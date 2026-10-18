from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from quizzes.models import (
    KnowledgePoint,
    Question,
    UserKnowledgeState,
    UserQuestionStatus,
)
from users.models import CourseStudentStatus, Institution, User


class DiagnosticAuditBase(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.content_inst = Institution.objects.create(
            name="科晟内容", slug="content-diag", contact_name="C", contact_email="c@example.com",
        )
        self.other_inst = Institution.objects.create(
            name="历史机构", slug="other-diag", contact_name="O", contact_email="o@example.com",
        )
        self.config = override_settings(UNIMIND_CONTENT_INSTITUTION_ID=str(self.content_inst.id))
        self.config.enable()
        self.addCleanup(self.config.disable)

    def make_student(self, institution=None, username="student"):
        user = User.objects.create_user(username=username, password="Pass12345!", institution=institution)
        CourseStudentStatus.objects.create(user=user, is_course_student=True)
        self.client.force_authenticate(user=user)
        return user

    def make_question(self, institution, q_type="objective", suffix="1"):
        kp = KnowledgePoint.objects.create(
            code=f"KP-{suffix}", name=f"知识点{suffix}", level="kp", institution=institution,
        )
        return Question.objects.create(
            text=f"题目{suffix}",
            q_type=q_type,
            correct_answer="A",
            knowledge_point=kp,
            institution=institution,
        )

    def submit(self, question, answer="A", **extra):
        return self.client.post(
            "/api/users/me/diagnostic/submit/",
            {"answers": [{"question": {"id": question.pk}, "answer": answer}], **extra},
            format="json",
        )


class DiagnosticContentScopeTests(DiagnosticAuditBase):
    def test_generate_uses_content_scope_not_user_institution(self):
        self.make_student(institution=self.other_inst)
        content_q = self.make_question(self.content_inst, suffix="content")
        other_q = self.make_question(self.other_inst, suffix="other")

        response = self.client.post("/api/users/me/diagnostic/generate/", {}, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([item["id"] for item in response.data["questions"]], [content_q.pk])
        self.assertNotIn(other_q.pk, [item["id"] for item in response.data["questions"]])

    def test_student_without_institution_can_generate(self):
        self.make_student(institution=None)
        self.make_question(self.content_inst, suffix="content")

        response = self.client.post("/api/users/me/diagnostic/generate/", {}, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["questions"]), 1)

    def test_reassess_uses_content_scope(self):
        self.make_student(institution=self.other_inst)
        content_q = self.make_question(self.content_inst, suffix="content")
        self.make_question(self.other_inst, suffix="other")

        response = self.client.post("/api/users/me/diagnostic/reassess/", {}, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([item["id"] for item in response.data["questions"]], [content_q.pk])

    def test_submit_rejects_out_of_scope_question(self):
        user = self.make_student(institution=self.other_inst)
        other_q = self.make_question(self.other_inst, suffix="other")

        response = self.submit(other_q)

        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(UserQuestionStatus.objects.filter(user=user, question=other_q).exists())
        self.assertFalse(UserKnowledgeState.objects.filter(user=user).exists())

    def test_submit_accepts_content_scope_and_initializes(self):
        user = self.make_student(institution=self.other_inst)
        content_q = self.make_question(self.content_inst, suffix="content")

        response = self.submit(content_q, answer="A")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["total_score"], 1)
        self.assertTrue(UserQuestionStatus.objects.filter(user=user, question=content_q).exists())
        self.assertTrue(UserKnowledgeState.objects.filter(user=user, knowledge_point=content_q.knowledge_point).exists())
        user.refresh_from_db()
        self.assertTrue(user.has_completed_initial_assessment)

    def test_knowledge_mastery_uses_content_scope(self):
        user = self.make_student(institution=self.other_inst)
        content_q = self.make_question(self.content_inst, suffix="content")
        other_q = self.make_question(self.other_inst, suffix="other")
        last_review = timezone.now() - timedelta(days=1)
        UserQuestionStatus.objects.create(
            user=user, question=content_q, stability=5.0, last_review=last_review,
        )
        UserQuestionStatus.objects.create(
            user=user, question=other_q, stability=5.0, last_review=last_review,
        )

        response = self.client.get("/api/users/me/knowledge-mastery/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn(str(content_q.knowledge_point_id), response.data)
        self.assertNotIn(str(other_q.knowledge_point_id), response.data)


class DiagnosticObjectiveOnlyTests(DiagnosticAuditBase):
    def test_submit_rejects_subjective_question_without_calling_ai(self):
        user = self.make_student(institution=self.other_inst)
        subjective = self.make_question(self.content_inst, q_type="subjective", suffix="subjective")

        with patch("ai_engine.service.AIEngine.call_ai") as call_ai:
            response = self.submit(subjective)

        self.assertEqual(response.status_code, 400, response.data)
        call_ai.assert_not_called()
        self.assertFalse(UserQuestionStatus.objects.filter(user=user).exists())
        self.assertFalse(UserKnowledgeState.objects.filter(user=user).exists())
        user.refresh_from_db()
        self.assertFalse(user.has_completed_initial_assessment)

    def test_mixed_submission_is_rejected_without_partial_writes(self):
        user = self.make_student(institution=self.other_inst)
        objective = self.make_question(self.content_inst, suffix="objective")
        subjective = self.make_question(self.content_inst, q_type="subjective", suffix="subjective")

        response = self.client.post(
            "/api/users/me/diagnostic/submit/",
            {"answers": [
                {"question": {"id": objective.pk}, "answer": "A"},
                {"question": {"id": subjective.pk}, "answer": "A"},
            ]},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(UserQuestionStatus.objects.filter(user=user).exists())
        self.assertFalse(UserKnowledgeState.objects.filter(user=user).exists())
