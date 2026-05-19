from rest_framework import generics, permissions, status
from rest_framework.response import Response
from .models import Article
from .serializers import ArticleSerializer
from django.db.models import Count
from users.views import IsMember
from users.permissions import is_platform_admin, is_institution_admin

class IsAdminUserOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated and (request.user.is_member or is_platform_admin(request.user) or is_institution_admin(request.user)))
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)

class ArticleListCreateView(generics.ListCreateAPIView):
    serializer_class = ArticleSerializer
    permission_classes = [IsAdminUserOrReadOnly]

    def get_queryset(self):
        from users.permissions import is_platform_admin
        from django.db.models import Q
        user = self.request.user
        qs = Article.objects.all().order_by('-created_at')
        if not is_platform_admin(user):
            inst = getattr(user, 'institution', None)
            if inst:
                qs = qs.filter(Q(institution=inst) | Q(institution__isnull=True))
            else:
                qs = qs.filter(institution__isnull=True)
        tag = self.request.query_params.get('tag')
        q = self.request.query_params.get('search')
        kp = self.request.query_params.get('kp')
        if tag: qs = qs.filter(tags__icontains=tag)
        if q: qs = qs.filter(title__icontains=q)
        if kp: qs = qs.filter(knowledge_point_id=kp)
        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        
        # 分页逻辑 (每页 20 条)
        page = int(request.query_params.get('page', 1))
        page_size = 20
        total = queryset.count()
        
        offset = (page - 1) * page_size
        paged_queryset = queryset[offset:offset + page_size]
        serializer = self.get_serializer(paged_queryset, many=True)
        
        # 计算标签统计 (基于机构可见文章)
        tag_data = {}
        for art in queryset.filter(tags__isnull=False):
            if isinstance(art.tags, list):
                for t in art.tags:
                    if t not in tag_data:
                        tag_data[t] = {'count': 0, 'views': 0}
                    tag_data[t]['count'] += 1
                    tag_data[t]['views'] += (art.views or 0)
        
        sorted_tags = sorted(tag_data.items(), key=lambda item: item[1]['views'], reverse=True)
        tag_stats = [{'name': k, 'count': v['count'], 'views': v['views']} for k, v in sorted_tags]
        
        return Response({
            'articles': serializer.data,
            'tag_stats': tag_stats,
            'total': total,
            'page': page,
            'total_pages': (total + page_size - 1) // page_size
        })

    def perform_create(self, serializer):
        serializer.save(author=self.request.user, institution=self.request.user.institution)

class ArticleDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer
    permission_classes = [IsAdminUserOrReadOnly]

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

class ArticleIncrementViewView(generics.GenericAPIView):
    queryset = Article.objects.all()

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
    permission_classes = [IsMember]

    def post(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.views += 1
        instance.save(update_fields=['views'])
        return Response({'views': instance.views}, status=status.HTTP_200_OK)
