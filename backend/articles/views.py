from rest_framework import generics, permissions, status
from rest_framework.response import Response
from .models import Article
from .serializers import ArticleSerializer
from django.db.models import Count, F
from django.utils.decorators import method_decorator
from users.views import IsMember
from users.permissions import is_platform_admin, IsAdminWriteMemberRead, HasQuota
from core.file_validation import validate_upload_file, IMAGE_MAX_BYTES
from core.rate_limit import user_rate_limit
from users.quota import validate_storage_quota, add_storage_usage

_upload_rl = method_decorator(user_rate_limit("upload", 20, 3600), name="dispatch")

@_upload_rl
class ArticleListCreateView(generics.ListCreateAPIView):
    serializer_class = ArticleSerializer
    permission_classes = [IsAdminWriteMemberRead]
    quota_resource = 'article'

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdmin(), HasQuota()]
        return [IsAdminWriteMemberRead()]

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
        try:
            page = int(request.query_params.get('page', 1))
        except (ValueError, TypeError):
            page = 1
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
        validate_upload_file(self.request.FILES.get("cover_image"), max_size_bytes=IMAGE_MAX_BYTES)
        total_size = sum(f.size for f in self.request.FILES.values() if f)
        inst = self.request.user.institution
        validate_storage_quota(inst, total_size)
        serializer.save(author=self.request.user, institution=inst)
        add_storage_usage(inst, total_size)

class ArticleDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer
    permission_classes = [IsAdminWriteMemberRead]

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

    def get_queryset(self):
        from users.permissions import is_platform_admin
        from django.db.models import Q
        user = self.request.user
        qs = Article.objects.all()
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
        Article.objects.filter(pk=instance.pk).update(views=F('views') + 1)
        instance.refresh_from_db()
        return Response({'views': instance.views}, status=status.HTTP_200_OK)
