"""Account identity is shared; learning identities are independent per space."""
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from rest_framework.exceptions import PermissionDenied

from users.models_workspace import WorkspaceLearner, WorkspaceMembership


def learner_identity(user):
    return WorkspaceLearner.objects.select_related('account', 'workspace__institution').filter(user=user).first()


def account_user(user):
    identity = learner_identity(user)
    return identity.account if identity else user


def account_learner_ids(user):
    account = account_user(user)
    return get_user_model().objects.filter(Q(pk=account.pk) | Q(workspace_learner__account=account)).values_list('pk', flat=True)


def account_membership_for(user):
    return WorkspaceMembership.objects.select_related('workspace__institution').filter(user=account_user(user)).first()


@transaction.atomic
def select_learner(user, space):
    account = account_user(user)
    if space in ('', 'personal', None):
        return account
    from .access import workspace_active
    member = account_membership_for(account)
    if not member or str(member.workspace_id) != str(space) or not workspace_active(member):
        raise PermissionDenied({'detail': '你没有访问此空间的权限，或机构服务已暂停。', 'code': 'workspace_unavailable'})
    # Serialize first-time provisioning across tabs. Never issue a login session
    # for this identity, and never duplicate memberships or purchased allowances.
    identity = WorkspaceLearner.objects.select_related('user__institution').filter(account=account, workspace=member.workspace).first()
    if not identity:
        get_user_model().objects.select_for_update().get(pk=account.pk)
        identity = WorkspaceLearner.objects.select_related('user__institution').filter(account=account, workspace=member.workspace).first()
    if not identity:
        learner = get_user_model().objects.create_user(
            username=f'space_{uuid4().hex}', nickname=account.nickname or account.username,
            password=None, institution=member.workspace.institution,
            avatar_style=account.avatar_style, avatar_seed=account.avatar_seed or account.username,
        )
        identity = WorkspaceLearner.objects.create(account=account, workspace=member.workspace, user=learner)
    if not identity.user.is_active:
        raise PermissionDenied({'detail': '机构空间已暂停或不可访问。', 'code': 'workspace_unavailable'})
    return identity.user


def request_learner(request, account):
    # Account security, service administration and payment endpoints always act
    # on the login account, even while the learning UI is inside a workspace.
    path = request.path
    if ((not path.startswith('/api/') and not path.startswith('/media/')) or path.startswith((
        '/api/payments/', '/api/backoffice/', '/api/users/workspace/',
        '/api/users/learning/', '/api/users/admin/', '/api/users/desktop-auth/',
    )) or path in {
        '/api/users/logout/', '/api/users/me/email/', '/api/users/me/password/',
        '/api/users/me/delete/',
    }):
        return account
    return select_learner(account, request.headers.get('X-UniMind-Workspace', request.GET.get('space', 'personal')))
