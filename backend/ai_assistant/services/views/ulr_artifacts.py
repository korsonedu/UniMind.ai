"""Keep model-authored conversation assets private until the answer commits."""
from django.db import transaction

from ai_assistant.models import AIChatMessage
from ai_assistant.services.learning_components import persist_template
from ai_assistant.services.learning_experiments import ExperimentConflict, anchor_for


class TurnArtifacts:
    def __init__(self, parent=None):
        self.anchor_id = parent.anchor_id if parent else None
        self.changes = parent.changes.copy() if parent else {}

    def overlay(self, anchor):
        if self.anchor_id is not None and anchor.pk != self.anchor_id:
            raise ExperimentConflict()
        for key, (original, _) in self.changes.items():
            if anchor.metadata.get(key, {}) != original:
                raise ExperimentConflict('交互资产已变化，请重新读取后继续。')
        anchor.metadata = {**anchor.metadata, **{key: updated for key, (_, updated) in self.changes.items()}}
        return anchor

    def stage(self, anchor, key, updated):
        self.anchor_id = anchor.pk
        original = self.changes[key][0] if key in self.changes else anchor.metadata.get(key, {})
        self.changes[key] = original, updated

    @transaction.atomic
    def commit(self, user, conversation_id):
        if not self.changes:
            return
        anchor = anchor_for(user, conversation_id)
        original = anchor.metadata
        updated = self.overlay(anchor).metadata
        if not AIChatMessage.objects.filter(pk=anchor.pk, metadata=original).update(metadata=updated):
            raise ExperimentConflict()
        if 'learning_experiments' in self.changes:
            before, after = self.changes['learning_experiments']
            for key, item in after.items():
                if item.get('save_template') and before.get(key) != item:
                    persist_template(user, item)
