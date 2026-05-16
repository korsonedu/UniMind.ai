from rest_framework import serializers
from .models import Institution, User


class InstitutionSerializer(serializers.ModelSerializer):
    student_count = serializers.IntegerField(read_only=True)
    max_students = serializers.IntegerField(read_only=True)
    is_plan_active = serializers.BooleanField(read_only=True)
    features = serializers.ListField(child=serializers.CharField(), read_only=True)

    class Meta:
        model = Institution
        fields = [
            'id', 'name', 'slug', 'invite_slug',
            'contact_name', 'contact_email', 'contact_phone',
            'plan', 'plan_expires_at', 'is_active', 'is_plan_active',
            'max_students', 'student_count', 'features',
            'custom_domain', 'logo', 'description', 'notes',
            'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at',
                            'student_count', 'max_students', 'is_plan_active', 'features']


class CreateInstitutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Institution
        fields = ['name', 'slug', 'contact_name', 'contact_email', 'contact_phone',
                  'plan', 'plan_expires_at', 'max_students_override',
                  'custom_domain', 'notes']


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
