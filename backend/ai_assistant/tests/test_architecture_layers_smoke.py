"""Guardrail tests for the four-layer service package layout and legacy module-identity aliases."""
import importlib
from pathlib import Path
from unittest.mock import patch


# legacy_name -> (subpackage, canonical_module_name)
MIGRATED_MODULES = {
    # L1 facts (10)
    'learning_task_evidence': ('facts', 'learning_task_evidence'),
    'diagnostic_revisions': ('facts', 'diagnostic_revisions'),
    'course_context': ('facts', 'course_context'),
    'external_audio_asr': ('facts', 'external_audio_asr'),
    'external_video_context': ('facts', 'external_video_context'),
    'learning_practice_memory': ('facts', 'learning_practice_memory'),
    'learning_diagnostics': ('facts', 'learning_diagnostics'),
    'teaching_sidecar': ('facts', 'teaching_sidecar'),
    'learning_tasks': ('facts', 'learning_tasks'),
    'learning_library': ('facts', 'learning_library'),
    # L2 state (20)
    'bayesian_evidence': ('state.bep', 'bayesian_evidence'),
    'bayesian_evaluation': ('state.bep', 'bayesian_evaluation'),
    'prism_kernel': ('state.prism', 'prism_kernel'),
    'prism_memory': ('state.prism', 'prism_memory'),
    'prism_mapping': ('state.prism', 'prism_mapping'),
    'prism_outcomes': ('state.prism', 'prism_outcomes'),
    'prism_feedback': ('state.prism', 'prism_feedback'),
    'prism_replay': ('state.prism', 'prism_replay'),
    'prism_migration': ('state.prism', 'prism_migration'),
    'ulr_memory': ('state.sdtm', 'ulr_memory'),
    'ulr_profile': ('state.sdtm', 'ulr_profile'),
    'fact_evidence': ('state.sdtm', 'fact_evidence'),
    'task_memory_store': ('state.sdtm', 'task_memory_store'),
    'task_memory_projection': ('state.sdtm', 'task_memory_projection'),
    'revision_memory': ('state.sdtm', 'revision_memory'),
    'memory_core': ('state.sdtm', 'memory_core'),
    'knowledge_build_path': ('state.knowledge', 'knowledge_build_path'),
    'learning_knowledge': ('state.knowledge', 'learning_knowledge'),
    'learning_continuity': ('state.knowledge', 'learning_continuity'),
    'teaching_shadow': ('state.rsi', 'teaching_shadow'),
    # L3 decision (7)
    'ulr_teaching': ('decision', 'ulr_teaching'),
    'prism_gate': ('decision', 'prism_gate'),
    'prism_execution': ('decision', 'prism_execution'),
    'learning_guidance': ('decision', 'learning_guidance'),
    'method_adoption': ('decision', 'method_adoption'),
    'public_methods': ('decision', 'public_methods'),
    'project_learning': ('decision', 'project_learning'),
    # L4 views (7)
    'ulr_artifacts': ('views', 'ulr_artifacts'),
    'guidance_messages': ('views', 'guidance_messages'),
    'language': ('views', 'language'),
    'title_generator': ('views', 'title_generator'),
    'dsh_cards': ('views', 'cards'),
    'dsh_stream': ('views', 'stream'),
    'planner_visuals': ('views', 'planner_visuals'),
    # ULR runtime spine (19)
    'ulr_config': ('runtime', 'ulr_config'),
    'ulr_outbox': ('runtime', 'ulr_outbox'),
    'ulr_structured': ('runtime', 'ulr_structured'),
    'ulr_grading': ('runtime', 'ulr_grading'),
    'ulr_history': ('runtime', 'ulr_history'),
    'ulr_capabilities': ('runtime', 'ulr_capabilities'),
    'ulr_tool_program': ('runtime', 'ulr_tool_program'),
    'ulr_runtime': ('runtime', 'ulr_runtime'),
    'learning_memory_oauth': ('runtime', 'learning_memory_oauth'),
    'project_learning_tools': ('runtime', 'project_learning_tools'),
    'learning_resources': ('runtime', 'learning_resources'),
    'grading_engine': ('runtime', 'grading_engine'),
    'session_tools': ('runtime', 'session_tools'),
    'dsh_scope': ('runtime', 'scope'),
    'dsh_tasks': ('runtime', 'fixed_tasks'),
    'dsh_actions': ('runtime', 'diagnostics_actions'),
    'dsh_generation': ('runtime', 'generation_gateway'),
    'chat_dispatch': ('runtime', 'chat_dispatch'),
    'exam_generator_tool_executor': ('runtime', 'exam_generator_tool_executor'),
}


def test_canonical_and_legacy_imports_share_identical_module_object():
    assert len(MIGRATED_MODULES) == 63
    for legacy_name, (subpkg, canon_name) in MIGRATED_MODULES.items():
        canonical = importlib.import_module(f'ai_assistant.services.{subpkg}.{canon_name}')
        legacy = importlib.import_module(f'ai_assistant.services.{legacy_name}')
        assert legacy is canonical, f'{legacy_name}: legacy alias must point to canonical module object'
        expected_suffix = Path('services', *subpkg.split('.'), f'{canon_name}.py')
        assert Path(legacy.__file__).as_posix().endswith(expected_suffix.as_posix())


def test_patch_on_legacy_alias_targets_canonical_module():
    from ai_assistant.services.runtime import ulr_config as canonical_config
    from ai_assistant.services.views import cards as canonical_cards
    with patch('ai_assistant.services.ulr_config.ulr_enabled', return_value=True):
        assert canonical_config.ulr_enabled() is True
    with patch('ai_assistant.services.dsh_cards.build_tool_card', return_value={'ok': True}):
        assert canonical_cards.build_tool_card('x', {}) == {'ok': True}


def test_teaching_sidecar_hashes_real_canonical_source_bytes():
    from ai_assistant.services.facts import teaching_sidecar
    from ai_assistant.services.decision import project_learning
    from ai_assistant.services.runtime import fixed_tasks
    from ai_assistant.services.state.prism import prism_kernel

    for rel, mod in (
        ('ai_assistant/services/prism_kernel.py', prism_kernel),
        ('ai_assistant/services/teaching_sidecar.py', teaching_sidecar),
        ('ai_assistant/services/project_learning.py', project_learning),
        ('ai_assistant/services/dsh_tasks.py', fixed_tasks),
    ):
        real_bytes = Path(mod.__file__).read_bytes()
        assert teaching_sidecar._source_bytes(rel) == real_bytes
        assert not real_bytes.startswith(b'"""Compatibility alias')
        assert len(real_bytes) > 500
