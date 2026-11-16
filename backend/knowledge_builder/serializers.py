"""Explicit public representations of the two-layer graph."""
import json
from rest_framework import serializers

from . import models
from .archetypes import PROFILES


def validate_json_object(value):
    if not isinstance(value, dict):
        raise serializers.ValidationError('请提供 JSON 对象。')
    try:
        json.dumps(value, allow_nan=False)
    except (ValueError, TypeError):
        raise serializers.ValidationError('JSON 中不能包含非有限数值。')
    return value


class CreateBuildSerializer(serializers.Serializer):
    subject = serializers.CharField(max_length=200, allow_blank=False, trim_whitespace=True)
    archetype = serializers.ChoiceField(choices=('auto', *PROFILES), default='auto')
    requirements = serializers.JSONField(required=False, default=dict, validators=[validate_json_object])

    class Meta:
        fields = ('subject', 'archetype', 'requirements')


class IntakeMessageSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=('user', 'assistant'))
    content = serializers.CharField(max_length=20000)

    class Meta:
        fields = ('role', 'content')


class RequirementIntakeSerializer(serializers.Serializer):
    subject = serializers.CharField(max_length=200, trim_whitespace=True)
    mode = serializers.ChoiceField(choices=('card', 'chat'), default='card')
    messages = IntakeMessageSerializer(many=True, required=False, max_length=40)
    card_answers = serializers.JSONField(required=False, default=dict, validators=[validate_json_object])
    self_report = serializers.CharField(required=False, allow_blank=True, max_length=10000)
    diagnostic_questions = serializers.ListField(child=serializers.DictField(), required=False, max_length=4)
    diagnostic_answers = serializers.DictField(child=serializers.CharField(max_length=20), required=False)

    def validate(self, attrs):
        try:
            json.dumps(attrs, allow_nan=False)
        except (ValueError, TypeError):
            raise serializers.ValidationError('JSON 中不能包含非有限数值。')
        return attrs

    class Meta:
        fields = ('subject', 'mode', 'messages', 'card_answers', 'self_report', 'diagnostic_questions', 'diagnostic_answers')


class BuildSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.KnowledgeTreeBuild
        fields = ('id', 'subject', 'requirements', 'status', 'current_stage', 'archetype', 'dispatch_profile', 'stats', 'error_message', 'created_at', 'updated_at', 'completed_at')


class ModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.TreeModule
        fields = ('id', 'parent', 'code', 'title', 'path', 'depth', 'order')


class AtomSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.TreeAtomPoint
        fields = ('id', 'module', 'code', 'name', 'goal_statement', 'parent_path', 'goal_type', 'granularity_minutes', 'cognitive_level', 'key_elements', 'prerequisites_hint', 'common_misconceptions', 'branch_condition', 'order')


class AtomEdgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.TreeAtomEdge
        fields = ('id', 'from_atom', 'to_atom', 'edge_strength', 'relation_label', 'rationale', 'confidence', 'similarity')


class StepAtomSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.BlockStepAtom
        fields = ('atom', 'membership_type', 'position')


class StepSerializer(serializers.ModelSerializer):
    step_atoms = StepAtomSerializer(many=True, read_only=True)

    class Meta:
        model = models.BlockStep
        fields = ('id', 'step_index', 'step_title', 'step_role', 'branch_condition', 'intra_lines', 'step_atoms')


class BlockResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.BlockResource
        fields = ('id', 'block', 'step', 'atom', 'public_asset', 'source_kind', 'asset_track', 'pedagogical_role', 'locator', 'region_scope', 'title', 'url', 'excerpt', 'course_id', 'library_resource_id', 'marketplace_listing_id', 'created_at')


class UserBlockProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.UserBlockProgress
        fields = ('block', 'status', 'best_accuracy', 'last_accuracy', 'core_passed', 'attempt_count', 'mastered_atom_ids', 'weak_atom_ids', 'last_quiz_result', 'completed_at', 'updated_at')


class BlockResourceInputSerializer(serializers.Serializer):
    url = serializers.URLField(required=False, max_length=1000)
    course_id = serializers.IntegerField(required=False, min_value=1)
    library_resource_id = serializers.IntegerField(required=False, min_value=1)
    public_asset_id = serializers.IntegerField(required=False, min_value=1)
    marketplace_listing_id = serializers.IntegerField(required=False, min_value=1)
    asset_track = serializers.ChoiceField(choices=models.BlockResource.AssetTrack.values, required=False)
    pedagogical_role = serializers.CharField(required=False, allow_blank=True, max_length=32)
    locator = serializers.CharField(required=False, allow_blank=True, max_length=120)
    step_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    atom_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    save_to_library = serializers.BooleanField(default=False)

    def validate_url(self, value):
        if not value.startswith('https://'):
            raise serializers.ValidationError('请提供公开 HTTPS 链接。')
        return value

    class Meta:
        fields = ('url', 'course_id', 'library_resource_id', 'public_asset_id', 'marketplace_listing_id', 'asset_track', 'pedagogical_role', 'locator', 'step_id', 'atom_id', 'save_to_library')


class AttachBlockResourceSerializer(BlockResourceInputSerializer):
    class Meta:
        fields = ('url', 'course_id', 'library_resource_id', 'public_asset_id', 'marketplace_listing_id', 'asset_track', 'pedagogical_role', 'locator', 'step_id', 'atom_id', 'save_to_library')


class PublicAssetCatalogSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.PublicAssetCatalog
        fields = ('id', 'subject', 'title', 'url', 'source_kind', 'asset_track', 'pedagogical_role', 'region_scope', 'description', 'topic_keywords', 'segments', 'created_at')


class TreePublicAssetImportSerializer(serializers.Serializer):
    url = serializers.URLField(required=False, max_length=1000)
    title = serializers.CharField(required=False, max_length=200)
    asset_track = serializers.ChoiceField(choices=models.BlockResource.AssetTrack.values, required=False)
    pedagogical_role = serializers.CharField(required=False, allow_blank=True, max_length=32)
    outline_text = serializers.CharField(required=False, allow_blank=True, max_length=100000)
    public_asset_id = serializers.IntegerField(required=False, min_value=1)
    marketplace_listing_id = serializers.IntegerField(required=False, min_value=1)
    album_id = serializers.IntegerField(required=False, min_value=1)
    target_block_id = serializers.IntegerField(required=False, min_value=1)
    target_atom_id = serializers.IntegerField(required=False, min_value=1)

    def validate_url(self, value):
        if not value.startswith('https://'):
            raise serializers.ValidationError('请提供公开 HTTPS 链接。')
        return value

    def validate(self, attrs):
        sources = ('url', 'public_asset_id', 'marketplace_listing_id', 'album_id')
        if sum(bool(attrs.get(key)) for key in sources) != 1:
            raise serializers.ValidationError('请指定一个公开链接、资产池条目、免费市场资源或课程专辑。')
        return attrs

    class Meta:
        fields = ('url', 'title', 'asset_track', 'pedagogical_role', 'outline_text', 'public_asset_id', 'marketplace_listing_id', 'album_id', 'target_block_id', 'target_atom_id')


class BlockResourceUpdateSerializer(serializers.Serializer):
    resource_id = serializers.IntegerField(min_value=1)
    block_id = serializers.IntegerField(required=False, min_value=1)
    step_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    atom_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    asset_track = serializers.ChoiceField(choices=models.BlockResource.AssetTrack.values, required=False)
    pedagogical_role = serializers.CharField(required=False, allow_blank=True, max_length=32)
    locator = serializers.CharField(required=False, allow_blank=True, max_length=120)

    class Meta:
        fields = ('resource_id', 'block_id', 'step_id', 'atom_id', 'asset_track', 'pedagogical_role', 'locator')


class BlockQuizRequestSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=('generate', 'submit'), default='generate')
    mode = serializers.ChoiceField(choices=('objective', 'challenge'), default='objective')
    retest = serializers.BooleanField(default=False)
    questions = serializers.ListField(child=serializers.DictField(), required=False, allow_empty=False)
    answers = serializers.DictField(child=serializers.CharField(allow_blank=True, max_length=20000), required=False)

    def validate(self, attrs):
        if attrs['action'] == 'submit' and not {'questions', 'answers'} <= attrs.keys():
            raise serializers.ValidationError('请提交完整检测题目和答案。')
        return attrs

    class Meta:
        fields = ('action', 'mode', 'retest', 'questions', 'answers')


class BlockSerializer(serializers.ModelSerializer):
    steps = StepSerializer(many=True, read_only=True)
    resources = BlockResourceSerializer(many=True, read_only=True)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        user_id = request.user.pk if request and request.user.is_authenticated else None
        from .public_asset_service import get_region_preference
        region = get_region_preference(request.user if request else None, request,
                                       request.query_params.get('region', '') if request else '')
        visible_ids = {row.pk for row in instance.resources.all()
                       if (row.source_kind != 'library' or user_id is not None and row.created_by_id == user_id)
                       and (region != 'cn' or row.region_scope != 'intl')}
        data['resources'] = [row for row in data['resources'] if row['id'] in visible_ids]
        return data

    class Meta:
        model = models.LearningBlock
        fields = ('id', 'code', 'short_title', 'narrative_summary', 'layer', 'contraction_group', 'is_entry_block', 'node_shape', 'order', 'steps', 'resources')


class BlockEdgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.BlockEdge
        fields = ('id', 'from_block', 'to_block', 'edge_kind', 'directness_score', 'hard_constraint_count', 'hard_net', 'similarity', 'is_retained', 'exclusion_reason', 'rationale')


class InterfaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.CrossBlockInterface
        fields = ('id', 'block_edge', 'from_atom', 'to_atom', 'interface_role', 'bridge_explanation')


class FullKnowledgeTreeSerializer(BuildSummarySerializer):
    modules = ModuleSerializer(many=True, read_only=True)
    atoms = AtomSerializer(many=True, read_only=True)
    atom_edges = AtomEdgeSerializer(many=True, read_only=True)
    blocks = BlockSerializer(many=True, read_only=True)
    block_edges = BlockEdgeSerializer(many=True, read_only=True)
    interfaces = InterfaceSerializer(source='cross_block_interfaces', many=True, read_only=True)
    block_progress = serializers.SerializerMethodField()

    def get_block_progress(self, instance):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return []
        return UserBlockProgressSerializer(instance.user_block_progress.filter(user=request.user), many=True).data

    class Meta(BuildSummarySerializer.Meta):
        fields = (*BuildSummarySerializer.Meta.fields, 'modules', 'atoms', 'atom_edges', 'blocks', 'block_edges', 'interfaces', 'block_progress')
