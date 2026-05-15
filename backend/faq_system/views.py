from rest_framework import generics, permissions, status, filters
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q
from .models import Question, Answer
from .serializers import QuestionSerializer, AnswerSerializer
from notifications.models import Notification
from users.views import IsMember

class QuestionListCreateView(generics.ListCreateAPIView):
    serializer_class = QuestionSerializer
    permission_classes = [IsMember]
    filter_backends = [filters.SearchFilter]
    search_fields = ['content', 'user__nickname']

    def get_queryset(self):
        from users.permissions import is_platform_admin
        from django.db.models import Q
        user = self.request.user
        qs = Question.objects.all().select_related('user').prefetch_related('answers__user')
        if not is_platform_admin(user):
            inst = getattr(user, 'institution', None)
            if inst:
                qs = qs.filter(Q(institution=inst) | Q(institution__isnull=True))
            else:
                qs = qs.filter(institution__isnull=True)

        # Filter Logic
        filter_type = self.request.query_params.get('filter', 'all')
        if filter_type == 'solved':
            qs = qs.filter(is_solved=True)
        elif filter_type == 'unsolved':
            qs = qs.filter(is_solved=False)
        elif filter_type == 'starred':
            # Assuming regular users can see starred questions too
            qs = qs.filter(is_starred=True)
        elif filter_type == 'followed':
            qs = qs.filter(followers=self.request.user)

        return qs

    def perform_create(self, serializer):
        serializer.save(user=self.request.user, institution=self.request.user.institution)

class QuestionDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Question.objects.all()
    serializer_class = QuestionSerializer
    permission_classes = [IsMember]

    def get_queryset(self):
        from users.permissions import is_platform_admin
        from django.db.models import Q
        user = self.request.user
        qs = super().get_queryset()
        if not is_platform_admin(user):
            inst = getattr(user, 'institution', None)
            if inst:
                qs = qs.filter(Q(institution=inst) | Q(institution__isnull=True))
            else:
                qs = qs.filter(institution__isnull=True)
        return qs

    def perform_update(self, serializer):
        if self.request.user == serializer.instance.user or self.request.user.role == 'admin':
            serializer.save()
        else:
            raise permissions.PermissionDenied("无权修改")

    def perform_destroy(self, instance):
        # Allow owner or admin to delete
        if instance.user == self.request.user or self.request.user.role == 'admin':
            instance.delete()
        else:
            raise permissions.PermissionDenied("无权删除")

class AnswerDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Answer.objects.all()
    serializer_class = AnswerSerializer
    permission_classes = [IsMember]

    def get_queryset(self):
        from users.permissions import is_platform_admin
        from django.db.models import Q
        user = self.request.user
        qs = super().get_queryset().select_related('question')
        if not is_platform_admin(user):
            inst = getattr(user, 'institution', None)
            if inst:
                qs = qs.filter(Q(question__institution=inst) | Q(question__institution__isnull=True))
            else:
                qs = qs.filter(question__institution__isnull=True)
        return qs

    def perform_update(self, serializer):
        if self.request.user == serializer.instance.user or self.request.user.role == 'admin':
            serializer.save()
        else:
            raise permissions.PermissionDenied("无权修改")

    def perform_destroy(self, instance):
        if instance.user == self.request.user or self.request.user.role == 'admin':
            instance.delete()
        else:
            raise permissions.PermissionDenied("无权删除")

class AnswerCreateView(generics.CreateAPIView):
    serializer_class = AnswerSerializer
    permission_classes = [IsMember]

    def create(self, request, *args, **kwargs):
        from users.permissions import is_platform_admin
        from django.db.models import Q
        question_id = request.data.get('question')
        try:
            if is_platform_admin(request.user):
                question = Question.objects.get(id=question_id)
            else:
                inst = request.user.institution
                if inst:
                    question = Question.objects.get(Q(id=question_id) & (Q(institution=inst) | Q(institution__isnull=True)))
                else:
                    question = Question.objects.get(id=question_id, institution__isnull=True)
        except Question.DoesNotExist:
            return Response({'error': 'Question not found'}, status=404)

        is_teacher = request.user.role == 'admin'
        
        # 逻辑：首次回答仅允许教师
        if question.answers.count() == 0:
            if not is_teacher:
                return Response({'error': '首个回答必须由教师完成'}, status=403)
            # 教师回答后，自动标记为已解决（可选逻辑，暂保留为手动或默认逻辑）
            question.is_solved = True
            question.save()

        # Create answer
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user, is_teacher=is_teacher, question=question)
        
        # 通知提问者
        if question.user != request.user:
            Notification.objects.create(
                recipient=question.user,
                sender=request.user,
                ntype='qa_reply',
                title='你的提问有了新回复',
                content=f'{request.user.nickname or request.user.username} 回复了你的问题',
                link=f'/qa'
            )
        
        # 通知关注者
        followers = question.followers.exclude(id=request.user.id).exclude(id=question.user.id)
        if followers.exists():
            notifs = [
                Notification(
                    recipient=f,
                    sender=request.user,
                    ntype='qa_reply',
                    title='你关注的问题有了新动态',
                    content=f'有人回复了你关注的问题',
                    link=f'/qa'
                ) for f in followers
            ]
            Notification.objects.bulk_create(notifs)
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class QuestionActionView(APIView):
    permission_classes = [IsMember]

    def patch(self, request, pk):
        from users.permissions import is_platform_admin
        from django.db.models import Q
        try:
            if is_platform_admin(request.user):
                question = Question.objects.get(pk=pk)
            else:
                inst = request.user.institution
                if inst:
                    question = Question.objects.get(Q(pk=pk) & (Q(institution=inst) | Q(institution__isnull=True)))
                else:
                    question = Question.objects.get(pk=pk, institution__isnull=True)
        except Question.DoesNotExist:
            return Response({'error': 'Not found'}, status=404)

        # Like Logic (Any User)
        if 'toggle_like' in request.data:
            if question.likes.filter(id=request.user.id).exists():
                question.likes.remove(request.user)
                is_liked = False
            else:
                question.likes.add(request.user)
                is_liked = True
            return Response({
                'status': 'ok',
                'is_liked': is_liked,
                'likes_count': question.likes.count()
            })

        # Follow Logic
        if 'toggle_follow' in request.data:
            if question.followers.filter(id=request.user.id).exists():
                question.followers.remove(request.user)
                is_followed = False
            else:
                question.followers.add(request.user)
                is_followed = True
            return Response({'status': 'ok', 'is_followed': is_followed})

        # Star Logic (Only Admin)
        if 'toggle_star' in request.data:
            if request.user.role != 'admin':
                return Response({'error': 'Permission denied'}, status=403)
            question.is_starred = not question.is_starred
            question.save()
            return Response({'status': 'ok', 'is_starred': question.is_starred})

        # Solve Logic (Owner or Admin)
        if 'toggle_solved' in request.data:
            if request.user != question.user and request.user.role != 'admin':
                return Response({'error': 'Permission denied'}, status=403)
            question.is_solved = not question.is_solved
            question.save()
            return Response({'status': 'ok', 'is_solved': question.is_solved})

        return Response({'error': 'Invalid action'}, status=400)

class AnswerActionView(APIView):
    permission_classes = [IsMember]

    def patch(self, request, pk):
        try:
            answer = Answer.objects.get(pk=pk)
        except Answer.DoesNotExist:
            return Response({'error': 'Not found'}, status=404)

        # Like Logic (Any User)
        if 'toggle_like' in request.data:
            if answer.likes.filter(id=request.user.id).exists():
                answer.likes.remove(request.user)
                is_liked = False
            else:
                answer.likes.add(request.user)
                is_liked = True
            return Response({
                'status': 'ok',
                'is_liked': is_liked,
                'likes_count': answer.likes.count()
            })

        return Response({'error': 'Invalid action'}, status=400)
