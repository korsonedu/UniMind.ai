import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import generics, serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .learning import active_grants, grant_product, usage_info
from .models import LearningProduct, LearningGrant
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


class LearningGrantSerializer(serializers.ModelSerializer):
    email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = LearningGrant
        fields = ('id', 'user', 'email', 'product', 'snapshot', 'source', 'starts_at', 'expires_at', 'revoked')
        read_only_fields = fields


class LearningCatalogView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({'free_ai_calls': settings.LEARNING_FREE_AI_CALLS_PER_MONTH,
                         'payment_methods': payment_methods(),
                         'products': LearningProductSerializer(LearningProduct.objects.filter(is_active=True).prefetch_related('modules'), many=True).data})


class MyLearningAccessView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({'ai_usage': usage_info(request.user),
                         'grants': LearningGrantSerializer(active_grants(request.user).select_related('user'), many=True).data})


class LearningProductAdminView(generics.ListCreateAPIView):
    permission_classes = [IsPlatformAdmin]
    serializer_class = LearningProductSerializer
    queryset = LearningProduct.objects.prefetch_related('modules')
    pagination_class = None


class LearningProductDetailView(generics.RetrieveUpdateAPIView):
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
        class GrantInput(serializers.Serializer):
            email = serializers.EmailField()
            product = serializers.PrimaryKeyRelatedField(queryset=LearningProduct.objects.all())
            source = serializers.ChoiceField(choices=['course', 'admin'], default='course')
        payload = GrantInput(data=request.data)
        payload.is_valid(raise_exception=True)
        user = get_user_model().objects.filter(email__iexact=payload.validated_data['email'], email_verified=True).first()
        if not user:
            return Response({'error': '未找到该邮箱的已验证账号，请学员先注册。'}, status=400)
        grant = grant_product(user, payload.validated_data['product'], source=payload.validated_data['source'])
        return Response(LearningGrantSerializer(grant).data, status=201)


class LearningGrantDetailView(generics.UpdateAPIView):
    permission_classes = [IsPlatformAdmin]
    queryset = LearningGrant.objects.all()

    class RevokeSerializer(serializers.ModelSerializer):
        class Meta:
            model = LearningGrant
            fields = ('id', 'revoked')
            read_only_fields = ('id',)

    serializer_class = RevokeSerializer
