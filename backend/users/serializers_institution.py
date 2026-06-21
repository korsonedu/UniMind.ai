from rest_framework import serializers
from .models import Institution, InstitutionInvite, JoinRequest, User, APICredential, SSOConfig


class InstitutionSerializer(serializers.ModelSerializer):
    student_count = serializers.IntegerField(read_only=True)
    max_students = serializers.IntegerField(read_only=True)
    is_plan_active = serializers.BooleanField(read_only=True)
    features = serializers.ListField(child=serializers.CharField(), read_only=True)
    parent_id = serializers.IntegerField(read_only=True, allow_null=True)
    children_count = serializers.SerializerMethodField()
    inherit_plan = serializers.BooleanField(read_only=True)

    class Meta:
        model = Institution
        fields = [
            'id', 'name', 'slug', 'invite_slug',
            'contact_name', 'contact_email', 'contact_phone',
            'plan', 'plan_expires_at', 'is_active', 'is_plan_active',
            'max_students', 'student_count', 'features',
            'custom_domain', 'logo', 'business_type', 'student_scale', 'description', 'notes',
            'parent_id', 'children_count', 'inherit_plan',
            'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at',
                            'student_count', 'max_students', 'is_plan_active', 'features',
                            'parent_id', 'children_count', 'inherit_plan']

    def get_children_count(self, obj):
        return obj.children.count()


class CreateInstitutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Institution
        fields = ['name', 'slug', 'contact_name', 'contact_email', 'contact_phone',
                  'plan', 'plan_expires_at', 'max_students_override',
                  'custom_domain', 'business_type', 'notes']


class ChangePlanSerializer(serializers.Serializer):
    plan = serializers.ChoiceField(choices=Institution.PLAN_CHOICES)
    plan_expires_at = serializers.DateTimeField(required=False, allow_null=True)


class InstitutionStudentSerializer(serializers.ModelSerializer):
    avatar_url = serializers.ReadOnlyField()
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'nickname', 'elo_score', 'avatar_url',
                  'institution_role', 'date_joined', 'last_active']


class CreateStudentSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    nickname = serializers.CharField(max_length=100, required=False, allow_blank=True)
    password = serializers.CharField(max_length=128, write_only=True)


class InstitutionFeatureSerializer(serializers.Serializer):
    """返回当前用户所属机构的信息 + 功能列表"""
    is_platform_admin = serializers.BooleanField()
    institution = serializers.DictField(allow_null=True)
    features = serializers.ListField(child=serializers.CharField())
    usage = serializers.DictField(allow_null=True, required=False)


class InstitutionInviteSerializer(serializers.ModelSerializer):
    class Meta:
        model = InstitutionInvite
        fields = ['id', 'slug', 'assigned_role', 'max_uses', 'used_count',
                  'expires_at', 'requires_approval', 'is_active',
                  'created_by', 'created_at']
        read_only_fields = ['id', 'slug', 'used_count', 'created_by', 'created_at']


class CreateInstitutionInviteSerializer(serializers.ModelSerializer):
    class Meta:
        model = InstitutionInvite
        fields = ['assigned_role', 'max_uses', 'expires_at', 'requires_approval']


class JoinRequestSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.username', read_only=True)
    user_nickname = serializers.CharField(source='user.nickname', read_only=True)
    invite_slug_used = serializers.CharField(source='invite.slug', read_only=True, allow_null=True)

    class Meta:
        model = JoinRequest
        fields = ['id', 'user', 'user_name', 'user_nickname', 'invite',
                  'invite_slug_used', 'status', 'message', 'reviewed_by',
                  'created_at', 'reviewed_at']
        read_only_fields = ['id', 'user', 'invite', 'reviewed_by', 'created_at', 'reviewed_at']


class InstitutionChildSerializer(serializers.ModelSerializer):
    """子校区列表用轻量序列化器。"""
    student_count = serializers.IntegerField(read_only=True)
    staff_count = serializers.SerializerMethodField()

    class Meta:
        model = Institution
        fields = ['id', 'name', 'slug', 'plan', 'inherit_plan', 'is_active',
                  'student_count', 'staff_count', 'created_at']

    def get_staff_count(self, obj):
        return obj.students.filter(institution_role__in=('owner', 'teacher', 'registrar')).count()


class APICredentialSerializer(serializers.ModelSerializer):
    class Meta:
        model = APICredential
        fields = ['id', 'name', 'key_id', 'scopes', 'rate_limit', 'is_active',
                  'last_used_at', 'created_at']
        read_only_fields = ['id', 'key_id', 'last_used_at', 'created_at']


class SSOConfigSerializer(serializers.ModelSerializer):
    client_secret = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = SSOConfig
        fields = ['id', 'provider', 'enabled', 'client_id', 'client_secret',
                  'redirect_uri', 'domain_whitelist', 'auto_join', 'default_role',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']
