import logging
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import PermissionGroup, UserTag, UserAccessProfile
from .permissions import IsPlatformAdmin

User = get_user_model()
logger = logging.getLogger(__name__)


# ── Superuser: 全局用户列表 & 编辑 ──

class SuperuserUserListView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        qs = User.objects.select_related('access_profile').prefetch_related(
            'access_profile__tags', 'access_profile__permission_groups'
        ).order_by('-date_joined')
        search = request.query_params.get('search', '')
        if search:
            qs = qs.filter(username__icontains=search) | qs.filter(email__icontains=search) | qs.filter(nickname__icontains=search)
        qs = qs.distinct()

        page_size = int(request.query_params.get('page_size', 200))
        qs = qs[:page_size]

        users_data = []
        for u in qs:
            profile = getattr(u, 'access_profile', None)
            users_data.append({
                'id': u.id,
                'username': u.username,
                'nickname': u.nickname or '',
                'email': u.email or '',
                'role': u.role,
                'is_member': u.is_member,
                'is_staff': u.is_staff,
                'is_superuser': u.is_superuser,
                'tag_ids': list(profile.tags.values_list('id', flat=True)) if profile else [],
                'tag_names': list(profile.tags.values_list('name', flat=True)) if profile else [],
                'permission_group_ids': list(profile.permission_groups.values_list('id', flat=True)) if profile else [],
                'permission_group_keys': list(profile.permission_groups.values_list('key', flat=True)) if profile else [],
                'extra_permissions': profile.extra_permissions if profile else [],
                'blocked_permissions': profile.blocked_permissions if profile else [],
                'profile_note': profile.note if profile else '',
                'elo_score': u.elo_score,
            })

        return Response({'results': users_data, 'count': len(users_data)})

    def patch(self, request, pk):
        user = get_object_or_404(User, pk=pk)

        if 'role' in request.data:
            valid_roles = [c[0] for c in User.ROLE_CHOICES]
            if request.data['role'] not in valid_roles:
                return Response({'detail': '无效的角色'}, status=400)
            user.role = request.data['role']
        if 'is_member' in request.data:
            user.is_member = bool(request.data['is_member'])
        if 'is_staff' in request.data:
            user.is_staff = bool(request.data['is_staff'])
        if 'is_superuser' in request.data:
            user.is_superuser = bool(request.data['is_superuser'])
        user.save()

        profile, _ = UserAccessProfile.objects.get_or_create(user=user)

        if 'tag_ids' in request.data:
            profile.tags.set(request.data['tag_ids'])
        if 'permission_group_ids' in request.data:
            profile.permission_groups.set(request.data['permission_group_ids'])
        if 'extra_permissions' in request.data:
            profile.extra_permissions = request.data['extra_permissions']
        if 'blocked_permissions' in request.data:
            profile.blocked_permissions = request.data['blocked_permissions']
        if 'note' in request.data:
            profile.note = request.data.get('note', '')
        profile.save()

        return Response({'status': 'ok'})


# ── 用户标签 CRUD ──

class UserTagListView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        qs = UserTag.objects.all().order_by('name')
        return Response([
            {'id': t.id, 'name': t.name, 'color': t.color,
             'description': t.description, 'is_active': t.is_active}
            for t in qs
        ])

    def post(self, request):
        name = (request.data.get('name') or '').strip()
        if not name:
            return Response({'error': '标签名不能为空'}, status=400)
        tag = UserTag.objects.create(
            name=name,
            color=request.data.get('color', 'slate'),
            description=request.data.get('description', ''),
        )
        return Response({
            'id': tag.id, 'name': tag.name, 'color': tag.color,
            'description': tag.description, 'is_active': tag.is_active,
        }, status=status.HTTP_201_CREATED)


# ── 权限组 CRUD ──

class PermissionGroupListView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        qs = PermissionGroup.objects.all().order_by('name')
        return Response([
            {'id': g.id, 'key': g.key, 'name': g.name,
             'description': g.description, 'permissions': g.permissions,
             'is_active': g.is_active}
            for g in qs
        ])

    def post(self, request):
        key = (request.data.get('key') or '').strip()
        name = (request.data.get('name') or '').strip()
        if not key or not name:
            return Response({'error': 'key 和 name 不能为空'}, status=400)
        group = PermissionGroup.objects.create(
            key=key, name=name,
            description=request.data.get('description', ''),
            permissions=request.data.get('permissions', []),
        )
        return Response({
            'id': group.id, 'key': group.key, 'name': group.name,
            'description': group.description, 'permissions': group.permissions,
            'is_active': group.is_active,
        }, status=status.HTTP_201_CREATED)
