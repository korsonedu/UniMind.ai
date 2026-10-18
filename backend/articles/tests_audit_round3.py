import uuid

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient, APITestCase

from articles.models import Article
from users.models import Institution, User


class ArticleAuditBase(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.content_inst = Institution.objects.create(
            name="科晟内容", slug="content-articles", contact_name="C", contact_email="c@example.com",
        )
        other_inst = Institution.objects.create(
            name="历史机构", slug="other-articles", contact_name="O", contact_email="o@example.com",
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
        self.client.force_authenticate(user=self.admins[0])
        self.other_inst = other_inst


class ArticleOwnershipTests(ArticleAuditBase):
    def test_b27_created_article_uses_content_institution_and_stays_visible(self):
        response = self.client.post(
            "/api/articles/",
            {"title": "受管文章", "content": "正文", "tags": ["金融"]},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        article = Article.objects.get(pk=response.data["id"])
        self.assertEqual(article.institution_id, self.content_inst.pk)

        listing = self.client.get("/api/articles/")
        self.assertEqual(listing.status_code, 200, listing.data)
        self.assertEqual(listing.data["total"], 1)
        self.assertEqual(listing.data["articles"][0]["id"], article.pk)


class ArticleTagStatsTests(ArticleAuditBase):
    def test_p09_tag_stats_only_read_tags_and_views(self):
        Article.objects.create(
            title="文章一", content="长正文" * 100,
            tags=["金融", "货币"], views=10, institution=self.content_inst,
        )
        Article.objects.create(
            title="文章二", content="长正文" * 100,
            tags=["金融"], views=5, institution=self.content_inst,
        )

        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/api/articles/")

        self.assertEqual(response.status_code, 200, response.data)
        stats = {item["name"]: item for item in response.data["tag_stats"]}
        self.assertEqual(stats["金融"]["count"], 2)
        self.assertEqual(stats["金融"]["views"], 15)
        self.assertEqual(stats["货币"]["count"], 1)
        self.assertEqual(stats["货币"]["views"], 10)

        tag_queries = [
            query["sql"] for query in queries.captured_queries
            if '"articles_article"."tags"' in query["sql"]
            and '"articles_article"."views"' in query["sql"]
            and '"articles_article"."content"' not in query["sql"]
        ]
        self.assertTrue(tag_queries, "标签统计应按 tags/views 两列读取")
