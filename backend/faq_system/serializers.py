from rest_framework import serializers
from .models import Question, Answer
from users.serializers import UserSerializer

class AnswerSerializer(serializers.ModelSerializer):
    user_detail = UserSerializer(source='user', read_only=True)
    likes_count = serializers.IntegerField(source='likes.count', read_only=True)
    is_liked = serializers.SerializerMethodField()

    class Meta:
        model = Answer
        fields = ('id', 'question', 'user', 'content', 'is_teacher', 'likes', 'created_at', 'updated_at', 'user_detail', 'likes_count', 'is_liked')
        read_only_fields = ('user', 'is_teacher', 'created_at')

    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.likes.filter(id=request.user.id).exists()
        return False

class QuestionSerializer(serializers.ModelSerializer):
    user_detail = UserSerializer(source='user', read_only=True)
    answers = serializers.SerializerMethodField()
    first_answer = serializers.SerializerMethodField()
    reply_count = serializers.SerializerMethodField()
    likes_count = serializers.IntegerField(source='likes.count', read_only=True)
    is_liked = serializers.SerializerMethodField()
    is_followed = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = ('id', 'user', 'content', 'attachment', 'is_solved', 'is_starred', 'likes', 'followers', 'created_at', 'updated_at', 'institution', 'user_detail', 'answers', 'first_answer', 'reply_count', 'likes_count', 'is_liked', 'is_followed')
        read_only_fields = ('user', 'created_at', 'updated_at', 'is_solved', 'is_starred')

    def get_answers(self, obj):
        # Pass context to answer serializer to get is_liked status correctly
        qs = obj.answers.all()
        return AnswerSerializer(qs, many=True, context=self.context).data

    def get_first_answer(self, obj):
        first = obj.answers.first()
        if first:
            return AnswerSerializer(first, context=self.context).data
        return None

    def get_reply_count(self, obj):
        return obj.answers.count()

    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.likes.filter(id=request.user.id).exists()
        return False

    def get_is_followed(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.followers.filter(id=request.user.id).exists()
        return False
