from rest_framework import generics, status, filters
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from django.db.models import Count, OuterRef, Prefetch, Subquery, prefetch_related_objects
from django.utils.decorators import method_decorator
from .models import Question, Answer
from .serializers import QuestionSerializer, AnswerSerializer
from notifications.models import Notification
from users.views import IsMember
from users.permissions import is_platform_admin, is_institution_admin, is_institution_teacher
from core.file_validation import validate_upload_file
from core.rate_limit import user_rate_limit
from core.utils import apply_institution_filter, get_content_institution
from users.quota import check_and_add_storage_usage

_upload_rl = method_decorator(user_rate_limit("upload", 100, 3600), name="dispatch")

class QuestionPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class QuestionListCreateView(generics.ListCreateAPIView):
    serializer_class = QuestionSerializer
    permission_classes = [IsMember]
    filter_backends = [filters.SearchFilter]
    search_fields = ['content', 'user__nickname']
    pagination_class = QuestionPagination

    def get_queryset(self):
        first_answer = Answer.objects.filter(question_id=OuterRef('pk')).order_by('created_at', 'pk')
        qs = Question.objects.select_related('user').prefetch_related('likes', 'followers').annotate(
            answer_count=Count('answers', distinct=True),
            first_answer_id=Subquery(first_answer.values('pk')[:1]),
        ).order_by('-created_at', '-pk')
        qs = apply_institution_filter(qs, self.request.user, self.request)

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

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        answers = Answer.objects.filter(pk__in=[q.first_answer_id for q in page if q.first_answer_id]).select_related('user').prefetch_related('likes')
        prefetch_related_objects(page, Prefetch('answers', queryset=answers, to_attr='summary_answers'))

        # 本页每位作者只解析一次学员身份，嵌套用户序列化不再逐行查询。
        from django.utils import timezone
        from users.models import CourseStudentStatus, LearningGrant
        from users.learning import has_legacy_membership
        authors = {q.user_id: q.user for q in page}
        authors.update({a.user_id: a.user for q in page for a in q.summary_answers})
        statuses = dict(CourseStudentStatus.objects.filter(user_id__in=authors).values_list('user_id', 'is_course_student'))
        missing = authors.keys() - statuses.keys()
        now = timezone.now()
        grants = set(LearningGrant.objects.filter(user_id__in=missing, revoked=False, starts_at__lte=now, expires_at__gt=now).values_list('user_id', flat=True))
        statuses.update({pk: has_legacy_membership(authors[pk]) or pk in grants for pk in missing})
        context = {**self.get_serializer_context(), 'is_course_student_by_id': statuses}
        return self.get_paginated_response(self.get_serializer(page, many=True, context=context).data)

    def perform_create(self, serializer):
        validate_upload_file(self.request.FILES.get("attachment"))
        total_size = sum(f.size for f in self.request.FILES.values() if f)
        inst = get_content_institution()
        check_and_add_storage_usage(inst, total_size)
        serializer.save(user=self.request.user, institution=inst)

class QuestionDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Question.objects.all()
    serializer_class = QuestionSerializer
    permission_classes = [IsMember]

    def get_queryset(self):
        qs = super().get_queryset()
        return apply_institution_filter(qs, self.request.user, self.request)

    def perform_update(self, serializer):
        if self.request.user == serializer.instance.user or is_platform_admin(self.request.user) or is_institution_admin(self.request.user):
            serializer.save()
        else:
            raise PermissionDenied("无权修改")

    def perform_destroy(self, instance):
        if instance.user == self.request.user or is_platform_admin(self.request.user) or is_institution_admin(self.request.user):
            instance.delete()
        else:
            raise PermissionDenied("无权删除")

class AnswerDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Answer.objects.all()
    serializer_class = AnswerSerializer
    permission_classes = [IsMember]

    def get_queryset(self):
        qs = super().get_queryset().select_related('question')
        return apply_institution_filter(qs, self.request.user, self.request, institution_field='question__institution')

    def perform_update(self, serializer):
        if self.request.user == serializer.instance.user or is_platform_admin(self.request.user) or is_institution_admin(self.request.user):
            serializer.save()
        else:
            raise PermissionDenied("无权修改")

    def perform_destroy(self, instance):
        if instance.user == self.request.user or is_platform_admin(self.request.user) or is_institution_admin(self.request.user):
            instance.delete()
        else:
            raise PermissionDenied("无权删除")

class AnswerCreateView(generics.CreateAPIView):
    serializer_class = AnswerSerializer
    permission_classes = [IsMember]

    def create(self, request, *args, **kwargs):
        question_id = request.data.get('question')
        try:
            qs = apply_institution_filter(Question.objects.all(), request.user, request)
            question = qs.get(id=question_id)
        except Question.DoesNotExist:
            return Response({'error': 'Question not found'}, status=404)

        is_teacher = is_institution_teacher(request.user) or is_platform_admin(request.user)
        
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
        try:
            qs = apply_institution_filter(Question.objects.all(), request.user, request)
            question = qs.get(pk=pk)
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

        # Star Logic (Platform admin or institution admin)
        if 'toggle_star' in request.data:
            if not (is_platform_admin(request.user) or is_institution_admin(request.user)):
                return Response({'error': 'Permission denied'}, status=403)
            question.is_starred = not question.is_starred
            question.save()
            return Response({'status': 'ok', 'is_starred': question.is_starred})

        # Solve Logic (Owner, platform admin, or institution admin)
        if 'toggle_solved' in request.data:
            if request.user != question.user and not is_platform_admin(request.user) and not is_institution_admin(request.user):
                return Response({'error': 'Permission denied'}, status=403)
            question.is_solved = not question.is_solved
            question.save()
            return Response({'status': 'ok', 'is_solved': question.is_solved})

        return Response({'error': 'Invalid action'}, status=400)

class AnswerActionView(APIView):
    permission_classes = [IsMember]

    def patch(self, request, pk):
        from django.shortcuts import get_object_or_404
        answer = get_object_or_404(apply_institution_filter(Answer.objects.all(), request.user, request,
                                   institution_field='question__institution'), pk=pk)
        user = request.user

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
