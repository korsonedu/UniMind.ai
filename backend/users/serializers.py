from rest_framework import serializers
from .models import User, DailyPlan, DailyCheckIn, Achievement, UserAchievement

class UserSerializer(serializers.ModelSerializer):
    avatar_url = serializers.ReadOnlyField()
    institution = serializers.SerializerMethodField()
    is_admin = serializers.SerializerMethodField()
    is_institution_admin = serializers.SerializerMethodField()
    is_institution_owner = serializers.SerializerMethodField()
    is_institution_teacher = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'username', 'nickname', 'role', 'elo_score', 'avatar_url', 'avatar_style', 'avatar_seed', 'bio', 'current_task', 'current_timer_end', 'today_focused_minutes', 'today_completed_tasks', 'allow_broadcast', 'show_others_broadcast', 'has_completed_initial_assessment', 'is_member', 'membership_tier', 'personal_plan', 'membership_expires_at', 'membership_source', 'is_admin', 'is_institution_admin', 'is_institution_owner', 'is_institution_teacher', 'institution', 'institution_role', 'institution_id', 'tour_dismissed_at', 'tour_panel_dismissed_at')
        read_only_fields = ('id', 'username', 'role', 'elo_score', 'avatar_url', 'is_member', 'membership_tier', 'personal_plan', 'membership_expires_at', 'membership_source', 'is_admin', 'is_institution_admin', 'is_institution_owner', 'is_institution_teacher', 'institution_role', 'institution_id', 'tour_dismissed_at', 'tour_panel_dismissed_at')

    def get_is_admin(self, obj):
        return obj.is_superuser and obj.institution_id is None

    def get_is_institution_admin(self, obj):
        return obj.institution is not None and obj.institution_role in ('owner', 'teacher')

    def get_is_institution_owner(self, obj):
        return obj.institution is not None and obj.institution_role == 'owner'

    def get_is_institution_teacher(self, obj):
        return obj.institution is not None and obj.institution_role in ('owner', 'teacher')

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

class DailyPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyPlan
        fields = ('id', 'user', 'content', 'is_completed', 'completed_at', 'created_at')
        read_only_fields = ('user',)

class RegisterSerializer(serializers.ModelSerializer):
    username = serializers.CharField(required=False)
    email = serializers.EmailField(required=True)
    code = serializers.CharField(required=True, write_only=True)
    nickname = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, required=True)
    agreed_to_terms = serializers.BooleanField(required=True)

    class Meta:
        model = User
        fields = ("username", "email", "code", "nickname", "password", "agreed_to_terms")

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


class DailyCheckInSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyCheckIn
        fields = ('id', 'date', 'streak', 'created_at')
        read_only_fields = ('id', 'date', 'streak', 'created_at')


class AchievementSerializer(serializers.ModelSerializer):
    category_label = serializers.SerializerMethodField()

    class Meta:
        model = Achievement
        fields = ('id', 'key', 'name', 'description', 'icon', 'category',
                  'category_label', 'threshold')

    def get_category_label(self, obj):
        labels = {
            'streak': '连续打卡', 'diagnostic': '首次诊断',
            'question': '刷题里程碑', 'mastery': '掌握知识点',
            'exam': '考试成绩', 'social': '社交互动',
        }
        return labels.get(obj.category, obj.category)


class UserAchievementSerializer(serializers.ModelSerializer):
    achievement = AchievementSerializer(read_only=True)

    class Meta:
        model = UserAchievement
        fields = ('id', 'achievement', 'unlocked_at', 'progress')

