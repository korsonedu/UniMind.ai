"""Core views: Legal document API, feedback admin. """

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from users.permissions import IsPlatformAdmin
from core.models import LegalDocument, Feedback


# ──────────────────────────────────────────────
# 内置法律文档（数据库无记录时的 fallback）
# ──────────────────────────────────────────────

_TERMS_HTML = """
<h2>一、服务条款的确认与接纳</h2>
<p>欢迎使用 UniMind（以下简称"本平台"）。请您在使用本平台服务前，仔细阅读并充分理解本协议的全部内容。您通过网络页面点击确认或实际使用本平台服务，即视为您已阅读、理解并同意接受本协议的全部条款。</p>

<h2>二、服务内容</h2>
<p>本平台是一个基于人工智能技术的智能教育基础设施，为用户提供以下核心服务：</p>
<ul>
<li><strong>AI 学习教练</strong>：个性化学习规划、知识讲解、数据分析与教练式对话；</li>
<li><strong>智能出题</strong>：AI 驱动的教研出题、对抗精修与题库管理；</li>
<li><strong>课程学习</strong>：在线课程观看、学习进度追踪与知识图谱可视化；</li>
<li><strong>诊断测试</strong>：智能诊断评估与个性化学习建议；</li>
<li><strong>模拟面试</strong>：AI 模拟面试与反馈。</li>
</ul>

<h2>三、用户账号与注册</h2>
<p>您在注册本平台账号时，应提供真实、准确、完整的注册信息，并及时更新。您应妥善保管账号及密码，因您个人原因导致的账号安全问题，由您自行承担。</p>
<p>未满 18 周岁的未成年人应在监护人指导下使用本平台。</p>

<h2>四、用户行为规范</h2>
<p>您在使用本平台时，应遵守法律法规及本协议约定，不得利用本平台从事以下行为：</p>
<ul>
<li>发布、传播违反国家法律法规的内容；</li>
<li>侵犯他人知识产权、商业秘密及其他合法权益；</li>
<li>利用技术手段干扰本平台正常运行；</li>
<li>将本平台服务用于任何非法目的。</li>
</ul>

<h2>五、知识产权</h2>
<p>本平台的所有内容，包括但不限于文字、图片、音频、视频、软件、程序代码、界面设计、数据等，均受知识产权法律法规保护。未经授权，您不得复制、修改、传播本平台的任何内容。</p>
<p>您在本平台上传或发布的内容，您保留原有知识产权，但授予本平台在全球范围内免费使用、展示、推广该内容的许可。</p>

<h2>六、AI 生成内容</h2>
<p>本平台提供的 AI 生成内容（包括但不限于学习建议、题目解析、面试反馈）仅供参考，不构成专业教育建议。您应结合自身实际情况判断和使用 AI 生成内容。</p>
<p>AI 生成内容可能存在不准确之处，本平台不对 AI 生成内容的准确性、完整性作任何保证。</p>

<h2>七、免责声明</h2>
<p>本平台不对因以下原因导致的服务中断或损失承担责任：</p>
<ul>
<li>不可抗力（自然灾害、政策变化等）；</li>
<li>系统维护、升级等计划内停机；</li>
<li>用户自身网络环境或设备问题。</li>
</ul>

<h2>八、协议修改</h2>
<p>本平台有权根据业务发展需要修改本协议。修改后的协议将在平台上公布，公布即生效。若您在协议修改后继续使用本平台服务，即视为您已接受修改后的协议。</p>

<h2>九、争议解决</h2>
<p>本协议的解释、效力及争议解决，适用中华人民共和国法律。因本协议引起的争议，双方应友好协商解决；协商不成的，任何一方均可向本平台运营方所在地人民法院提起诉讼。</p>

<h2>十、联系方式</h2>
<p>如您对本协议有任何疑问，请通过平台内的反馈功能与我们联系。</p>
""".strip()

_PRIVACY_HTML = """
<h2>一、引言</h2>
<p>UniMind（以下简称"我们"或"本平台"）非常重视用户的隐私保护。本隐私政策旨在向您说明我们如何收集、使用、存储、共享及保护您的个人信息。</p>

<h2>二、我们收集的信息</h2>
<h3>2.1 您主动提供的信息</h3>
<ul>
<li><strong>注册信息</strong>：邮箱地址、昵称、密码（加密存储）；</li>
<li><strong>机构信息</strong>：机构名称、角色（学生/教师/机构管理员）；</li>
<li><strong>学习数据</strong>：答题记录、学习计划、课程进度；</li>
<li><strong>反馈信息</strong>：您通过平台反馈功能提交的内容。</li>
</ul>

<h3>2.2 自动收集的信息</h3>
<ul>
<li><strong>设备信息</strong>：浏览器类型、操作系统、设备标识符；</li>
<li><strong>日志信息</strong>：访问时间、IP 地址、访问页面；</li>
<li><strong>Cookie</strong>：用于维持登录状态和会话安全。</li>
</ul>

<h3>2.3 AI 交互数据</h3>
<ul>
<li><strong>对话内容</strong>：您与 AI 助教的对话记录；</li>
<li><strong>学习轨迹</strong>：AI 基于您的学习行为生成的用户画像和记忆数据。</li>
</ul>

<h2>三、我们如何使用您的信息</h2>
<p>我们收集的信息将用于以下目的：</p>
<ul>
<li>提供、维护和改进本平台服务；</li>
<li>实现个性化学习推荐和 AI 辅导；</li>
<li>保障账号安全和平台运行安全；</li>
<li>进行数据分析以优化平台功能；</li>
<li>遵守法律法规要求。</li>
</ul>

<h2>四、信息存储与安全</h2>
<p>您的个人信息存储在位于中华人民共和国境内的服务器上。我们采用行业标准的安全措施保护您的个人信息，包括但不限于：</p>
<ul>
<li>数据传输加密（HTTPS）；</li>
<li>密码加密存储（不可逆）；</li>
<li>敏感字段加密（AES）；</li>
<li>访问控制与权限管理。</li>
</ul>

<h2>五、信息共享与披露</h2>
<p>除以下情形外，我们不会向第三方共享您的个人信息：</p>
<ul>
<li>获得您的明确同意；</li>
<li>根据法律法规或政府主管部门的强制性要求；</li>
<li>为维护本平台的合法权益所必需；</li>
<li>与本平台关联公司的共享（仅限提供服务所必需）。</li>
</ul>

<h2>六、您的权利</h2>
<p>您对您的个人信息享有以下权利：</p>
<ul>
<li><strong>查阅权</strong>：查阅您在本平台上的个人信息；</li>
<li><strong>更正权</strong>：更正不准确的个人信息；</li>
<li><strong>删除权</strong>：在特定条件下请求删除您的个人信息；</li>
<li><strong>撤回同意</strong>：撤回此前给予的同意。</li>
</ul>

<h2>七、未成年人保护</h2>
<p>我们高度重视未成年人个人信息的保护。如您为未满 18 周岁的未成年人，请在监护人的指导下阅读本政策并使用本平台。</p>

<h2>八、隐私政策的更新</h2>
<p>我们可能适时修订本隐私政策。更新后的政策将在平台上公布，重大变更时我们会通过平台通知等方式告知您。</p>

<h2>九、联系我们</h2>
<p>如您对本隐私政策有任何疑问、意见或建议，请通过平台内的反馈功能与我们联系。</p>
""".strip()

_LEGAL_FALLBACK = {
    'terms': {
        'doc_type': 'terms',
        'doc_type_display': '用户协议',
        'version': '1.0',
        'title': '用户协议',
        'content': _TERMS_HTML,
        'effective_date': '2026-06-01',
    },
    'privacy': {
        'doc_type': 'privacy',
        'doc_type_display': '隐私政策',
        'version': '1.0',
        'title': '隐私政策',
        'content': _PRIVACY_HTML,
        'effective_date': '2026-06-01',
    },
}


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

        # 数据库无记录时返回内置默认内容
        if not doc:
            fallback = _LEGAL_FALLBACK.get(doc_type)
            if not fallback:
                return Response({'error': '文档不存在'}, status=404)
            return Response(fallback)

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
