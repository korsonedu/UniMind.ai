"""Explicit public representations of the two-layer graph."""
from rest_framework import serializers

from . import models
from .archetypes import PROFILES


class CreateBuildSerializer(serializers.Serializer):
    subject = serializers.CharField(max_length=200, allow_blank=False, trim_whitespace=True)
    archetype = serializers.ChoiceField(choices=('auto', *PROFILES), default='auto')

    class Meta:
        fields = ('subject', 'archetype')


class BuildSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = models.KnowledgeTreeBuild
        fields = ('id', 'subject', 'status', 'current_stage', 'archetype', 'dispatch_profile', 'stats', 'error_message', 'created_at', 'updated_at', 'completed_at')


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
