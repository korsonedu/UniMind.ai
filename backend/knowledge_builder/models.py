"""Persistent two-layer knowledge graph and build lifecycle."""
import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class KnowledgeTreeBuild(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING'
        RUNNING = 'RUNNING'
        COMPLETED = 'COMPLETED'
        FAILED = 'FAILED'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subject = models.CharField(max_length=200)
    requirements = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    current_stage = models.CharField(max_length=64, blank=True)
    archetype = models.CharField(max_length=40, default='auto')
    dispatch_profile = models.JSONField(default=dict)
    stats = models.JSONField(default=dict)
    error_message = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='knowledge_tree_builds')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class TreeModule(models.Model):
    build = models.ForeignKey(KnowledgeTreeBuild, on_delete=models.CASCADE, related_name='modules')
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='children')
    code = models.CharField(max_length=40)
    title = models.CharField(max_length=200)
    path = models.CharField(max_length=500)
    depth = models.PositiveSmallIntegerField(default=1)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ('order', 'pk')
        constraints = [models.UniqueConstraint(fields=['build', 'code'], name='kb_module_code')]


class TreeAtomPoint(models.Model):
    build = models.ForeignKey(KnowledgeTreeBuild, on_delete=models.CASCADE, related_name='atoms')
    module = models.ForeignKey(TreeModule, on_delete=models.CASCADE, related_name='atoms')
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=200)
    goal_statement = models.TextField()
    parent_path = models.CharField(max_length=500)
    goal_type = models.CharField(max_length=40)
    granularity_minutes = models.PositiveSmallIntegerField(validators=[MinValueValidator(3), MaxValueValidator(6)])
    cognitive_level = models.CharField(max_length=40)
    key_elements = models.JSONField(default=list)
    prerequisites_hint = models.JSONField(default=list)
    common_misconceptions = models.JSONField(default=list)
    branch_condition = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ('order', 'pk')
        constraints = [
            models.UniqueConstraint(fields=['build', 'code'], name='kb_atom_code'),
            models.CheckConstraint(condition=models.Q(granularity_minutes__gte=3, granularity_minutes__lte=6), name='kb_atom_minutes'),
        ]


class TreeAtomEdge(models.Model):
    build = models.ForeignKey(KnowledgeTreeBuild, on_delete=models.CASCADE, related_name='atom_edges')
    from_atom = models.ForeignKey(TreeAtomPoint, on_delete=models.CASCADE, related_name='outgoing_edges')
    to_atom = models.ForeignKey(TreeAtomPoint, on_delete=models.CASCADE, related_name='incoming_edges')
    edge_strength = models.CharField(max_length=24, choices=[(v, v) for v in ('strong', 'weak', 'contrast', 'bidirectional')])
    relation_label = models.CharField(max_length=64, blank=True)
    rationale = models.TextField()
    confidence = models.FloatField(default=1.0)
    similarity = models.FloatField(default=0.0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['build', 'from_atom', 'to_atom', 'edge_strength'], name='kb_atom_edge_unique')]


class LearningBlock(models.Model):
    build = models.ForeignKey(KnowledgeTreeBuild, on_delete=models.CASCADE, related_name='blocks')
    code = models.CharField(max_length=32)
    short_title = models.CharField(max_length=120)
    narrative_summary = models.TextField()
    layer = models.PositiveSmallIntegerField(default=1)
    contraction_group = models.CharField(max_length=64, blank=True)
    is_entry_block = models.BooleanField(default=False)
    node_shape = models.JSONField(default=dict)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ('order', 'pk')
        constraints = [models.UniqueConstraint(fields=['build', 'code'], name='kb_block_code')]


class BlockEdge(models.Model):
    build = models.ForeignKey(KnowledgeTreeBuild, on_delete=models.CASCADE, related_name='block_edges')
    from_block = models.ForeignKey(LearningBlock, on_delete=models.CASCADE, related_name='outgoing_edges')
    to_block = models.ForeignKey(LearningBlock, on_delete=models.CASCADE, related_name='incoming_edges')
    edge_kind = models.CharField(max_length=24, choices=[(v, v) for v in ('unidirectional', 'bidirectional')])
    directness_score = models.FloatField(default=0.0)
    hard_constraint_count = models.PositiveIntegerField(default=0)
    hard_net = models.PositiveIntegerField(default=0)
    similarity = models.FloatField(default=0.0)
    is_retained = models.BooleanField(default=True)
    exclusion_reason = models.CharField(max_length=255, blank=True)
    rationale = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['build', 'from_block', 'to_block'], name='kb_block_edge_unique')]


class BlockStep(models.Model):
    block = models.ForeignKey(LearningBlock, on_delete=models.CASCADE, related_name='steps')
    step_index = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    step_title = models.CharField(max_length=120)
    step_role = models.CharField(max_length=64)
    branch_condition = models.TextField(blank=True)
    intra_lines = models.JSONField(default=list)

    class Meta:
        ordering = ('step_index',)
        constraints = [models.UniqueConstraint(fields=['block', 'step_index'], name='kb_block_step_unique')]


class BlockStepAtom(models.Model):
    step = models.ForeignKey(BlockStep, on_delete=models.CASCADE, related_name='step_atoms')
    atom = models.OneToOneField(TreeAtomPoint, on_delete=models.CASCADE, related_name='block_assignment')
    membership_type = models.CharField(max_length=16, choices=[('core', 'core'), ('extension', 'extension')])
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ('position', 'pk')


class CrossBlockInterface(models.Model):
    build = models.ForeignKey(KnowledgeTreeBuild, on_delete=models.CASCADE, related_name='cross_block_interfaces')
    block_edge = models.ForeignKey(BlockEdge, on_delete=models.CASCADE, related_name='interfaces')
    from_atom = models.ForeignKey(TreeAtomPoint, on_delete=models.CASCADE, related_name='exit_interfaces')
    to_atom = models.ForeignKey(TreeAtomPoint, on_delete=models.CASCADE, related_name='entry_interfaces')
    interface_role = models.CharField(max_length=64)
    bridge_explanation = models.TextField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['block_edge', 'from_atom', 'to_atom'], name='kb_interface_unique')]


class PublicAssetCatalog(models.Model):
    class AssetTrack(models.TextChoices):
        SPINE = 'spine', 'spine'
        SPOTLIGHT = 'spotlight', 'spotlight'
        WIKI = 'wiki', 'wiki'

    subject = models.CharField(max_length=200, db_index=True)
    title = models.CharField(max_length=200)
    url = models.CharField(max_length=1000)
    source_kind = models.CharField(max_length=24, default='web')
    asset_track = models.CharField(max_length=24, choices=AssetTrack.choices, default=AssetTrack.SPOTLIGHT)
    pedagogical_role = models.CharField(max_length=32, blank=True, default='')
    region_scope = models.CharField(max_length=16, choices=[('cn', 'cn'), ('intl', 'intl'), ('global', 'global')], default='global')
    description = models.TextField(blank=True)
    topic_keywords = models.JSONField(default=list)
    segments = models.JSONField(default=list)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='contributed_public_assets')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-id',)
        constraints = [models.UniqueConstraint(fields=['subject', 'url'], name='kb_public_asset_subject_url')]


class BlockResource(models.Model):
    class SourceKind(models.TextChoices):
        COURSE = 'course', 'course'
        LIBRARY = 'library', 'library'
        WEB = 'web', 'web'
        BILIBILI = 'bilibili', 'bilibili'
        GITHUB = 'github', 'github'
        WIKIPEDIA = 'wikipedia', 'wikipedia'
        YOUTUBE = 'youtube', 'youtube'
        MARKETPLACE = 'marketplace', 'marketplace'

    class AssetTrack(models.TextChoices):
        SPINE = 'spine', 'spine'
        SPOTLIGHT = 'spotlight', 'spotlight'
        WIKI = 'wiki', 'wiki'

    build = models.ForeignKey(KnowledgeTreeBuild, on_delete=models.CASCADE, related_name='block_resources')
    block = models.ForeignKey(LearningBlock, on_delete=models.CASCADE, related_name='resources')
    step = models.ForeignKey(BlockStep, null=True, blank=True, on_delete=models.SET_NULL, related_name='resources')
    atom = models.ForeignKey(TreeAtomPoint, null=True, blank=True, on_delete=models.SET_NULL, related_name='resources')
    public_asset = models.ForeignKey(PublicAssetCatalog, null=True, blank=True, on_delete=models.SET_NULL, related_name='mounted_resources')
    source_kind = models.CharField(max_length=24, choices=SourceKind.choices, default=SourceKind.WEB)
    asset_track = models.CharField(max_length=24, choices=AssetTrack.choices, default=AssetTrack.SPOTLIGHT)
    pedagogical_role = models.CharField(max_length=32, blank=True, default='')
    locator = models.CharField(max_length=120, blank=True, default='')
    region_scope = models.CharField(max_length=16, choices=[('cn', 'cn'), ('intl', 'intl'), ('global', 'global')], default='global')
    title = models.CharField(max_length=200)
    url = models.CharField(max_length=1000)
    excerpt = models.TextField(blank=True)
    course_id = models.PositiveIntegerField(null=True, blank=True)
    library_resource_id = models.PositiveIntegerField(null=True, blank=True)
    marketplace_listing_id = models.PositiveIntegerField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='created_block_resources')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('id',)
