from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("quizzes", "0012_remove_knowledgepoint_structural_data_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ContentPipelineTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("task_type", models.CharField(choices=[("ai_parse", "AI 整理解析"), ("ai_generate", "AI 智能命题"), ("bulk_import", "批量题库导入"), ("course_publish", "课程发布流水线"), ("article_publish", "文章发布流水线"), ("other", "其他任务")], default="other", max_length=30, verbose_name="任务类型")),
                ("status", models.CharField(choices=[("draft", "草稿"), ("pending", "待执行"), ("running", "执行中"), ("review", "待审核"), ("completed", "已完成"), ("failed", "失败"), ("cancelled", "已取消")], default="pending", max_length=20, verbose_name="任务状态")),
                ("title", models.CharField(max_length=200, verbose_name="任务标题")),
                ("description", models.TextField(blank=True, verbose_name="任务说明")),
                ("progress", models.PositiveSmallIntegerField(default=0, verbose_name="进度百分比")),
                ("payload", models.JSONField(blank=True, default=dict, verbose_name="输入载荷")),
                ("result", models.JSONField(blank=True, default=dict, verbose_name="输出结果")),
                ("error_message", models.TextField(blank=True, verbose_name="错误信息")),
                ("request_id", models.CharField(blank=True, max_length=80, verbose_name="请求链路 ID")),
                ("started_at", models.DateTimeField(blank=True, null=True, verbose_name="开始时间")),
                ("finished_at", models.DateTimeField(blank=True, null=True, verbose_name="完成时间")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                ("assignee", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_pipeline_tasks", to=settings.AUTH_USER_MODEL, verbose_name="处理人")),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pipeline_tasks", to=settings.AUTH_USER_MODEL, verbose_name="创建人")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="contentpipelinetask",
            index=models.Index(fields=["status", "created_at"], name="quizzes_con_status_29fd52_idx"),
        ),
        migrations.AddIndex(
            model_name="contentpipelinetask",
            index=models.Index(fields=["task_type", "created_at"], name="quizzes_con_task_ty_3366b5_idx"),
        ),
    ]
