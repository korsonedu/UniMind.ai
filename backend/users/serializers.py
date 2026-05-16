from rest_framework import serializers
from .models import User, SystemConfig, DailyPlan, ActivationCode

class UserSerializer(serializers.ModelSerializer):
    avatar_url = serializers.ReadOnlyField()
    institution = serializers.SerializerMethodField()
    is_admin = serializers.SerializerMethodField()
    is_institution_admin = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'username', 'nickname', 'role', 'elo_score', 'avatar_url', 'avatar_style', 'avatar_seed', 'bio', 'current_task', 'current_timer_end', 'today_focused_minutes', 'today_completed_tasks', 'allow_broadcast', 'show_others_broadcast', 'has_completed_initial_assessment', 'elo_reset_count', 'is_member', 'membership_tier', 'is_admin', 'is_institution_admin', 'institution', 'institution_role', 'institution_id')
        read_only_fields = ('id', 'username', 'role', 'elo_score', 'avatar_url', 'is_member', 'is_admin', 'is_institution_admin', 'institution_role', 'institution_id')

    def get_is_admin(self, obj):
        return obj.is_superuser and obj.institution_id is None

    def get_is_institution_admin(self, obj):
        return obj.institution is not None and obj.institution_role == 'admin'

    def get_institution(self, obj):
        inst = obj.institution
        if inst is None:
            return None
        return {
            'id': inst.id,
            'name': inst.name,
            'plan': inst.plan,
            'plan_label': inst.get_plan_display(),
            'is_plan_active': inst.is_plan_active,
            'max_students': inst.max_students,
            'student_count': inst.student_count,
            'invite_slug': inst.invite_slug,
        }

class ActivationCodeSerializer(serializers.ModelSerializer):
    used_by_username = serializers.CharField(source='used_by.username', read_only=True)

    class Meta:
        model = ActivationCode
        fields = ('id', 'code', 'is_used', 'used_by', 'used_at', 'duration_days', 'created_at', 'used_by_username')

class DailyPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyPlan
        fields = ('id', 'user', 'content', 'is_completed', 'completed_at', 'created_at')
        read_only_fields = ('user',)

class SystemConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemConfig
        fields = ("school_name", "school_short_name", "school_description", "school_logo", "invite_code")

class RegisterSerializer(serializers.ModelSerializer):
    username = serializers.CharField(required=False)
    email = serializers.EmailField(required=True)
    code = serializers.CharField(required=True, write_only=True)
    nickname = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ("username", "email", "code", "nickname", "password")

    def create(self, validated_data):
        # 如果是第一个用户，设为管理员且具有后台权限
        if User.objects.count() == 0:
            user = User.objects.create_superuser(
                username=validated_data["username"],
                password=validated_data["password"],
                nickname=validated_data["username"],
                role="admin"
            )
        else:
            user = User.objects.create_user(
                username=validated_data["username"],
                password=validated_data["password"],
                nickname=validated_data["username"],
                role="student"
            )
        return user
