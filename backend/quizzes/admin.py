from django.contrib import admin, messages
from .models import KnowledgePoint, Question, QuizAttempt, UserQuestionStatus, QuizExam, ExamQuestionResult, KnowledgeEdge

from ai_service import AIService 

@admin.register(KnowledgePoint)
class KnowledgePointAdmin(admin.ModelAdmin):
    list_display = ('get_tree_name', 'code', 'level', 'prefix_category', 'created_at')
    list_filter = ('level', 'prefix_category')
    search_fields = ('name', 'code', 'description')
    ordering = ('id',)
    
    actions = ['generate_ai_questions']

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
            count = AIService.batch_generate_questions(kp_queryset, count_per_kp=1, institution=request.user.institution)
            self.message_user(request, f"成功为选中的考点生成了 {count} 道题目！", level=messages.SUCCESS)
        except Exception as e:
            self.message_user(request, f"生题过程发生错误：{str(e)}", level=messages.ERROR)

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'text', 'q_type', 'difficulty_level', 'knowledge_point', 'created_at')
    list_filter = ('q_type', 'difficulty_level', 'knowledge_point__prefix_category')
    search_fields = ('text', 'knowledge_point__name', 'knowledge_point__code')
    raw_id_fields = ('knowledge_point',)

# 注册其他模型
admin.site.register(QuizAttempt)
admin.site.register(UserQuestionStatus)
admin.site.register(QuizExam)
admin.site.register(ExamQuestionResult)
admin.site.register(KnowledgeEdge)
