"""Typed failures propagated by the knowledge tree builder."""


class KnowledgeBuilderError(Exception):
    """Base class for construction failures."""


class ArchetypeDispatchError(KnowledgeBuilderError):
    """The subject cannot be dispatched to a supported archetype."""


class EmbeddingError(KnowledgeBuilderError):
    """The online embedding service returned invalid data or failed."""


class InvariantViolationError(KnowledgeBuilderError):
    """A structural or mathematical invariant was violated."""


class PipelineRepairExhaustedError(InvariantViolationError):
    """Two repair rounds failed to produce valid stage output."""


class AIResponseError(KnowledgeBuilderError):
    """The structured AI call failed or violated its response schema."""
