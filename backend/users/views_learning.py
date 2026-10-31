import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import generics, serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .learning import active_grants, usage_info, ai_limit, is_course_student, active_addons, get_weekly_quota_config, cohort_info
from .models import LearningProduct, LearningGrant, AIAddonProduct
from .permissions import IsPlatformAdmin


def payment_methods():
    methods = []
    if all(os.getenv(key) for key in ('ALIPAY_APP_ID', 'ALIPAY_PRIVATE_KEY', 'ALIPAY_PUBLIC_KEY', 'ALIPAY_NOTIFY_URL', 'ALIPAY_RETURN_URL')):
        methods.append('alipay')
    if settings.DEBUG:
        methods.append('stub')
    return methods


class LearningProductSerializer(serializers.ModelSerializer):
    module_names = serializers.SerializerMethodField()

    class Meta:
        model = LearningProduct
        fields = ('id', 'name', 'description', 'price_cents', 'duration_days', 'monthly_ai_calls', 'modules', 'module_names', 'is_active', 'sort_order')

    def get_module_names(self, obj):
        return list(obj.modules.values_list('name', flat=True))

    def validate_duration_days(self, value):
        if value < 1:
            raise serializers.ValidationError('有效期至少为一天。')
        return value

    def validate(self, attrs):
        active = attrs.get('is_active', self.instance.is_active if self.instance else False)
        price = attrs.get('price_cents', self.instance.price_cents if self.instance else 0)
        if active and price < 1:
            raise serializers.ValidationError({'price_cents': '上架前请设置销售价格。'})
        return attrs


class AIAddonProductSerializer(serializers.ModelSerializer):
    configured = serializers.BooleanField(read_only=True)

    class Meta:
        model = AIAddonProduct
        fields = ('id', 'name', 'description', 'price_cents', 'ai_calls', 'validity_days',
                  'is_active', 'sort_order', 'configured')

    def validate(self, attrs):
        active = attrs.get('is_active', self.instance.is_active if self.instance else False)
        if active:
            for name in ('price_cents', 'ai_calls', 'validity_days'):
                value = attrs.get(name, getattr(self.instance, name, None))
                if value is None or value < 1:
                    raise serializers.ValidationError({name: '请明确配置价格、次数和有效期后再上架。'})
        return attrs


class LearningGrantSerializer(serializers.ModelSerializer):
    email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = LearningGrant
        fields = ('id', 'user', 'email', 'product', 'snapshot', 'source', 'starts_at', 'expires_at', 'revoked')
        read_only_fields = fields


class LearningCatalogView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        config = get_weekly_quota_config()
        return Response({'experience_weekly_calls': config.experience_calls,
                         'course_weekly_calls': config.course_calls,
                         'payment_methods': payment_methods(),
                         'products': AIAddonProductSerializer(AIAddonProduct.objects.filter(
                             is_active=True, price_cents__gt=0, ai_calls__gt=0, validity_days__gt=0), many=True).data})


class MyLearningAccessView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        addons = active_addons(request.user)
        return Response({'ai_usage': usage_info(request.user),
                         'is_course_student': is_course_student(request.user),
                         'cohort': cohort_info(request.user),
                         'addons': [{'id': grant.id, 'name': grant.snapshot.get('name', ''),
                                     'ai_calls': grant.ai_calls, 'used_calls': grant.used_calls,
                                     'expires_at': grant.expires_at} for grant in addons],
                         'grants': LearningGrantSerializer(active_grants(request.user).select_related('user'), many=True).data})


class LearningProductAdminView(generics.ListAPIView):
    permission_classes = [IsPlatformAdmin]
    serializer_class = LearningProductSerializer
    queryset = LearningProduct.objects.prefetch_related('modules')
    pagination_class = None


class LearningProductDetailView(generics.RetrieveAPIView):
    permission_classes = [IsPlatformAdmin]
    serializer_class = LearningProductSerializer
    queryset = LearningProduct.objects.prefetch_related('modules')


class LearningGrantAdminView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        query = request.query_params.get('search', '').strip()
        grants = LearningGrant.objects.select_related('user')
        if query:
            grants = grants.filter(Q(user__email__iexact=query) | Q(user__username__iexact=query))
        return Response(LearningGrantSerializer(grants[:100], many=True).data)

    def post(self, request):
        return Response({'error': '旧学习服务不再发放，请在学员管理中手动设置课程学员状态。'}, status=410)


class LearningGrantDetailView(generics.UpdateAPIView):
    permission_classes = [IsPlatformAdmin]
    queryset = LearningGrant.objects.all()

    class RevokeSerializer(serializers.ModelSerializer):
        class Meta:
            model = LearningGrant
            fields = ('id', 'revoked')
            read_only_fields = ('id',)

    serializer_class = RevokeSerializer
