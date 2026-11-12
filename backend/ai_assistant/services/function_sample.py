"""Original four-node function sample; setup never seeds shared content implicitly."""
import hashlib
import json
from pathlib import Path

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from ai_assistant.models import (ConversationProject, ProjectLearning, LearningResource,
    LearningResourceVersion, LearningKnowledgeMap, LearningKnowledgeVersion, AIChatMessage)
from core.utils import get_content_institution_id
from quizzes.models import KnowledgePoint, Question
from .learning_knowledge import knowledge_operation, validate_nodes
from .learning_resources import store_resource
from .project_learning import change_learning, learning_data


CONTENT_PATH = Path(__file__).resolve().parent.parent / 'data' / 'function_foundations.json'
SOURCE_URL = '/learning-samples/function-foundations/v1'
PHASE_TITLES = {'pretest': '起点检查', 'practice': '学习练习', 'recheck': '换题再检验'}


def sample_content():
    return json.loads(CONTENT_PATH.read_text())


def question_values(item):
    return {'text': item['text'], 'q_type': 'objective', 'options': item['options'],
            'correct_answer': item['correct_answer'], 'ai_answer': item['explanation'],
            'difficulty_level': item['difficulty_level']}


def question_hash(values):
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _matches_question(row, item):
    return question_hash({key: getattr(row, key) for key in question_values(item)}) == question_hash(question_values(item))


@transaction.atomic
def seed_content():
    """Explicit administrator action, constrained to the configured content partition."""
    content = sample_content()
    scope = get_content_institution_id()
    created_points = created_questions = 0
    for order, node in enumerate(content['nodes']):
        point, created = KnowledgePoint.objects.get_or_create(code=node['code'], institution_id=scope,
            defaults={'name': node['title'], 'subject': '高中数学', 'level': 'kp', 'order': order,
                      'description': node['explanation'] + '\n\n' + node['example']})
        if not created and (point.name != node['title'] or point.subject != '高中数学'):
            raise ValidationError('样板知识编码已被其他内容使用，请人工核对，不覆盖原内容。')
        created_points += int(created)
        for item in node['questions']:
            row, created = Question.objects.get_or_create(knowledge_point=point, institution_id=scope, text=item['text'],
                defaults={key: value for key, value in question_values(item).items() if key != 'text'})
            if not _matches_question(row, item):
                raise ValidationError('已有同名样板题的内容已变化，请人工核对，不覆盖原题。')
            created_questions += int(created)
    return {'sample_id': content['id'], 'version': content['version'],
            'created_knowledge_points': created_points, 'created_questions': created_questions}


def _seeded_questions(content):
    scope = get_content_institution_id()
    result = {}
    for node in content['nodes']:
        point = KnowledgePoint.objects.filter(code=node['code'], institution_id=scope, subject='高中数学').first()
        for item in node['questions']:
            row = Question.objects.filter(knowledge_point=point, institution_id=scope, text=item['text']).first() if point else None
            if not row or not _matches_question(row, item):
                raise ValidationError('函数样板题库尚未准备好，请管理员先运行 seed_function_foundations 并核对内容。')
            result[item['code']] = row.pk
    return result


def _original_resource(user, content):
    excerpt = '\n\n'.join([content['notice'], content['scope'], *[
        f"## {node['title']}\n{node['explanation']}\n\n{node['example']}" for node in content['nodes']]])
    row, _ = LearningResource.objects.get_or_create(user=user, url_hash=hashlib.sha256(SOURCE_URL.encode()).hexdigest(),
        defaults={'url': SOURCE_URL, 'title': content['title'] + '·原创讲解', 'excerpt': excerpt,
                  'read_at': timezone.now(), 'domain': '高中数学', 'topic': '函数基础', 'level': '入门', 'edition': content['version']})
    if row.is_archived:
        raise ValidationError('这份原创样板资料已归档，请先在本人资料库恢复。')
    snapshot = {key: getattr(row, key) for key in ('id', 'url', 'title', 'excerpt', 'domain', 'topic', 'level', 'edition')}
    snapshot.update(read_at=row.read_at.isoformat(), revision=1, source_kind='unimind_original',
                    content_version=content['version'], references=content['references'], notice=content['notice'], not_web_read=True)
    version, _ = LearningResourceVersion.objects.get_or_create(resource=row, revision=1, defaults={'snapshot': snapshot})
    if version.snapshot.get('source_kind') != 'unimind_original' or version.snapshot['excerpt'] != excerpt:
        raise ValidationError('原创样板来源版本与当前内容不一致，请管理员核对，不覆盖旧快照。')
    return row, version


def _instructions(node, phase):
    if phase == 'pretest':
        return '先独立完成这一题起点检查，了解目前的理解，不作正式考试成绩。若作答时查看了提示，请如实选择帮助程度。'
    if phase == 'practice':
        return f"先阅读讲解和示例，再做另一道练习。\n\n{node['explanation']}\n\n{node['example']}\n\n示例不是本次练习原题；作答时是否查看提示，需要另行记录。"
    return '先回顾本节点讲解和上一题的反馈，再完成这道不同的题。请按实际作答记录提示程度；一次答对只提供一次任务证据，不自动证明迁移或完整掌握。'


@transaction.atomic
def setup_sample(project):
    """Initialize only a fresh owned project after its explicit sample action."""
    from .learning_tasks import create_task, task_data
    project = ConversationProject.objects.select_for_update().get(pk=project.pk, user_id=project.user_id)
    state, _ = ProjectLearning.objects.get_or_create(project=project)
    state = ProjectLearning.objects.select_for_update().get(pk=state.pk)
    if not state.planning_enabled:
        raise ValidationError('函数样板需要规划模式项目。')
    has_learning_messages = AIChatMessage.objects.filter(user=project.user, role='user',
        conversation_id__in=project.conversations.values('conversation_id')).exists()
    if project.instructions.strip() or has_learning_messages or state.status != 'preparing' or state.plan or state.resources or state.pending_plan or (state.revision and project.learning_events.exclude(kind='reminders').exists()):
        raise ValidationError('函数样板只能在全新的待准备项目中开始，不能覆盖现有学习安排。')
    content = sample_content()
    question_ids = _seeded_questions(content)
    resource, resource_version = _original_resource(project.user, content)
    nodes = [{key: node[key] for key in ('id', 'title', 'outcome', 'prerequisites')} | {
        'citation': {'resource_id': resource.pk, 'revision': 1, 'quote': node['quote']}} for node in content['nodes']]
    validate_nodes(project.user, nodes)
    for node in nodes:
        node['citation']['source_kind'] = 'unimind_original'
    knowledge_map = LearningKnowledgeMap.objects.create(user=project.user, title=content['title'])
    version = LearningKnowledgeVersion.objects.create(knowledge_map=knowledge_map, revision=1,
        snapshot={'title': content['title'], 'nodes': nodes, 'sample_id': content['id'], 'content_version': content['version']})
    prepared = knowledge_operation(project, {'action': 'prepare', 'version_id': version.pk,
        'targets': [node['id'] for node in nodes], 'depth': 'apply'})
    state.refresh_from_db(fields=['resources'])
    pinned = next(source for source in state.resources if source['id'] in prepared['sources'].values())
    store_resource(project, {**pinned, **{key: resource_version.snapshot[key] for key in
        ('source_kind', 'content_version', 'references', 'notice', 'not_web_read')}})
    source_id = pinned['id']
    stages = [{'id': node['id'], 'title': node['title'], 'outcome': node['outcome'],
               'task': '起点检查 → 原创讲解与示例 → 学习练习 → 反馈与复习 → 换题再检验',
               'prerequisites': node['prerequisites'], 'sources': [source_id], 'knowledge_nodes': [node['id']]} for node in nodes]
    change_learning(project, {'action': 'plan', 'revision': state.revision,
        'plan': {'goal': '用四个基础节点开始理解函数，并通过真实作答检查起点与后续表现。',
                 'weekly_minutes': 0, 'deadline': None, 'knowledge_path': prepared['knowledge_path'], 'stages': stages},
        'next_action': '先完成“函数概念”的一题起点检查，再阅读讲解与示例。', 'reason': '用户主动选择开始函数基础原创样板。'})
    tasks = []
    for node in content['nodes']:
        previous = None
        for item in node['questions']:
            task = create_task(project, {'version_id': version.pk, 'node_id': node['id'], 'stage_id': node['id'],
                'title': f"{node['title']}｜{PHASE_TITLES[item['phase']]}", 'instructions': _instructions(node, item['phase']),
                'question_ids': [question_ids[item['code']]], 'mode': 'apply',
                'purpose': {'pretest': 'diagnostic', 'practice': 'practice', 'recheck': 'recheck'}[item['phase']],
                'source_task_id': str(previous.pk) if previous else None})
            tasks.append(task)
            previous = task
    return {'project': learning_data(project), 'tasks': [task_data(task) for task in tasks],
            'sample': {key: content[key] for key in ('id', 'version', 'title', 'scope', 'source_kind')}}
