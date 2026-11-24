from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from quizzes.models import KnowledgeEdge, KnowledgePoint
from users.models import Institution


def synthetic_tree():
    lines = []
    for module in range(1, 5):
        lines.append(f'# [SUB-{module:02}] 模块 {module}')
        for chapter in range(1, 4):
            lines.append(f'## [CH-{chapter:02}] 篇章 {chapter}')
            for section in range(1, 3):
                lines.append(f'### [SEC-{section:02}] 小节 {section}')
                lines.extend(f'- [KP-{point:02}] 考点 {point}' for point in range(1, 4))
    return '\n'.join(lines)


def test_ulr_legacy_tree_command_publishes_only_a_complete_tree(tmp_path, settings):
    settings.DEBUG = False
    settings.UNIMIND_LEARNING_RUNTIME = 'ulr'
    settings.UNIMIND_DSH_ENABLED = settings.UNIMIND_DSH_GENERATION_ENABLED = False
    settings.UNIMIND_DSH_PYTHON = ''
    tree = synthetic_tree()
    destination = tmp_path / '合成树.md'
    destination.write_text('已有知识树', encoding='utf-8')

    def run(**options):
        call_command('generate_knowledge_tree', subject='合成树', output_dir=str(tmp_path), stdout=StringIO(), **options)

    def response(content, finish='stop'):
        return {'choices': [{'finish_reason': finish, 'message': {'content': content}}]}

    with patch('ai_engine.service.AIEngine.call_provider') as provider, \
            patch('ai_assistant.services.dsh_generation.generate') as dsh:
        for result in (response(tree.rsplit('\n', 1)[0]), response(tree, 'length')):
            provider.return_value = result
            with pytest.raises(CommandError):
                run()
            assert destination.read_text(encoding='utf-8') == '已有知识树'
        provider.return_value = response(tree)
        run(dry_run=True)
        assert destination.read_text(encoding='utf-8') == '已有知识树'
        run()
        assert destination.read_text(encoding='utf-8').rstrip() == tree
        assert provider.call_count == 4
        dsh.assert_not_called()


@pytest.mark.django_db
def test_ulr_semantic_edge_command_matches_unique_points_in_the_configured_scope(settings):
    import json

    settings.UNIMIND_LEARNING_RUNTIME = 'ulr'
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    own_subject = '合成语义关系'
    source = KnowledgePoint.objects.create(subject=own_subject, name='现金流')
    target = KnowledgePoint.objects.create(subject=own_subject, name='折现率')
    for _ in range(2):
        KnowledgePoint.objects.create(subject=own_subject, name='同名考点')
    institution = Institution.objects.create(name='合成外机构', slug='foreign-semantic-command')
    KnowledgePoint.objects.create(subject=own_subject, name='FOREIGN_MARKER', institution=institution)

    def provider(messages, **kwargs):
        assert kwargs['operation'] == 'knowledge_edge_analyze'
        assert 'FOREIGN_MARKER' not in messages[-1]['content']
        edges = [{'source_name': source.name, 'target_name': name, 'relation': 'prerequisite',
                  'confidence': 0.9} for name in (target.name, '同名考点', 'FOREIGN_MARKER')]
        return {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [{
            'function': {'name': 'submit_edges', 'arguments': json.dumps({'items': edges})},
        }]}}]}

    with patch('ai_engine.service.AIEngine.call_provider', side_effect=provider) as model:
        preview = StringIO()
        call_command('analyze_semantic_edges', subject=own_subject, dry_run=True, stdout=preview)
        assert '总计 1 条边（未写入）' in preview.getvalue() and not KnowledgeEdge.objects.exists()
        for _ in range(2):
            call_command('analyze_semantic_edges', subject=own_subject, stdout=StringIO())
        edge = KnowledgeEdge.objects.get()
        assert (edge.source_id, edge.target_id, edge.is_active, edge.institution_id) == (source.pk, target.pk, False, None)
        assert model.call_count == 3
