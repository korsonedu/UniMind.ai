from rest_framework import serializers
from .models import (
    Question, QuizAttempt, KnowledgePoint, UserQuestionStatus, QuizExam, ExamQuestionResult,
    ContentPipelineTask, TeacherExam, StudentExamSubmission, KnowledgePointAnnotation,
    PersonalizedMockExam, ExamTemplate,
)
from users.serializers import UserSerializer

class KnowledgePointSerializer(serializers.ModelSerializer):
    questions_count = serializers.IntegerField(source='questions.count', read_only=True)
    children = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgePoint
        fields = ('id', 'code', 'name', 'level', 'prefix_category', 'description', 'parent', 'institution', 'order', 'created_at', 'questions_count', 'children')

    def get_children(self, obj):
        children = obj.children.all()  # uses prefetch cache when available
        if not children:
            return []
        return KnowledgePointSerializer(children, many=True, context=self.context).data

class QuestionSerializer(serializers.ModelSerializer):
    knowledge_point_detail = KnowledgePointSerializer(source='knowledge_point', read_only=True)
    is_favorite = serializers.SerializerMethodField()
    is_mastered = serializers.SerializerMethodField()
    difficulty_level_display = serializers.CharField(source='get_difficulty_level_display', read_only=True)

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
        fields = ('id', 'exam', 'details', 'question', 'user_answer', 'score', 'max_score', 'feedback', 'analysis', 'is_correct', 'question_detail')

class QuizExamSerializer(serializers.ModelSerializer):
    results = ExamQuestionResultSerializer(many=True, read_only=True)
    created_at_fmt = serializers.DateTimeField(source='created_at', format="%Y-%m-%d %H:%M", read_only=True)

    class Meta:
        model = QuizExam
        fields = ('id', 'user', 'total_score', 'max_score', 'elo_change', 'summary', 'created_at', 'results', 'created_at_fmt')


class ContentPipelineTaskSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    task_type_display = serializers.CharField(source='get_task_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = ContentPipelineTask
        fields = ('id', 'task_type', 'status', 'title', 'description', 'progress', 'payload', 'result', 'error_message', 'request_id', 'assignee', 'created_by', 'institution', 'started_at', 'finished_at', 'created_at', 'updated_at', 'created_by_username', 'task_type_display', 'status_display')


class TeacherExamSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeacherExam
        fields = ('id', 'title', 'description', 'exam_pdf', 'created_at', 'created_by', 'institution')


class StudentExamSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentExamSubmission
        fields = ('id', 'user', 'exam', 'answer_pdf', 'score', 'feedback', 'graded_pdf', 'created_at')


class KnowledgePointAnnotationSerializer(serializers.ModelSerializer):
    class Meta:
        model = KnowledgePointAnnotation
        fields = ('id', 'user', 'knowledge_point', 'mastery_level', 'priority', 'confidence_score', 'tags', 'note', 'source', 'created_at', 'updated_at')


class PersonalizedMockExamSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonalizedMockExam
        fields = ('id', 'user', 'status', 'exam_pdf', 'answer_pdf', 'question_count', 'weak_coverage', 'error_message', 'created_at')


class ExamTemplateSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.username', read_only=True, default=None)

    class Meta:
        model = ExamTemplate
        fields = (
            'id', 'name', 'description', 'subject', 'difficulty',
            'question_types', 'type_ratio', 'question_count',
            'knowledge_point_ids', 'is_system', 'created_by',
            'created_by_name', 'institution', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'is_system', 'created_by', 'institution', 'created_at', 'updated_at')