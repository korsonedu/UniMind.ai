"""Core views: Legal document API, feedback admin. """

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from users.permissions import IsPlatformAdmin
from core.models import LegalDocument, Feedback


class LegalDocumentView(APIView):
    """获取法律文档（公开接口）。

    GET /api/legal/<doc_type>/?version=1.0
    doc_type: privacy | terms
    不传 version 则返回当前生效版本。
    """
    permission_classes = [AllowAny]

    def get(self, request, doc_type):
        if doc_type not in dict(LegalDocument.DOC_TYPE_CHOICES):
            return Response({'error': '无效的文档类型'}, status=404)

        version = request.query_params.get('version')
        qs = LegalDocument.objects.filter(doc_type=doc_type, is_active=True)

        if version:
            doc = qs.filter(version=version).first()
        else:
            doc = qs.order_by('-effective_date').first()

        if not doc:
            return Response({'error': '文档不存在'}, status=404)

        return Response({
            'doc_type': doc.doc_type,
            'doc_type_display': doc.get_doc_type_display(),
            'version': doc.version,
            'title': doc.title,
            'content': doc.content,
            'effective_date': str(doc.effective_date),
        })


class LegalDocumentListView(APIView):
    """获取所有生效法律文档列表（公开接口）。

    GET /api/legal/
    """
    permission_classes = [AllowAny]

    def get(self, request):
        docs = LegalDocument.objects.filter(is_active=True).order_by('doc_type', '-effective_date')
        # 每种类型只返回最新版
        seen = {}
        for doc in docs:
            if doc.doc_type not in seen:
                seen[doc.doc_type] = {
                    'doc_type': doc.doc_type,
                    'doc_type_display': doc.get_doc_type_display(),
                    'version': doc.version,
                    'title': doc.title,
                    'effective_date': str(doc.effective_date),
                }
        return Response(list(seen.values()))


class FeedbackAdminListView(APIView):
    """管理后台查看反馈列表。

    GET /api/admin/feedback/?resolved=false&page=1
    """
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        qs = Feedback.objects.select_related('user').all()
        resolved = request.query_params.get('resolved')
        if resolved == 'true':
            qs = qs.filter(is_resolved=True)
        elif resolved == 'false':
            qs = qs.filter(is_resolved=False)

        page = int(request.query_params.get('page', 1))
        page_size = 20
        total = qs.count()
        items = qs[(page - 1) * page_size: page * page_size]

        return Response({
            'total': total,
            'page': page,
            'page_size': page_size,
            'items': [
                {
                    'id': f.id,
                    'user': f.user.username if f.user else '匿名',
                    'category': f.category,
                    'category_display': f.get_category_display(),
                    'content': f.content,
                    'contact': f.contact,
                    'page_url': f.page_url,
                    'is_resolved': f.is_resolved,
                    'admin_note': f.admin_note,
                    'created_at': f.created_at.isoformat(),
                }
                for f in items
            ],
        })


class FeedbackAdminDetailView(APIView):
    """管理员处理反馈。

    PATCH /api/admin/feedback/<pk>/
    Body: { "is_resolved": true, "admin_note": "已修复" }
    """
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def patch(self, request, pk):
        from django.utils import timezone
        try:
            fb = Feedback.objects.get(pk=pk)
        except Feedback.DoesNotExist:
            return Response({'error': '反馈不存在'}, status=404)

        if 'is_resolved' in request.data:
            fb.is_resolved = request.data['is_resolved']
            if fb.is_resolved:
                fb.resolved_at = timezone.now()
        if 'admin_note' in request.data:
            fb.admin_note = request.data['admin_note']
        fb.save()

        return Response({'status': 'ok'})
