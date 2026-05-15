from django.db import models
from django.conf import settings

from quizzes.models import KnowledgePoint

class Article(models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField(help_text="支持 Markdown 和 LaTeX 格式")
    knowledge_point = models.ForeignKey(KnowledgePoint, on_delete=models.SET_NULL, null=True, blank=True, related_name='articles', verbose_name="挂载知识点")
    author_display_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="发布人名称")
    tags = models.JSONField(default=list, blank=True, help_text="文章标签列表")
    cover_image = models.ImageField(upload_to='article_covers/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True)
    views = models.PositiveIntegerField(default=0, verbose_name="阅读量")
    institution = models.ForeignKey("users.Institution", on_delete=models.SET_NULL, null=True, blank=True, related_name="articles", verbose_name="所属机构")

    def __str__(self):
        return self.title
