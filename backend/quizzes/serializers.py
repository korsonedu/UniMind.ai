from rest_framework import serializers
from .models import (
    Question, QuizAttempt, KnowledgePoint, UserQuestionStatus, QuizExam, ExamQuestionResult,
    ContentPipelineTask, TeacherExam, StudentExamSubmission, KnowledgePointAnnotation,
    PersonalizedMockExam, PromptTemplateVersion,
)
from users.serializers import UserSerializer

class KnowledgePointSerializer(serializers.ModelSerializer):
    questions_count = serializers.IntegerField(source='questions.count', read_only=True)
    children = serializers.SerializerMethodField()  # 新增：递归获取子节点

    class Meta:
        model = KnowledgePoint
        fields = '__all__'

    def get_children(self, obj):
        # 递归调用自身来序列化子节点，输出完美的 JSON 树
        if obj.children.exists():
            return KnowledgePointSerializer(obj.children.all(), many=True, context=self.context).data
        return []

class QuestionSerializer(serializers.ModelSerializer):
    knowledge_point_detail = KnowledgePointSerializer(source='knowledge_point', read_only=True)
    is_favorite = serializers.SerializerMethodField()
    is_mastered = serializers.SerializerMethodField()
    difficulty_level_display = serializers.CharField(source='get_difficulty_level_display', read_only=True)

    class Meta:
        model = Question
        fields = '__all__'

    def get_is_favorite(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            status = UserQuestionStatus.objects.filter(user=request.user, question=obj).first()
            return status.is_favorite if status else False
        return False

    def get_is_mastered(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            status = UserQuestionStatus.objects.filter(user=request.user, question=obj).first()
            return status.is_mastered if status else False
        return False

class UserQuestionStatusSerializer(serializers.ModelSerializer):
    question_detail = QuestionSerializer(source='question', read_only=True)
    class Meta:
        model = UserQuestionStatus
        fields = '__all__'

class QuizAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuizAttempt
        fields = '__all__'
        read_only_fields = ('user', 'elo_change')

class ExamQuestionResultSerializer(serializers.ModelSerializer):
    question_detail = QuestionSerializer(source='question', read_only=True)
    class Meta:
        model = ExamQuestionResult
        fields = '__all__'

class QuizExamSerializer(serializers.ModelSerializer):
    results = ExamQuestionResultSerializer(many=True, read_only=True)
    created_at_fmt = serializers.DateTimeField(source='created_at', format="%Y-%m-%d %H:%M", read_only=True)

    class Meta:
        model = QuizExam
        fields = '__all__'


class ContentPipelineTaskSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    task_type_display = serializers.CharField(source='get_task_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = ContentPipelineTask
        fields = '__all__'


class TeacherExamSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeacherExam
        fields = '__all__'


class StudentExamSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentExamSubmission
        fields = '__all__'


class KnowledgePointAnnotationSerializer(serializers.ModelSerializer):
    class Meta:
        model = KnowledgePointAnnotation
        fields = '__all__'


class PersonalizedMockExamSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonalizedMockExam
        fields = '__all__'