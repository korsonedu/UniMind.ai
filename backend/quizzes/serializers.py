from rest_framework import serializers
from .models import (
    Question, QuizAttempt, KnowledgePoint, UserQuestionStatus, QuizExam, ExamQuestionResult,
    ContentPipelineTask, KnowledgePointAnnotation, KnowledgeEdge,
    MarketplaceListing,
)
from users.serializers import UserSerializer

class KnowledgePointSerializer(serializers.ModelSerializer):
    questions_count = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgePoint
        fields = ('id', 'code', 'name', 'level', 'prefix_category', 'description', 'parent', 'institution', 'order', 'created_at', 'questions_count', 'children')

    def get_questions_count(self, obj):
        annotated = getattr(obj, '_questions_count', None)
        if annotated is not None:
            return annotated
        return obj.questions.count()

    def get_children(self, obj):
        children = getattr(obj, '_tree_children', None)
        if children is None:
            children = obj.children.all()
        if not children:
            return []
        return KnowledgePointSerializer(children, many=True, context=self.context).data

    def validate_parent(self, value):
        instance = self.instance
        if value is None or instance is None:
            return value
        if value.pk == instance.pk:
            raise serializers.ValidationError('上级知识点不能是自身。')
        seen = set()
        ancestor = value
        while ancestor is not None:
            if ancestor.pk == instance.pk:
                raise serializers.ValidationError('上级知识点不能是当前节点的后代。')
            if ancestor.pk in seen:
                raise serializers.ValidationError('上级知识点层级存在循环。')
            seen.add(ancestor.pk)
            ancestor = ancestor.parent
        return value


class KnowledgePointSummarySerializer(serializers.ModelSerializer):
    """题目内嵌的精简知识点摘要，不展开子树。"""

    class Meta:
        model = KnowledgePoint
        fields = ('id', 'code', 'name', 'level', 'prefix_category', 'description', 'parent', 'institution', 'order', 'created_at')


class QuestionListSerializer(serializers.ModelSerializer):
    """学生端题目列表 serializer — 不含答案/解析等敏感字段。"""
    knowledge_point_detail = KnowledgePointSummarySerializer(source='knowledge_point', read_only=True)
    is_favorite = serializers.SerializerMethodField()
    is_mastered = serializers.SerializerMethodField()
    difficulty_level_display = serializers.CharField(source='get_difficulty_level_display', read_only=True)

    class Meta:
        model = Question
        fields = ('id', 'knowledge_point', 'text', 'q_type', 'subjective_type', 'difficulty_level', 'options', 'difficulty', 'institution', 'created_at', 'knowledge_point_detail', 'is_favorite', 'is_mastered', 'difficulty_level_display')

    def get_is_favorite(self, obj):
        status_map = self.context.get('status_map')
        if status_map is not None:
            s = status_map.get(obj.pk)
            return s.is_favorite if s else False
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            status = UserQuestionStatus.objects.filter(user=request.user, question=obj).first()
            return status.is_favorite if status else False
        return False

    def get_is_mastered(self, obj):
        status_map = self.context.get('status_map')
        if status_map is not None:
            s = status_map.get(obj.pk)
            return s.is_mastered if s else False
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            status = UserQuestionStatus.objects.filter(user=request.user, question=obj).first()
            return status.is_mastered if status else False
        return False

    def to_representation(self, instance):
        data = super().to_representation(instance)
        options = data.get('options')
        if isinstance(options, dict):
            data['options'] = [options[k] for k in sorted(options.keys())]
        return data


class QuestionSerializer(serializers.ModelSerializer):
    """管理员/内部用 serializer — 含完整答案和评分标准。"""
    knowledge_point_detail = KnowledgePointSummarySerializer(source='knowledge_point', read_only=True)
    is_favorite = serializers.SerializerMethodField()
    is_mastered = serializers.SerializerMethodField()
    difficulty_level_display = serializers.CharField(source='get_difficulty_level_display', read_only=True)
    knowledge_point = serializers.PrimaryKeyRelatedField(
        queryset=KnowledgePoint.objects.filter(level='kp'),
        required=True,
        help_text='知识点ID（必填）',
    )

    class Meta:
        model = Question
        fields = ('id', 'knowledge_point', 'text', 'q_type', 'subjective_type', 'difficulty_level', 'grading_points', 'options', 'correct_answer', 'ai_answer', 'rubric', 'difficulty', 'institution', 'created_at', 'knowledge_point_detail', 'is_favorite', 'is_mastered', 'difficulty_level_display')

    def get_is_favorite(self, obj):
        status_map = self.context.get('status_map')
        if status_map is not None:
            s = status_map.get(obj.pk)
            return s.is_favorite if s else False
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            status = UserQuestionStatus.objects.filter(user=request.user, question=obj).first()
            return status.is_favorite if status else False
        return False

    def get_is_mastered(self, obj):
        status_map = self.context.get('status_map')
        if status_map is not None:
            s = status_map.get(obj.pk)
            return s.is_mastered if s else False
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            status = UserQuestionStatus.objects.filter(user=request.user, question=obj).first()
            return status.is_mastered if status else False
        return False

    def to_representation(self, instance):
        data = super().to_representation(instance)
        options = data.get('options')
        if isinstance(options, dict):
            data['options'] = [options[k] for k in sorted(options.keys())]
        return data

class UserQuestionStatusSerializer(serializers.ModelSerializer):
    question_detail = QuestionSerializer(source='question', read_only=True)
    class Meta:
        model = UserQuestionStatus
        fields = ('id', 'user', 'question', 'is_favorite', 'is_mastered', 'wrong_count', 'stability', 'difficulty', 'reps', 'lapses', 'last_review', 'next_review_at', 'last_correct', 'question_detail')

class QuizAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuizAttempt
        fields = ('id', 'user', 'score', 'elo_change', 'is_initial_placement', 'created_at')
        read_only_fields = ('user', 'elo_change')

class ExamQuestionResultSerializer(serializers.ModelSerializer):
    question_detail = QuestionSerializer(source='question', read_only=True)
    class Meta:
        model = ExamQuestionResult
        fields = (
            'id', 'exam', 'details', 'question', 'position', 'user_answer', 'score', 'max_score',
            'feedback', 'analysis', 'is_correct', 'status', 'error_type', 'error_metadata',
            'question_snapshot', 'attempts', 'graded_at', 'question_detail',
        )

class QuizExamSerializer(serializers.ModelSerializer):
    results = ExamQuestionResultSerializer(many=True, read_only=True)
    created_at_fmt = serializers.DateTimeField(source='created_at', format="%Y-%m-%d %H:%M", read_only=True)

    class Meta:
        model = QuizExam
        fields = (
            'id', 'user', 'total_score', 'max_score', 'elo_change', 'summary', 'status',
            'total_questions', 'graded_count', 'failed_count', 'last_error',
            'started_at', 'grading_completed_at', 'notified_at', 'created_at',
            'results', 'created_at_fmt',
        )


class ContentPipelineTaskSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    task_type_display = serializers.CharField(source='get_task_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = ContentPipelineTask
        fields = ('id', 'task_type', 'status', 'title', 'description', 'progress', 'payload', 'result', 'error_message', 'request_id', 'assignee', 'created_by', 'institution', 'started_at', 'finished_at', 'created_at', 'updated_at', 'created_by_username', 'task_type_display', 'status_display')


class KnowledgePointAnnotationSerializer(serializers.ModelSerializer):
    class Meta:
        model = KnowledgePointAnnotation
        fields = ('id', 'user', 'knowledge_point', 'mastery_level', 'priority', 'confidence_score', 'tags', 'note', 'source', 'created_at', 'updated_at')


class KnowledgeEdgeSerializer(serializers.ModelSerializer):
    source_name = serializers.CharField(source='source.name', read_only=True)
    source_code = serializers.CharField(source='source.code', read_only=True)
    target_name = serializers.CharField(source='target.name', read_only=True)
    target_code = serializers.CharField(source='target.code', read_only=True)

    class Meta:
        model = KnowledgeEdge
        fields = (
            'id', 'source', 'source_name', 'source_code',
            'target', 'target_name', 'target_code',
            'edge_type', 'weight', 'source_type', 'is_active',
            'institution', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'institution', 'source_type', 'created_at', 'updated_at')


class MarketplaceListingSerializer(serializers.ModelSerializer):
    publisher_name = serializers.SerializerMethodField()

    class Meta:
        model = MarketplaceListing
        fields = [
            'id', 'publisher', 'publisher_name', 'title', 'description',
            'content_type', 'subject', 'grade', 'price_cents', 'license_type',
            'status', 'downloads', 'rating', 'content_ids', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'publisher', 'publisher_name', 'downloads', 'rating', 'created_at', 'updated_at']

    def get_publisher_name(self, obj):
        return obj.publisher.name if obj.publisher else None