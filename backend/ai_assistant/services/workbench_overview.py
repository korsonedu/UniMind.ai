"""Build a fast project overview and a richer synthesis on demand."""
import hashlib
import json

from django.db.models import F, Window
from django.db.models.functions import RowNumber

from ai_assistant.models import ProjectSourceChunk
from ai_engine.service import AIEngine
from .project_learning_tools import obj, text
from .workbench_grounding import workbench_prompt

OVERVIEW_SCHEMA = obj({
    'overview': {**text(), 'minLength': 1, 'maxLength': 2400},
    'suggested_questions': {
        'type': 'array', 'minItems': 3, 'maxItems': 4,
        'items': {**text(), 'minLength': 1, 'maxLength': 300},
    },
}, ('overview', 'suggested_questions'))


def source_signature(sources):
    keys = [(str(source.pk), source.updated_at.isoformat()) for source in sources]
    return hashlib.sha256(json.dumps(keys).encode()).hexdigest()


def _sample_chunks(sources, limit):
    return ProjectSourceChunk.objects.filter(source_id__in=[source.pk for source in sources]).annotate(
        position=Window(RowNumber(), partition_by=F('source_id'), order_by=F('chunk_index').asc()),
    ).filter(position__lte=limit).values('source_id', 'content', 'heading', 'locator_label').order_by('chunk_index')


def extractive_overview(sources):
    if not sources:
        return {'overview': '', 'suggested_questions': []}
    lead = {row['source_id']: row['content'] for row in _sample_chunks(
        [source for source in sources if not source.summary], limit=1,
    )}
    paragraphs = []
    for source in sources:
        summary = source.summary or lead.get(source.pk, '')
        excerpt = ' '.join(summary.split())[:300]
        paragraphs.append(f'《{source.title}》：{excerpt}' if excerpt else f'《{source.title}》')
    first = sources[0].title[:80]
    if len(sources) == 1:
        questions = [
            f'《{first}》主要讲了哪些概念，它们之间有什么关系？',
            '资料用了哪些例子解释核心观点？',
            '用一道小题检验我能不能把资料里的方法用到新情境。',
        ]
    else:
        second = sources[1].title[:80]
        questions = [
            f'《{first}》与《{second}》有哪些共同主题，各自补充了什么？',
            '把选中资料的核心概念连起来，可以整理出怎样的学习顺序？',
            '各来源对同一个问题的解释或例子有什么异同？',
            '能否用选中资料中的观点共同分析一个具体例子？',
        ]
    return {'overview': '\n\n'.join(paragraphs), 'suggested_questions': questions}


def synthesize_overview(sources):
    materials = {
        source.pk: {'title': source.title, 'type': source.source_type, 'summary': source.summary[:600],
                    'unit_count': source.unit_count, 'excerpts': []}
        for source in sources
    }
    for row in _sample_chunks(sources, limit=2):
        materials[row['source_id']]['excerpts'].append({
            'locator': row['locator_label'], 'heading': row['heading'], 'text': row['content'][:600],
        })
    result = AIEngine.structured_output(
        messages=[
            {'role': 'system', 'content': workbench_prompt('project_overview.txt')},
            {'role': 'user', 'content': json.dumps(list(materials.values()), ensure_ascii=False)},
        ],
        schema=OVERVIEW_SCHEMA,
        tool_name='submit_workbench_overview',
        operation='assistant.chat.planner.workbench_overview',
        max_tokens=1600,
        temperature=0.3,
    )
    if not isinstance(result, dict):
        return None
    overview = result.get('overview')
    questions = result.get('suggested_questions')
    if (not isinstance(overview, str) or not 0 < len(overview.strip()) <= 2400
            or not isinstance(questions, list) or not 3 <= len(questions) <= 4
            or any(not isinstance(question, str) or not 0 < len(question.strip()) <= 300 for question in questions)):
        return None
    return {'overview': overview.strip(), 'suggested_questions': [question.strip() for question in questions]}
