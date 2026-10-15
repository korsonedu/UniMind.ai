from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers

from quizzes.models import KnowledgePoint, KnowledgeEdge, Question
from quizzes.serializers import QuestionSerializer
from quizzes.services.question_normalizer import normalize_objective_answer, normalize_options
from .common import content_institution, identity, managed, paginate


LEVELS = ['sub', 'ch', 'sec', 'kp']


def catalog_rows(lock=False):
    queryset = managed(KnowledgePoint.objects.all()).order_by('order', 'id')
    return list(queryset.select_for_update() if lock else queryset)


def descendants(nodes, root):
    children = {}
    for node in nodes:
        children.setdefault(node.parent_id, []).append(node.pk)
    found, queue = set(), [root]
    while queue:
        key = queue.pop()
        if key not in found:
            found.add(key)
            queue.extend(children.get(key, []))
    return found


def invalidate_catalog(institution_id, subjects):
    keys = {f'knowledge_tree:ids:inst:{institution_id}'} if institution_id else {
        'knowledge_tree:ids:global',
        *(f'knowledge_tree:ids:global:subject:{subject}' for subject in subjects if subject),
    }
    transaction.on_commit(lambda: cache.delete_many(keys))


def catalog_item(node):
    return {field: getattr(node, field) for field in (
        'id', 'code', 'name', 'level', 'subject', 'description', 'order',
    )} | {'parent': node.parent_id, 'question_count': getattr(node, 'question_count', 0)}


def list_catalog(request, data):
    nodes = managed(KnowledgePoint.objects.annotate(question_count=Count('questions'))).order_by('order', 'id')
    return {'items': [catalog_item(node) for node in nodes]}


class KnowledgeInput(serializers.ModelSerializer):
    class Meta:
        model = KnowledgePoint
        fields = ('code', 'name', 'level', 'parent', 'subject', 'description', 'order')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['parent'].queryset = managed(KnowledgePoint.objects.all())


def save_catalog(request, data):
    scope = content_institution(required=True)
    nodes = catalog_rows(lock=True)
    by_id = {node.pk: node for node in nodes}
    instance = get_object_or_404(managed(KnowledgePoint.objects.all()), pk=identity(data)) if data.get('id') else None
    serializer = KnowledgeInput(instance, data=data, partial=bool(instance))
    serializer.is_valid(raise_exception=True)
    attrs = serializer.validated_data
    parent = attrs.get('parent', instance.parent if instance else None)
    level = attrs.get('level', instance.level if instance else 'kp')
    subtree = descendants(nodes, instance.pk) if instance else set()
    if parent and (parent.pk in subtree or parent.institution_id != (scope.pk if scope else None)):
        raise serializers.ValidationError({'parent': '上级目录不能是自身、下级节点或其他内容范围的节点。'})
    if parent and LEVELS.index(parent.level) >= LEVELS.index(level):
        raise serializers.ValidationError({'parent': '上级目录的层级须高于当前节点。'})
    if instance and any(node.parent_id == instance.pk and LEVELS.index(node.level) <= LEVELS.index(level) for node in nodes):
        raise serializers.ValidationError({'level': '当前层级与已有下级节点冲突，请先调整下级节点。'})
    if instance and instance.level == 'kp' and level != 'kp' and (
        instance.questions.exists() or KnowledgeEdge.objects.filter(Q(source=instance) | Q(target=instance)).exists()
    ):
        raise serializers.ValidationError({'level': '考点已被题目或知识关联引用，不能修改层级。'})
    subject = (parent.subject or '') if parent else (attrs.get('subject', instance.subject if instance else '') or '').strip()
    if not subject:
        raise serializers.ValidationError({'subject': '请先填写顶层目录的所属学科。'})
    old_subjects = {by_id[key].subject for key in subtree}
    node = serializer.save(institution=scope, subject=subject)
    if subtree:
        KnowledgePoint.objects.filter(pk__in=subtree - {node.pk}).update(subject=subject)
    invalidate_catalog(node.institution_id, old_subjects | {subject})
    return catalog_item(node)


def referenced(instance, ignore=()):
    # Include historical learning records as well as content links before cascading deletion.
    for relation in instance._meta.related_objects:
        if relation.related_model in ignore:
            continue
        if relation.related_model._default_manager.filter(**{relation.field.name: instance}).exists():
            return True
    return False


def delete_catalog(request, data):
    catalog_rows(lock=True)
    node = get_object_or_404(managed(KnowledgePoint.objects.all()), pk=identity(data))
    if node.children.exists():
        raise serializers.ValidationError('目录仍有下级节点，请先迁移或处理下级节点。')
    if referenced(node, ignore=(KnowledgePoint, KnowledgeEdge)):
        raise serializers.ValidationError('知识点已被内容或学习记录引用，不能直接删除。')
    if KnowledgeEdge.objects.filter(Q(source=node) | Q(target=node)).exclude(source_type='tree').exists():
        raise serializers.ValidationError('知识点仍有非目录派生的知识关联，不能直接删除。')
    key = node.pk
    node.delete()
    invalidate_catalog(node.institution_id, {node.subject})
    return {'id': key, 'deleted': True}


class QuestionInput(QuestionSerializer):
    class Meta(QuestionSerializer.Meta):
        fields = ('id', 'knowledge_point', 'text', 'q_type', 'subjective_type', 'difficulty_level',
                  'grading_points', 'options', 'correct_answer', 'ai_answer', 'rubric', 'difficulty')
        read_only_fields = ('difficulty',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['knowledge_point'].queryset = managed(KnowledgePoint.objects.filter(level='kp'))

    def validate(self, attrs):
        def value(field, default=None):
            return attrs.get(field, getattr(self.instance, field, default))
        point = value('knowledge_point')
        scope = content_institution(required=True)
        if not point or point.institution_id != (scope.pk if scope else None):
            raise serializers.ValidationError({'knowledge_point': '请选择受管范围内的考点。'})
        q_type = value('q_type', 'objective')
        answer = (value('correct_answer') or '').strip()
        if not answer:
            raise serializers.ValidationError({'correct_answer': '请填写标准答案或参考答案。'})
        if q_type == 'objective':
            options = value('options')
            if isinstance(options, dict):
                options = [options[key] for key in sorted(options)]
            options = serializers.ListField(child=serializers.CharField(allow_blank=False), min_length=2, max_length=4).run_validation(options)
            answer = normalize_objective_answer(answer, normalize_options(options))
            if answer not in 'ABCD'[:len(options)] or len(answer) != 1:
                raise serializers.ValidationError({'correct_answer': '标准答案须为实际选项对应的单个字母。'})
            attrs.update(options=options, correct_answer=answer, subjective_type=None)
        else:
            if not value('subjective_type'):
                raise serializers.ValidationError({'subjective_type': '请选择主观题类型。'})
            if not (value('grading_points') or '').strip() and not value('rubric'):
                raise serializers.ValidationError({'grading_points': '请填写得分点或结构化评分标准。'})
        if 'rubric' in attrs and attrs['rubric'] is not None:
            if not isinstance(attrs['rubric'], list) or any(
                not isinstance(item, (str, dict)) or
                (isinstance(item, dict) and not str(item.get('point') or item.get('criteria') or '').strip())
                for item in attrs['rubric']
            ):
                raise serializers.ValidationError({'rubric': '评分标准须为得分点数组，每项包含 point 或 criteria。'})
        return attrs


def question_item(item):
    return {'id': item.pk, 'text': item.text, 'q_type': item.q_type, 'subjective_type': item.subjective_type,
            'difficulty_level': item.difficulty_level, 'knowledge_point': item.knowledge_point_id,
            'knowledge_name': item.knowledge_point.name if item.knowledge_point else '',
            'subject': item.knowledge_point.subject if item.knowledge_point else '',
            'has_answer': bool(item.correct_answer)}


def list_questions(request, data):
    queryset = managed(Question.objects.select_related('knowledge_point')).order_by('-id')
    if data.get('search'):
        queryset = queryset.filter(text__icontains=str(data['search'])[:200])
    if data.get('knowledge_point') == 'unassigned':
        queryset = queryset.filter(knowledge_point__isnull=True)
    elif data.get('knowledge_point'):
        root = get_object_or_404(managed(KnowledgePoint.objects.all()), pk=identity(data, 'knowledge_point'))
        queryset = queryset.filter(knowledge_point_id__in=descendants(catalog_rows(), root.pk))
    for field, choices in (('q_type', Question.QUESTION_TYPES), ('difficulty_level', Question.DIFFICULTY_LEVELS)):
        if data.get(field):
            queryset = queryset.filter(**{field: serializers.ChoiceField(choices=choices).run_validation(data[field])})
    return paginate(queryset, data, question_item)


def question_detail(request, data):
    item = get_object_or_404(managed(Question.objects.all()), pk=identity(data))
    return QuestionInput(item).data


def save_question(request, data):
    scope = content_institution(required=True)
    instance = get_object_or_404(managed(Question.objects.select_for_update()), pk=identity(data)) if data.get('id') else None
    serializer = QuestionInput(instance, data=data, partial=bool(instance))
    serializer.is_valid(raise_exception=True)
    attrs = serializer.validated_data
    if instance and any(
        field in attrs and (attrs[field] or '') != (getattr(instance, field) or '') for field in ('q_type', 'subjective_type')
    ) and referenced(instance):
        raise serializers.ValidationError('题目已有业务或学习记录，不能直接改变题型。')
    level = attrs.get('difficulty_level', instance.difficulty_level if instance else 'normal')
    kwargs = {'institution': scope}
    if not instance or level != instance.difficulty_level:
        kwargs['difficulty'] = Question.DIFFICULTY_MAP[level]
    return QuestionInput(serializer.save(**kwargs)).data


def delete_question(request, data):
    item = get_object_or_404(managed(Question.objects.select_for_update()), pk=identity(data))
    if referenced(item):
        raise serializers.ValidationError('题目已有业务或学习记录，不能直接删除。')
    key = item.pk
    item.delete()
    return {'id': key, 'deleted': True}


def assign_questions(request, data):
    point = get_object_or_404(managed(KnowledgePoint.objects.select_for_update()), pk=identity(data, 'knowledge_point'), level='kp')
    ids = set(serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False, max_length=500).run_validation(data.get('questions')))
    queryset = managed(Question.objects.select_for_update()).filter(pk__in=ids)
    selected = list(queryset)
    if len(selected) != len(ids) or any(item.institution_id != point.institution_id for item in selected):
        raise serializers.ValidationError('全部题目与目标考点须属于同一内容范围。')
    queryset.update(knowledge_point=point)
    return {'id': point.pk, 'updated': len(ids)}
