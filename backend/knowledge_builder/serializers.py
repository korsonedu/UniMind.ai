"""Explicit public representations of the two-layer graph."""
import json
from rest_framework import serializers

from . import models
from .archetypes import PROFILES
from .build_state import can_resume_build, lock_build_for_resume
from .public_asset_service import compute_atom_difficulty
from .source_parsers import clean_resource_excerpt


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
    can_resume = serializers.SerializerMethodField()

    class Meta:
        model = models.KnowledgeTreeBuild
        fields = ('id', 'subject', 'requirements', 'status', 'current_stage', 'archetype', 'dispatch_profile', 'stats', 'error_message', 'created_at', 'updated_at', 'completed_at', 'can_resume')

    def get_can_resume(self, obj):
        request = self.context.get('request')
        return bool(request and obj.created_by_id == request.user.pk
                    and can_resume_build(obj)
                    and (obj.status == models.KnowledgeTreeBuild.Status.FAILED
                         or self.context.get('check_build_lock') and lock_build_for_resume(obj)))


class ModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.TreeModule
        fields = ('id', 'parent', 'code', 'title', 'path', 'depth', 'order')


class AtomSerializer(serializers.ModelSerializer):
    difficulty_tier = serializers.SerializerMethodField()
    difficulty_label = serializers.SerializerMethodField()

    def get_difficulty_tier(self, instance):
        return compute_atom_difficulty(instance)[0]

    def get_difficulty_label(self, instance):
        return compute_atom_difficulty(instance)[1]

    class Meta:
        model = models.TreeAtomPoint
        fields = ('id', 'module', 'code', 'name', 'goal_statement', 'parent_path', 'goal_type', 'granularity_minutes', 'cognitive_level', 'key_elements', 'prerequisites_hint', 'common_misconceptions', 'branch_condition', 'order', 'difficulty_tier', 'difficulty_label')


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
    user_vote = serializers.SerializerMethodField()
    excerpt = serializers.SerializerMethodField()

    def get_user_vote(self, instance):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return 0
        return instance.feedbacks.filter(user=user).values_list('vote', flat=True).first() or 0

    def get_excerpt(self, instance):
        return clean_resource_excerpt(instance.excerpt, max_len=600)

    class Meta:
        model = models.BlockResource
        fields = ('id', 'block', 'step', 'atom', 'public_asset', 'source_kind', 'asset_track', 'pedagogical_role', 'locator', 'region_scope', 'title', 'url', 'excerpt', 'course_id', 'library_resource_id', 'marketplace_listing_id', 'origin', 'match_method', 'match_score', 'upvotes', 'downvotes', 'user_vote', 'created_at')


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
    action = serializers.ChoiceField(choices=('generate', 'read'), default='generate')
    project_id = serializers.IntegerField(min_value=1)
    mode = serializers.ChoiceField(choices=('objective', 'challenge'), default='objective')
    retest = serializers.BooleanField(default=False)

    class Meta:
        fields = ('action', 'project_id', 'mode', 'retest')


class BlockSerializer(serializers.ModelSerializer):
    difficulty_summary = serializers.SerializerMethodField()
    steps = StepSerializer(many=True, read_only=True)
    resources = BlockResourceSerializer(many=True, read_only=True)

    def get_difficulty_summary(self, instance):
        summary = {'L1': 0, 'L2': 0, 'L3': 0}
        seen = set()
        for step in instance.steps.all():
            for membership in step.step_atoms.all():
                if membership.atom_id in seen:
                    continue
                seen.add(membership.atom_id)
                tier, _ = compute_atom_difficulty(membership.atom)
                summary[tier] += 1
        return summary

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        from .block_study import visible_block_resources
        visible_ids = set(visible_block_resources(request.user if request else None, instance, request=request).values_list('pk', flat=True))
        data['resources'] = [row for row in data['resources'] if row['id'] in visible_ids]
        return data

    class Meta:
        model = models.LearningBlock
        fields = ('id', 'code', 'short_title', 'narrative_summary', 'layer', 'contraction_group', 'is_entry_block', 'node_shape', 'order', 'difficulty_summary', 'steps', 'resources')


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
    region_pref = serializers.SerializerMethodField()

    def get_region_pref(self, instance):
        from .public_asset_service import get_region_preference
        request = self.context.get('request')
        return get_region_preference(request.user if request else None, request)

    class Meta(BuildSummarySerializer.Meta):
        fields = (*BuildSummarySerializer.Meta.fields, 'modules', 'atoms', 'atom_edges', 'blocks', 'block_edges', 'interfaces', 'region_pref')


class SourceAlignmentSerializer(serializers.ModelSerializer):
    source_title = serializers.CharField(source='source_document.title', read_only=True)
    source_kind = serializers.CharField(source='source_document.source_kind', read_only=True)
    block_title = serializers.CharField(source='block.short_title', read_only=True)
    atom_name = serializers.SerializerMethodField()
    full_excerpt = serializers.SerializerMethodField()

    def get_atom_name(self, instance):
        return instance.atom.name if instance.atom_id and instance.atom else ''

    def get_full_excerpt(self, instance):
        sections = instance.source_document.raw_sections if isinstance(instance.source_document.raw_sections, dict) else {}
        return clean_resource_excerpt(sections.get(instance.source_node_id) or instance.excerpt_quote, max_len=1600)

    class Meta:
        model = models.SourceAlignment
        fields = (
            'id', 'source_document', 'source_title', 'source_kind',
            'block', 'block_title', 'atom', 'atom_name',
            'source_node_id', 'section_title', 'locator', 'source_url',
            'excerpt_quote', 'full_excerpt', 'alignment_role', 'match_reason',
            'confidence', 'is_verified', 'created_at', 'updated_at',
        )


class TreeSourceDocumentSerializer(serializers.ModelSerializer):
    alignment_count = serializers.SerializerMethodField()
    aligned_block_count = serializers.SerializerMethodField()
    aligned_atom_count = serializers.SerializerMethodField()
    node_count = serializers.SerializerMethodField()
    alignments = SourceAlignmentSerializer(many=True, read_only=True)

    def get_alignment_count(self, instance):
        return instance.alignments.count()

    def get_aligned_block_count(self, instance):
        return instance.alignments.values('block_id').distinct().count()

    def get_aligned_atom_count(self, instance):
        return instance.alignments.exclude(atom_id__isnull=True).values('atom_id').distinct().count()

    def get_node_count(self, instance):
        return len(instance.raw_sections or {})

    class Meta:
        model = models.TreeSourceDocument
        fields = (
            'id', 'build', 'source_kind', 'title', 'url', 'file_key',
            'is_primary', 'parse_status', 'parse_error', 'toc_tree',
            'node_count', 'alignment_count', 'aligned_block_count',
            'aligned_atom_count', 'alignments', 'created_at', 'updated_at',
        )


class CreateTreeSourceSerializer(serializers.Serializer):
    source_kind = serializers.ChoiceField(choices=models.TreeSourceDocument.SourceKind.values, default=models.TreeSourceDocument.SourceKind.MARKDOWN)
    title = serializers.CharField(required=False, allow_blank=True, max_length=240)
    url = serializers.URLField(required=False, allow_blank=True, max_length=1000)
    content = serializers.CharField(required=False, allow_blank=True, max_length=300000)
    outline_text = serializers.CharField(required=False, allow_blank=True, max_length=100000)
    album_id = serializers.IntegerField(required=False, min_value=1)
    is_primary = serializers.BooleanField(default=True)
    auto_align = serializers.BooleanField(default=False)

    def validate_url(self, value):
        if value and not value.startswith('https://'):
            raise serializers.ValidationError('请提供公开 HTTPS 链接。')
        return value

    class Meta:
        fields = ('source_kind', 'title', 'url', 'content', 'outline_text', 'album_id', 'is_primary', 'auto_align')


class SourceAlignmentUpdateSerializer(serializers.Serializer):
    is_verified = serializers.BooleanField(required=True)

    class Meta:
        fields = ('is_verified',)


class AtomMicroLessonSerializer(serializers.ModelSerializer):
    exists = serializers.SerializerMethodField()
    difficulty_label = serializers.SerializerMethodField()

    def get_exists(self, instance):
        return True

    def get_difficulty_label(self, instance):
        return {'L1': '基础速通', 'L2': '机制辨析', 'L3': '硬核攻坚'}.get(instance.difficulty_tier, '基础速通')

    class Meta:
        model = models.AtomMicroLesson
        fields = (
            'exists', 'id', 'build', 'atom', 'version', 'difficulty_tier', 'difficulty_label',
            'style', 'is_source_grounded', 'grounded_source_ids', 'hook_summary', 'pitfalls',
            'narration_script', 'visuals', 'quick_check', 'citations', 'status',
            'error_message', 'created_at', 'updated_at',
        )


class AtomMicroLessonRequestSerializer(serializers.Serializer):
    regenerate = serializers.BooleanField(default=False)
    style = serializers.ChoiceField(choices=('balanced', 'intuition', 'exam', 'visual'), default='balanced')

    class Meta:
        fields = ('regenerate', 'style')
