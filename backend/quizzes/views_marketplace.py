"""内容市场 — 机构间题库/课程共享与发现。"""
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

from .models import MarketplaceListing
from .serializers import MarketplaceListingSerializer


class MarketplaceListView(APIView):
    """GET /api/quizzes/marketplace/ — 可搜索的内容列表。"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = MarketplaceListing.objects.filter(status='published').select_related('publisher')

        # 筛选
        subject = request.query_params.get('subject', '')
        grade = request.query_params.get('grade', '')
        content_type = request.query_params.get('content_type', '')
        license_type = request.query_params.get('license_type', '')
        search = request.query_params.get('search', '')

        if subject:
            qs = qs.filter(subject=subject)
        if grade:
            qs = qs.filter(grade=grade)
        if content_type:
            qs = qs.filter(content_type=content_type)
        if license_type:
            qs = qs.filter(license_type=license_type)
        if search:
            qs = qs.filter(title__icontains=search)

        # 分页
        try:
            page = int(request.query_params.get('page', 1))
            page_size = int(request.query_params.get('page_size', 20))
        except (ValueError, TypeError):
            page, page_size = 1, 20

        start = (page - 1) * page_size
        end = start + page_size

        ser = MarketplaceListingSerializer(qs[start:end], many=True)
        return Response({
            'listings': ser.data,
            'total': qs.count(),
            'page': page,
            'page_size': page_size,
        })


class MarketplaceDetailView(APIView):
    """GET /api/quizzes/marketplace/<int:pk>/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        listing = get_object_or_404(MarketplaceListing, pk=pk, status='published')
        return Response(MarketplaceListingSerializer(listing).data)


class MarketplacePublishView(APIView):
    """POST /api/quizzes/marketplace/publish/ — 平台管理员发布官方内容到市场。"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.is_admin:
            return Response({'error': '仅平台管理员可发布内容'}, status=403)

        ser = MarketplaceListingSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ser.save(publisher=None)
        return Response(ser.data, status=201)


class MarketplaceManageView(APIView):
    """GET/PUT/DELETE /api/quizzes/marketplace/manage/<int:pk>/ — 平台管理员管理官方上架内容。"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_admin:
            return Response({'error': '仅平台管理员可管理内容'}, status=403)
        qs = MarketplaceListing.objects.filter(publisher__isnull=True).order_by('-created_at')
        ser = MarketplaceListingSerializer(qs, many=True)
        return Response(ser.data)

    def put(self, request, pk):
        if not request.user.is_admin:
            return Response({'error': '仅平台管理员可管理内容'}, status=403)
        listing = get_object_or_404(MarketplaceListing, pk=pk, publisher__isnull=True)
        ser = MarketplaceListingSerializer(listing, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)

    def delete(self, request, pk):
        if not request.user.is_admin:
            return Response({'error': '仅平台管理员可管理内容'}, status=403)
        listing = get_object_or_404(MarketplaceListing, pk=pk, publisher__isnull=True)
        listing.delete()
        return Response(status=204)


class MarketplacePurchaseView(APIView):
    """POST /api/quizzes/marketplace/<int:pk>/purchase/ — 购买/下载市场内容。"""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        inst = getattr(request.user, 'institution', None)
        if not inst:
            return Response({'error': '无机构归属'}, status=403)

        listing = get_object_or_404(MarketplaceListing, pk=pk, status='published')

        if listing.license_type == 'free':
            listing.downloads += 1
            listing.save(update_fields=['downloads'])
            return Response({
                'status': 'downloaded',
                'content_type': listing.content_type,
                'content_ids': listing.content_ids,
            })

        # 付费内容 — 创建订单
        from payments.services.base import create_order
        order = create_order(
            user=request.user,
            plan='starter',
            billing_cycle='annual',
            gateway='stripe',
            institution=inst,
        )
        # 覆写金额为 listing 价格
        order.amount_cents = listing.price_cents
        order.save(update_fields=['amount_cents'])

        from payments.services.gateway_router import get_gateway
        try:
            gw = get_gateway('stripe')
            data = gw.create_checkout_session(order)
            return Response({
                'status': 'payment_required',
                'order_id': order.id,
                'checkout_url': data['checkout_url'],
            })
        except Exception:
            order.status = 'cancelled'
            order.save(update_fields=['status'])
            return Response({'error': '创建支付会话失败'}, status=500)
