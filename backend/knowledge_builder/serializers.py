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


class BlockSerializer(serializers.ModelSerializer):
    steps = StepSerializer(many=True, read_only=True)

    class Meta:
        model = models.LearningBlock
        fields = ('id', 'code', 'short_title', 'narrative_summary', 'layer', 'contraction_group', 'is_entry_block', 'node_shape', 'order', 'steps')


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

    class Meta(BuildSummarySerializer.Meta):
        fields = (*BuildSummarySerializer.Meta.fields, 'modules', 'atoms', 'atom_edges', 'blocks', 'block_edges', 'interfaces')
