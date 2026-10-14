from django.contrib import admin, messages
from core.admin_base import InstitutionContentAdmin, PlatformModelAdmin
from .models import (KnowledgePoint, Question, QuizAttempt, UserQuestionStatus, QuizExam, ExamQuestionResult,
                     KnowledgeEdge, ContentPipelineTask, PromptTemplateVersion, MemorixFieldConfig)

from ai_service import AIService 

@admin.register(KnowledgePoint)
class KnowledgePointAdmin(InstitutionContentAdmin):
    list_display = ('get_tree_name', 'code', 'level', 'institution', 'order', 'created_at')
    list_filter = ('institution', 'level', 'prefix_category')
    search_fields = ('name', 'code', 'description')
    ordering = ('id',)
    
    actions = ['generate_ai_questions']

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from .views_knowledge import _invalidate_tree_cache
        _invalidate_tree_cache(obj)

    def delete_model(self, request, obj):
        from .views_knowledge import _invalidate_tree_cache
        _invalidate_tree_cache(obj)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        from .views_knowledge import _invalidate_tree_cache
        for obj in queryset:
            _invalidate_tree_cache(obj)
        super().delete_queryset(request, queryset)

    def get_tree_name(self, obj):
        indent_map = {'sub': '', 'ch': '— ', 'sec': '—— ', 'kp': '——— '}
        indent = indent_map.get(obj.level, '')
        return f"{indent}{obj.name}"
    get_tree_name.short_description = '知识点名称(树状)'

    @admin.action(description="🤖 AI 批量生成混合题型 (仅对选中考点)")
    def generate_ai_questions(self, request, queryset):
        # 过滤出叶子节点
        kp_queryset = queryset.filter(level='kp')
        
        if not kp_queryset.exists():
            self.message_user(request, "请至少选择一个具体的考点(kp级别)！", level=messages.WARNING)
            return
            
        try:
            # 调用 AI 服务
            count = 0
            for kp in kp_queryset:
                count += AIService.batch_generate_questions(KnowledgePoint.objects.filter(pk=kp.pk), count_per_kp=1, institution=kp.institution)
            self.message_user(request, f"成功为选中的考点生成了 {count} 道题目！", level=messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"生题过程发生错误：{str(e)}", level=messages.ERROR)

@admin.register(Question)
class QuestionAdmin(InstitutionContentAdmin):
    list_display = ('id', 'text', 'q_type', 'difficulty_level', 'knowledge_point', 'created_at')
    list_filter = ('q_type', 'difficulty_level', 'knowledge_point__prefix_category')
    search_fields = ('text', 'knowledge_point__name', 'knowledge_point__code')
    raw_id_fields = ('knowledge_point',)

# 注册其他模型
admin.site.register([QuizAttempt, UserQuestionStatus, QuizExam, ExamQuestionResult,
                     ContentPipelineTask, PromptTemplateVersion], PlatformModelAdmin)


@admin.register(KnowledgeEdge)
class KnowledgeEdgeAdmin(InstitutionContentAdmin):
    institution_lookup = 'source__institution'
    list_display = ('source', 'target', 'edge_type', 'weight', 'is_active')
    list_filter = ('edge_type', 'is_active')
    autocomplete_fields = ('source', 'target')
    search_fields = ('source__name', 'target__name')


@admin.register(MemorixFieldConfig)
class MemorixFieldConfigAdmin(InstitutionContentAdmin):
    list_display = ('institution', 'decay', 'beta_e', 'beta_a', 'eta')
    readonly_fields = ('brier_score', 'reviews_evaluated', 'last_evaluated_at', 'perturbation_param',
                       'perturbation_multiplier', 'perturbation_brier_before', 'perturbation_original_value',
                       'last_perturbed_at', 'perturbation_history', 'created_at', 'updated_at')
