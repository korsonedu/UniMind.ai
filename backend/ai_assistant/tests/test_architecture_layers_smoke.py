"""Guardrail tests for the four-layer service package layout and legacy module-identity aliases."""
import importlib
from pathlib import Path
from unittest.mock import patch


MIGRATED_MODULES = {
    'learning_task_evidence': 'facts',
    'diagnostic_revisions': 'facts',
    'bayesian_evidence': 'state.bep',
    'bayesian_evaluation': 'state.bep',
    'prism_kernel': 'state.prism',
    'prism_memory': 'state.prism',
    'prism_mapping': 'state.prism',
    'prism_outcomes': 'state.prism',
    'prism_feedback': 'state.prism',
    'prism_replay': 'state.prism',
    'prism_migration': 'state.prism',
    'ulr_memory': 'state.sdtm',
    'ulr_profile': 'state.sdtm',
    'ulr_teaching': 'decision',
    'prism_gate': 'decision',
    'prism_execution': 'decision',
    'ulr_artifacts': 'views',
    'ulr_config': 'runtime',
    'ulr_outbox': 'runtime',
    'ulr_structured': 'runtime',
    'ulr_grading': 'runtime',
    'ulr_history': 'runtime',
    'ulr_capabilities': 'runtime',
    'ulr_tool_program': 'runtime',
    'ulr_runtime': 'runtime',
}


def test_canonical_and_legacy_imports_share_identical_module_object():
    for name, subpkg in MIGRATED_MODULES.items():
        canonical = importlib.import_module(f'ai_assistant.services.{subpkg}.{name}')
        legacy = importlib.import_module(f'ai_assistant.services.{name}')
        assert legacy is canonical, f'{name}: legacy alias must point to canonical module object'
        expected_suffix = Path('services', *subpkg.split('.'), f'{name}.py')
        assert Path(legacy.__file__).as_posix().endswith(expected_suffix.as_posix())


def test_patch_on_legacy_alias_targets_canonical_module():
    from ai_assistant.services.runtime import ulr_config as canonical_config
    with patch('ai_assistant.services.ulr_config.ulr_enabled', return_value=True):
        assert canonical_config.ulr_enabled() is True


def test_teaching_sidecar_hashes_real_canonical_source_bytes():
    from ai_assistant.services import teaching_sidecar
    from ai_assistant.services.state.prism import prism_kernel

    real_bytes = Path(prism_kernel.__file__).read_bytes()
    assert teaching_sidecar._source_bytes('ai_assistant/services/prism_kernel.py') == real_bytes
    assert b'sys.modules[__name__] = _impl' not in real_bytes
