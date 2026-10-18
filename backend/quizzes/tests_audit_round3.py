import uuid
from datetime import timedelta

from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from quizzes.models import (
    KnowledgeEdge,
    KnowledgePoint,
    Question,
    UserQuestionStatus,
)
from quizzes.serializers import QuestionListSerializer
from quizzes.services.memorix_scheduler import build_adaptive_question_ids
from users.models import CourseStudentStatus, Institution, User


class AuditRound3Base(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.content_inst = Institution.objects.create(
            name="科晟内容", slug="content-audit", contact_name="C", contact_email="c@example.com",
        )
        self.other_inst = Institution.objects.create(
            name="历史机构", slug="other-audit", contact_name="O", contact_email="o@example.com",
        )
        self.admins = [
            User.objects.create_superuser(username=f"operator{i}", email=f"op{i}@example.com", password="Pass12345!")
            for i in range(2)
        ]
        actors = [str(uuid.uuid4()), str(uuid.uuid4())]
        self.config = override_settings(
            UNIMIND_CONTENT_INSTITUTION_ID=str(self.content_inst.id),
            UNIMIND_DIRECTUS_ADMIN_MAP=dict(zip(actors, [admin.pk for admin in self.admins])),
        )
        self.config.enable()
        self.addCleanup(self.config.disable)
        cache.clear()

    def make_student(self, institution=None, username="student"):
        user = User.objects.create_user(username=username, password="Pass12345!", institution=institution)
        CourseStudentStatus.objects.create(user=user, is_course_student=True)
        return user

    def make_kp(self, code, institution=None, parent=None, level="kp", subject="金融431"):
        return KnowledgePoint.objects.create(
            code=code, name=code, level=level, parent=parent, subject=subject,
            institution=institution if institution is not None else self.content_inst,
        )

    def make_question(self, kp, institution=None):
        return Question.objects.create(
            text=f"题目-{kp.code if kp else '无知识点'}",
            q_type="objective",
            correct_answer="A",
            knowledge_point=kp,
            institution=institution if institution is not None else self.content_inst,
        )


class KnowledgeEdgeAuditTests(AuditRound3Base):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.admins[0])
        self.source = self.make_kp("KP-A")
        self.target = self.make_kp("KP-B")

    def test_b20_single_edge_create_returns_created(self):
        response = self.client.post(
            "/api/quizzes/knowledge-edges/",
            {"source": self.source.pk, "target": self.target.pk, "edge_type": "prerequisite", "weight": 0.6},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(KnowledgeEdge.objects.filter(
            source=self.source, target=self.target, edge_type="prerequisite",
            source_type="manual", institution=self.content_inst,
        ).exists())

    def test_b21_bulk_does_not_overwrite_tree_edge(self):
        edge = KnowledgeEdge.objects.create(
            source=self.source, target=self.target, edge_type="contains",
            weight=0.8, source_type="tree", institution=self.content_inst,
        )
        response = self.client.post(
            "/api/quizzes/knowledge-edges/bulk/",
            {"edges": [{
                "source": self.source.pk, "target": self.target.pk,
                "edge_type": "contains", "weight": 0.1,
            }]},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        edge.refresh_from_db()
        self.assertEqual(edge.source_type, "tree")
        self.assertEqual(edge.weight, 0.8)
        self.assertEqual(response.data["created"], 0)
        self.assertEqual(response.data["skipped"], 1)

    def test_b21_tree_edge_update_is_forbidden(self):
        edge = KnowledgeEdge.objects.create(
            source=self.source, target=self.target, edge_type="contains",
            weight=0.8, source_type="tree", institution=self.content_inst,
        )
        response = self.client.patch(
            f"/api/quizzes/knowledge-edges/{edge.pk}/", {"weight": 0.1}, format="json",
        )
        self.assertEqual(response.status_code, 403)
        edge.refresh_from_db()
        self.assertEqual(edge.weight, 0.8)

    def test_b21_single_create_cannot_duplicate_tree_edge(self):
        edge = KnowledgeEdge.objects.create(
            source=self.source, target=self.target, edge_type="contains",
            weight=0.8, source_type="tree", institution=self.content_inst,
        )
        response = self.client.post(
            "/api/quizzes/knowledge-edges/",
            {"source": self.source.pk, "target": self.target.pk, "edge_type": "contains", "weight": 0.2},
            format="json",
        )
        self.assertIn(response.status_code, (400, 403), response.data)
        edge.refresh_from_db()
        self.assertEqual(edge.source_type, "tree")
        self.assertEqual(edge.weight, 0.8)

    def test_b21_update_cannot_collide_with_tree_edge(self):
        KnowledgeEdge.objects.create(
            source=self.source, target=self.target, edge_type="contains",
            weight=0.8, source_type="tree", institution=self.content_inst,
        )
        other = self.make_kp("KP-C")
        manual = KnowledgeEdge.objects.create(
            source=self.source, target=other, edge_type="contains",
            weight=0.5, source_type="manual", institution=self.content_inst,
        )
        response = self.client.patch(
            f"/api/quizzes/knowledge-edges/{manual.pk}/", {"target": self.target.pk}, format="json",
        )
        self.assertIn(response.status_code, (400, 403), response.data)
        manual.refresh_from_db()
        self.assertEqual(manual.target_id, other.pk)

    def test_b21_source_type_is_server_controlled(self):
        edge = KnowledgeEdge.objects.create(
            source=self.source, target=self.target, edge_type="similar",
            weight=0.5, source_type="manual", institution=self.content_inst,
        )
        response = self.client.patch(
            f"/api/quizzes/knowledge-edges/{edge.pk}/", {"source_type": "llm"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        edge.refresh_from_db()
        self.assertEqual(edge.source_type, "manual")


class KnowledgePointAuditTests(AuditRound3Base):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.admins[0])

    def test_b22_parent_cannot_be_self_or_descendant(self):
        root = self.make_kp("SUB-1", level="sub")
        child = self.make_kp("SEC-1", parent=root, level="sec")
        grandchild = self.make_kp("KP-1", parent=child)

        response = self.client.patch(
            f"/api/quizzes/knowledge-points/{root.pk}/", {"parent": grandchild.pk}, format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        response = self.client.patch(
            f"/api/quizzes/knowledge-points/{child.pk}/", {"parent": child.pk}, format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)

        root.refresh_from_db()
        child.refresh_from_db()
        self.assertIsNone(root.parent_id)
        self.assertEqual(child.parent_id, root.pk)

    def test_p08_tree_list_query_count_does_not_grow_with_depth(self):
        student = self.make_student()
        self.client.force_authenticate(user=student)
        root = self.make_kp("SUB-1", level="sub")
        self.make_question(root)

        self.client.get("/api/quizzes/knowledge-points/")
        cache.clear()
        with CaptureQueriesContext(connection) as shallow:
            response = self.client.get("/api/quizzes/knowledge-points/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data), 1)

        child = self.make_kp("SEC-1", parent=root, level="sec")
        grandchild = self.make_kp("KP-1", parent=child)
        self.make_question(grandchild)
        cache.clear()
        with CaptureQueriesContext(connection) as deep:
            response = self.client.get("/api/quizzes/knowledge-points/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data[0]["children"][0]["children"][0]["id"], grandchild.pk)
        self.assertEqual(len(shallow), len(deep))

    def test_p08_question_detail_uses_compact_knowledge_point(self):
        kp = self.make_kp("KP-1")
        question = self.make_question(kp)
        data = QuestionListSerializer(question).data
        detail = data["knowledge_point_detail"]
        self.assertEqual(detail["name"], kp.name)
        self.assertNotIn("children", detail)
        self.assertNotIn("questions_count", detail)


class MemorixAuditTests(AuditRound3Base):
    def setUp(self):
        super().setUp()
        self.student = self.make_student(institution=self.other_inst)
        self.client.force_authenticate(user=self.student)

    def test_b25_favorite_rejects_out_of_scope_question(self):
        kp = self.make_kp("KP-OUT", institution=self.other_inst)
        question = self.make_question(kp, institution=self.other_inst)
        response = self.client.post(
            "/api/quizzes/favorite/toggle/", {"question_id": question.pk}, format="json",
        )
        self.assertEqual(response.status_code, 404, response.data)
        self.assertFalse(UserQuestionStatus.objects.filter(user=self.student, question=question).exists())

    def test_b25_invalid_question_id_is_not_a_server_error(self):
        response = self.client.post(
            "/api/quizzes/favorite/toggle/", {"question_id": "not-an-id"}, format="json",
        )
        self.assertIn(response.status_code, (400, 404))

    def test_b25_valid_favorite_still_works(self):
        kp = self.make_kp("KP-IN")
        question = self.make_question(kp)
        response = self.client.post(
            "/api/quizzes/favorite/toggle/", {"question_id": question.pk}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["is_favorite"])
        self.assertTrue(UserQuestionStatus.objects.filter(user=self.student, question=question).exists())

    def test_b26_stats_ignore_favorites_and_out_of_scope_statuses(self):
        now = timezone.now()
        due_q = self.make_question(self.make_kp("KP-DUE"))
        risk_q = self.make_question(self.make_kp("KP-RISK"))
        new_q = self.make_question(self.make_kp("KP-NEW"))
        mastered_q = self.make_question(self.make_kp("KP-MASTERED"))
        out_q = self.make_question(self.make_kp("KP-OUT", institution=self.other_inst), institution=self.other_inst)

        favorite = UserQuestionStatus.objects.create(user=self.student, question=new_q, is_favorite=True)
        due = UserQuestionStatus.objects.create(
            user=self.student, question=due_q, reps=1, stability=2.0, last_review=now - timedelta(days=2),
        )
        risk = UserQuestionStatus.objects.create(
            user=self.student, question=risk_q, reps=1, stability=2.0, last_review=now - timedelta(days=1),
        )
        mastered = UserQuestionStatus.objects.create(
            user=self.student, question=mastered_q, is_mastered=True,
            stability=2.0, last_review=now - timedelta(days=2),
        )
        out = UserQuestionStatus.objects.create(
            user=self.student, question=out_q, reps=1, stability=2.0, last_review=now - timedelta(days=2),
        )
        UserQuestionStatus.objects.filter(pk=favorite.pk).update(next_review_at=now - timedelta(days=1))
        UserQuestionStatus.objects.filter(pk=due.pk).update(next_review_at=now - timedelta(days=1))
        UserQuestionStatus.objects.filter(pk=risk.pk).update(next_review_at=now + timedelta(days=1))
        UserQuestionStatus.objects.filter(pk=mastered.pk).update(next_review_at=now - timedelta(days=1))
        UserQuestionStatus.objects.filter(pk=out.pk).update(next_review_at=now - timedelta(days=1))

        response = self.client.get("/api/quizzes/stats/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["review_goal"], 1)
        self.assertEqual(response.data["at_risk_count"], 1)
        self.assertEqual(response.data["new_questions"], 1)

    def test_b26_adaptive_selection_ignores_unanswered_favorites(self):
        favorite_q = self.make_question(self.make_kp("KP-FAV"))
        UserQuestionStatus.objects.create(user=self.student, question=favorite_q, is_favorite=True)

        result = build_adaptive_question_ids(
            self.student,
            limit=10,
            base_queryset=Question.objects.filter(institution_id=self.content_inst.pk),
            preference="review_first",
        )

        self.assertEqual(result["meta"]["pool"]["due"], 0)
        self.assertEqual(result["meta"]["pool"]["new"], 1)
        self.assertIn(favorite_q.pk, result["question_ids"])

    def test_p07_mastery_query_count_does_not_grow_with_statuses(self):
        def make_status(index):
            kp = self.make_kp(f"KP-{index}")
            question = self.make_question(kp)
            return UserQuestionStatus.objects.create(
                user=self.student, question=question, stability=5.0,
                last_review=timezone.now() - timedelta(days=1),
            )

        make_status(1)
        self.client.get("/api/users/me/knowledge-mastery/")
        with CaptureQueriesContext(connection) as shallow:
            response = self.client.get("/api/users/me/knowledge-mastery/")
        self.assertEqual(response.status_code, 200, response.data)
        for index in range(2, 6):
            make_status(index)
        with CaptureQueriesContext(connection) as deep:
            response = self.client.get("/api/users/me/knowledge-mastery/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(shallow), len(deep))


class AdjacencyCacheAuditTests(AuditRound3Base):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.admins[0])

    def test_b28_bulk_edge_change_invalidates_adjacency_cache(self):
        source = self.make_kp("KP-A")
        target = self.make_kp("KP-B")
        cache.set("memorix:adj", [("cached", [])], 300)
        cache.set("memorix:field:adj_in", [("cached", [])], 300)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/api/quizzes/knowledge-edges/bulk/",
                {"edges": [{
                    "source": source.pk, "target": target.pk,
                    "edge_type": "similar", "weight": 0.5,
                }]},
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(cache.get("memorix:adj"))
        self.assertIsNone(cache.get("memorix:field:adj_in"))

    def test_b28_tree_change_invalidates_adjacency_cache(self):
        parent = self.make_kp("SEC-1", level="sec")
        cache.set("memorix:adj", [("cached", [])], 300)
        cache.set("memorix:field:adj_in", [("cached", [])], 300)
        with self.captureOnCommitCallbacks(execute=True):
            self.make_kp("KP-1", parent=parent)
        self.assertIsNone(cache.get("memorix:adj"))
        self.assertIsNone(cache.get("memorix:field:adj_in"))

    def test_b28_tree_delete_invalidates_adjacency_cache(self):
        parent = self.make_kp("SEC-1", level="sec")
        self.make_kp("KP-1", parent=parent)
        cache.set("memorix:adj", [("cached", [])], 300)
        cache.set("memorix:field:adj_in", [("cached", [])], 300)
        with self.captureOnCommitCallbacks(execute=True):
            parent.delete()
        self.assertIsNone(cache.get("memorix:adj"))
        self.assertIsNone(cache.get("memorix:field:adj_in"))
