"""Re-render task memory inside the same transaction as reviewed corrections."""

from django.db import connection, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from ai_assistant.models import Conversation, ConversationProject, TaskMemoryProgram
from ai_assistant.services.facts import learning_diagnostics
from ai_assistant.services.decision import method_adoption
from ai_assistant.services.state.sdtm import task_memory_store
from ai_assistant.services.facts.diagnostic_revisions import revise_text_sources
from ai_assistant.services.state.sdtm.task_memory_projection import project_source


def _revise_projection(project, initial, packet, impact, now):
    old = initial.get('diagnostic_support', {})
    previous_witnesses = {row['before'][1] for row in impact['witness_changes'] if row['before']}
    refresh = (impact['submitted_tasks'].keys() | impact['pending_tasks'].keys()) & old.keys()
    refresh.update(task_id for task_id, proof in old.items()
                   if previous_witnesses.intersection(proof['deliveries']))
    if not refresh:
        return initial, packet['estimates']
    renewed = learning_diagnostics.read_sources(project, refresh, now=now)
    support = {key: proof for key, proof in old.items() if key not in refresh}
    support.update(renewed)
    excluded = learning_diagnostics.excluded_tasks(support)
    changed = learning_diagnostics.excluded_tasks(old) ^ excluded
    source = {**initial, 'diagnostic_support': support,
              'method_history': list(method_adoption.qualify_diagnostic_outcomes(
                  initial['method_history'], excluded, changed=changed))}
    dirty = {row['node_id'] + ':' + row['mode'] for row in initial['observations'] if row['task_id'] in changed}
    return source, task_memory_store.estimate_groups(source, now, previous=packet['estimates'], dirty=dirty)


@transaction.atomic
def revise_with_readouts(project, user, conversation_id, operations):
    """Apply a trusted batch and return a complete readout after each correction."""
    operations = tuple(operations)
    if not operations:
        return []
    project = task_memory_store._project(project, user)
    # Keep revision writers serialized without blocking the readout's project FK checks.
    project = ConversationProject.objects.select_for_update(
        no_key=connection.features.has_select_for_no_key_update).get(pk=project.pk, user_id=user.pk)
    if not Conversation.objects.filter(conversation_id=conversation_id, user=user, project=project).exists():
        raise PermissionDenied('对话不属于当前学习项目。')
    project, memory = task_memory_store.lock_memory(project, user)
    consistent = connection.vendor == 'sqlite' and learning_diagnostics.active()
    reuse = consistent and len(operations) > 1
    task_memory_store._bootstrap()
    program = TaskMemoryProgram.objects.filter(definition__family=task_memory_store.FAMILY).order_by('-pk').first()
    now = timezone.now()
    source = project_source(project, now=now) if reuse else None
    packet = task_memory_store._run(source, program, now) if reuse else None
    results = []
    for operation in operations:
        revision = revise_text_sources(project, now=now, **operation)
        impact = revision.value.get('impact')
        estimates = None
        incremental = reuse and impact is not None and impact['as_of'] == now.isoformat()
        if incremental:
            source, estimates = _revise_projection(project, source, packet, impact, now)
        else:
            if not consistent:
                task_memory_store._bootstrap()
                program = TaskMemoryProgram.objects.filter(
                    definition__family=task_memory_store.FAMILY).order_by('-pk').first()
            source = project_source(project, now=now)
        packet = task_memory_store._run(source, program, now, estimates=estimates)
        prepared = task_memory_store.persist_readout(project, memory, source, packet, program, now)
        from ai_assistant.services.project_learning import model_project_context, project_context
        exclusions = learning_diagnostics.excluded_tasks(source.get('diagnostic_support', {})) if consistent else None
        context = model_project_context(project_context(user, conversation_id,
            memory_read=prepared, diagnostic_excluded=exclusions))
        results.append({'revision_id': revision.pk, 'readout': prepared, 'context': context,
                        'incremental': incremental})
    return results
