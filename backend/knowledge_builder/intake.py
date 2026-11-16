"""Requirement intake joined to the scoped question bank and learner state."""
import json
import logging
import math
import re
from pathlib import Path

from django.core import signing
from django.db import transaction
from django.db.models import Case, F, When
from rest_framework.exceptions import ValidationError

from ai_engine import config
from core.utils import apply_institution_filter
from quizzes.models import KnowledgeEdge, KnowledgePoint, Question, UserKnowledgeState
from . import prompts
from .archetypes import PROFILES

logger = logging.getLogger(__name__)
SIGNING_SALT = 'knowledge-builder-diagnostic'


def _normalized(text):
    return re.sub(r'\s+', '', text or '').casefold()


def _score(value):
    return min(1.0, max(0.0, value)) if math.isfinite(value) else 0.0


def inspect_subject_context(subject: str, user=None) -> dict:
    points = apply_institution_filter(KnowledgePoint.objects.all(), user)
    subjects = sorted(filter(None, points.order_by().values_list('subject', flat=True).distinct()))
    needle = _normalized(subject)
    matched = next((s for s in subjects if _normalized(s) == needle), None)
    if not matched:
        matched = next((s for s in subjects if needle in _normalized(s) or _normalized(s) in needle), None)
    if not matched:
        digits = re.findall(r'\d{3}', needle)
        matched = next((s for s in subjects if any(d in s for d in digits)), None)
    info = dict(matched_subject=matched, existing_modules=[], existing_edges=[], module_count=0, kp_count=0, edge_count=0,
                assessed_kp_count=0, avg_mastery=0.0, mastered_topics=[], weak_topics=[])
    if matched:
        points = points.filter(subject=matched)
        modules = list(points.filter(level__in=('sub', 'ch', 'sec')).values('code', 'name', 'level', 'order', 'id'))
        info['module_count'] = len(modules)
        modules.sort(key=lambda m: (('sub', 'ch', 'sec').index(m['level']), m['order'], m['id']))
        info['existing_modules'] = [{k: m[k] or '' for k in ('code', 'name', 'level')} for m in modules[:12]]
        info['kp_count'] = points.filter(level='kp').count()
        edges = apply_institution_filter(
            KnowledgeEdge.objects.filter(source__in=points, target__in=points), user,
        )
        info['edge_count'] = edges.count()
        seed_edges = (edges.filter(is_active=True).exclude(edge_type='contains')
                      .exclude(target__parent_id=F('source_id')).exclude(source__parent_id=F('target_id'))
                      .select_related('source', 'target')
                      .order_by(Case(When(edge_type='prerequisite', then=0), default=1), '-weight', 'id')[:20])
        info['existing_edges'] = [dict(source=e.source.name, target=e.target.name, edge_type=e.edge_type) for e in seed_edges]
        if user is not None and user.is_authenticated:
            states = list(UserKnowledgeState.objects.filter(
                user=user, knowledge_point__in=points,
            ).select_related('knowledge_point').order_by('knowledge_point_id'))
            scores = [_score(s.mastery_score) for s in states]
            info.update(assessed_kp_count=len(states), avg_mastery=round(sum(scores) / len(scores), 2) if scores else 0.0,
                        mastered_topics=[s.knowledge_point.name for s in states if _score(s.mastery_score) >= .7][:8],
                        weak_topics=[s.knowledge_point.name for s in states if _score(s.mastery_score) <= .45][:8])
    info['needs_diagnostic'] = info['assessed_kp_count'] < 3
    return info


def _options(raw):
    if isinstance(raw, dict):
        rows = [{'key': str(k), 'label': v} for k, v in raw.items()]
    elif isinstance(raw, list):
        rows = [dict(key=str(v.get('key', v.get('value', chr(65 + i)))), label=v.get('label', v.get('text', v.get('content', ''))))
                if isinstance(v, dict) else dict(key=chr(65 + i), label=v) for i, v in enumerate(raw)]
    else:
        return []
    return [dict(key=r['key'].strip().upper(), label=str(r['label']).strip()) for r in rows if r['label']]


def _answer(value):
    text = str(value or '').strip().upper()
    return {'TRUE': '对', '正确': '对', '是': '对', '√': '对', 'FALSE': '错', '错误': '错', '否': '错', '×': '错'}.get(text, text)


def _normalize_question(data):
    options = _options(data.get('options', data.get('choices')))
    answer = _answer(data.get('correct_answer', ''))
    if not options and answer in ('对', '错'):
        options = [dict(key='对', label='对'), dict(key='错', label='错')]
    for option in options:
        if _answer(option['label']) == answer:
            answer = option['key']
            break
    stem = data.get('stem') or data.get('question') or data.get('title')
    if not isinstance(stem, str) or not stem.strip() or not 2 <= len(options) <= 4:
        return None
    if len({o['key'] for o in options}) != len(options) or answer not in {o['key'] for o in options}:
        return None
    return {**data, 'stem': stem.strip(), 'options': options, 'correct_answer': answer,
            'explanation': str(data.get('explanation') or '')}


def _bank_question(q):
    # Current Question uses text/options; historical imports may embed a content object.
    content = getattr(q, 'content', None)
    if not isinstance(content, dict):
        try:
            content = json.loads(q.text)
        except (ValueError, TypeError):
            content = {}
    if not isinstance(content, dict):
        content = {}
    return _normalize_question({**content, 'id': f'q_{q.pk}', 'question_id': q.pk,
        'kp_id': q.knowledge_point_id, 'topic': q.knowledge_point.name,
        'stem': content.get('stem') or content.get('question') or content.get('title') or q.text,
        'options': content.get('options') or content.get('choices') or q.options,
        'correct_answer': q.correct_answer or content.get('correct_answer'),
        'explanation': content.get('explanation') or q.ai_answer or '', 'source': 'question_bank'})


def _chapter(kp, parents):
    while kp.parent_id in parents:
        parent = parents[kp.parent_id]
        if parent.level in ('ch', 'sub'):
            return parent.pk
        kp = parent
    return kp.pk


def build_diagnostic_questions(subject, matched_subject, existing_modules, self_report, ai_payload=None, user=None):
    selected, remaining, chapters = [], [], set()
    if matched_subject:
        points = apply_institution_filter(KnowledgePoint.objects.filter(subject=matched_subject), user)
        parents = {p.pk: p for p in points}
        bank = apply_institution_filter(
            Question.objects.filter(q_type='objective', knowledge_point__in=points), user,
        ).select_related('knowledge_point').order_by('id')
        for q in bank.iterator():
            item = _bank_question(q)
            if item is None:
                continue
            chapter = _chapter(q.knowledge_point, parents)
            if chapter not in chapters:
                selected.append(item)
                chapters.add(chapter)
            elif len(remaining) < 4:
                remaining.append(item)
            if len(selected) == 4:
                break
        selected.extend(remaining[:4 - len(selected)])
    if len(selected) < 3:
        candidates = (ai_payload or {}).get('diagnostic_questions', [])
        for raw in candidates:
            item = _normalize_question(raw)
            if item:
                # Only bank questions may write to a real knowledge point.
                selected.append({**item, 'id': f'probe_{len(selected) + 1}', 'question_id': None, 'kp_id': None, 'source': 'ai_probe'})
            if len(selected) == 4:
                break
    if len(selected) < 3:
        probes = json.loads((Path(prompts.PROMPT_DIR) / 'diagnostic_probes.json').read_text(encoding='utf-8'))
        family = 'finance' if any(t in subject + (matched_subject or '') for t in ('431', '金融', '理财')) else 'computing' if any(t in subject + (matched_subject or '') for t in ('408', '计算机')) else 'general'
        for raw in probes[family]:
            item = _normalize_question({**raw, 'stem': raw['stem'].replace('{subject}', subject)})
            selected.append({**item, 'id': f'probe_{len(selected) + 1}', 'question_id': None, 'kp_id': None, 'source': 'ai_probe'})
            if len(selected) >= 3:
                break
    for item in selected:
        item['signed_payload'] = signing.dumps({'subject': subject, 'question': item.copy()}, salt=SIGNING_SALT, compress=True)
    return selected


def _verified_questions(subject, questions):
    verified = []
    for item in questions:
        token = item.get('signed_payload', '')
        if not isinstance(token, str):
            raise ValidationError({'diagnostic_questions': '摸底题目凭据无效。'})
        try:
            issued = signing.loads(token, salt=SIGNING_SALT)
        except signing.BadSignature:
            raise ValidationError({'diagnostic_questions': '摸底题目无效，请重新生成。'})
        if issued['subject'] != subject:
            raise ValidationError({'diagnostic_questions': '题目与当前学科不一致，请重新生成。'})
        verified.append({**issued['question'], 'signed_payload': item['signed_payload']})
    if len({q['id'] for q in verified}) != len(verified):
        raise ValidationError({'diagnostic_questions': '摸底题目不能重复。'})
    return verified


def _entry_strategy(gaps, known):
    start = '、'.join(gaps[:3]) or ('、'.join(known[:2]) if known else '基础概念与核心机制')
    return f'保留完整客观前置依赖图，不删前置节点；建议将“{start}”对应学习块标记为推荐起点（entry_blocks / ENTRY）。薄弱内容逐步讲解与推导，已掌握内容保留并简要回顾，进阶应用列为拓展。'


def evaluate_diagnostic_answers(user, questions, answers: dict, self_report: str = '') -> dict:
    points = apply_institution_filter(KnowledgePoint.objects.all(), user)
    results, known, gaps = [], [], []
    with transaction.atomic():
        for question in questions:
            q = question
            if q.get('source') == 'question_bank':
                bank = apply_institution_filter(
                    Question.objects.filter(knowledge_point__in=points, pk=q.get('question_id'), q_type='objective'), user,
                ).select_related('knowledge_point').first()
                if bank is None:
                    raise ValidationError({'diagnostic_questions': '题目已不可用，请重新生成。'})
                q = _bank_question(bank)
                if q is None:
                    raise ValidationError({'diagnostic_questions': '题目已更新，请重新生成。'})
            selected = answers.get(str(q['id']), answers.get(str(q.get('question_id')), ''))
            if not selected:
                continue
            selected = _answer(selected)
            if selected not in {o['key'] for o in q['options']}:
                raise ValidationError({'diagnostic_answers': '请选择题目提供的选项。'})
            correct = selected == _answer(q['correct_answer'])
            (known if correct else gaps).append(q['topic'])
            results.append(dict(id=q['id'], selected_answer=selected, correct=correct,
                                correct_answer=q['correct_answer'], explanation=q['explanation']))
            if q.get('kp_id') and q.get('source') == 'question_bank' and user is not None and user.is_authenticated:
                state, created = UserKnowledgeState.objects.select_for_update().get_or_create(user=user, knowledge_point_id=q['kp_id'])
                old = .5 if created else _score(state.mastery_score)
                state.mastery_score = max(old, .75) if correct else min(old, .35)
                state.save(update_fields=('mastery_score', 'updated_at'))
    count = len(results)
    correct_count = sum(r['correct'] for r in results)
    return dict(answered_count=count, correct_count=correct_count, accuracy=round(correct_count / count, 2) if count else 0.0,
        known_topics=list(dict.fromkeys(known)), gap_topics=list(dict.fromkeys(gaps)), self_report=self_report,
        entry_strategy=_entry_strategy(gaps, known), results=results)


def _card(dimension, title, question, choices, multi=False):
    return dict(id=dimension, dimension=dimension, title=title, question=question, multi_select=multi,
                options=[dict(value=v, label=v, description=d) for v, d in choices], allow_custom=True)


def _default_cards(subject, catalog):
    modules = [(m['name'], f"已有章节 · {m['code']}") for m in catalog['existing_modules']]
    return [
        _card('goal', '学习目的', '你希望用这张知识树完成什么？', [(f'{subject}应试复习', '按考点与典型题组织'), ('课程期末', '围绕教材与课程考核'), ('实操应用', '围绕工作任务与实际问题'), ('系统理解', '梳理概念与机制')]),
        _card('scope', '学习范围', '优先展开哪些模块？可在补充中写“排除：…”说明暂不展开的范围。', modules or [(f'{subject}基础概念', '先建立概念骨架'), (f'{subject}核心机制', '理解关系与适用条件'), (f'{subject}综合应用', '连接典型问题')], True),
        _card('depth', '推导深度', '讲解与原子点需要细到什么程度？', [('概念与框架', '解释概念及相互关系'), ('逐步推导与计算', '展开关键推导与例题'), ('综合迁移与应用', '比较情境并解决综合问题')]),
        _card('prior_knowledge', '现有基础', '你目前的学习基础如何？', [('从零开始', '从基本概念开始讲解'), ('学过但不熟', '回顾基础并定位薄弱点'), ('基础较扎实', '保留基础并侧重进阶应用')]),
    ]


def _texts(value):
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [s.strip() for s in value if isinstance(s, str) and s.strip()]
    if isinstance(value, dict):
        return _texts(value.get('selected')) + _texts(value.get('custom'))
    return []


def _chat_dimensions(messages, modules):
    values = {}
    users = [m['content'] for m in messages if m['role'] == 'user']
    patterns = dict(goal=r'目的|目标|应试|考试|考研|期末|实操|复习|学会', depth=r'推导|深度|颗粒|计算|框架|迁移|综合应用',
                    prior_knowledge=r'基础|学过|不熟|掌握|零开始|不会|已经懂', scope=r'范围|章节|重点|教材|考纲|排除|暂不|只学|完整学科|全科')
    for text in users:
        current = {}
        for sentence in re.split(r'[。；，,;\n]', text):
            found = [m['name'] for m in modules if m['name'] in sentence]
            matched_keys = [key for key, pattern in patterns.items() if re.search(pattern, sentence)]
            for key in matched_keys:
                content = found if key == 'scope' and not re.search(r'排除|暂不', sentence) and found else [sentence.strip()]
                current[key] = current.get(key, []) + content
            if found and not matched_keys:
                current['scope'] = current.get('scope', []) + found
        values.update(current)
    if users and 'goal' not in values:
        values['goal'] = [users[0]]
    return values


def inquire_requirements(user, payload: dict) -> dict:
    subject, mode = payload['subject'].strip(), payload.get('mode', 'card')
    catalog = inspect_subject_context(subject, user)
    messages, answers = payload.get('messages', []), payload.get('card_answers', {})
    self_report = payload.get('self_report', '').strip()
    ai = {}
    if config._get_api_key():
        try:
            ai = prompts.ask('requirement_intake', dict(subject=subject, mode=mode, messages=messages, card_answers=answers,
                self_report=self_report, catalog_match=catalog))
        except Exception:
            # Intake alone explicitly supports an offline workflow; builds stay fail-fast.
            logger.warning('Requirement intake AI unavailable; using deterministic intake.')
    cards = ai.get('cards') or _default_cards(subject, catalog)
    # The scope choices are always the real catalog when one was matched.
    if catalog['existing_modules']:
        cards = [c for c in cards if c['dimension'] != 'scope']
        cards.insert(1, _default_cards(subject, catalog)[1])
    questions = _verified_questions(subject, payload['diagnostic_questions']) if payload.get('diagnostic_questions') else build_diagnostic_questions(
        subject, catalog['matched_subject'], catalog['existing_modules'], self_report, ai, user=user)
    if payload.get('diagnostic_answers') and not payload.get('diagnostic_questions'):
        raise ValidationError({'diagnostic_questions': '请提交本次摸底题目。'})
    baseline = evaluate_diagnostic_answers(user, questions, payload.get('diagnostic_answers', {}), self_report)
    if baseline['answered_count']:
        catalog = inspect_subject_context(subject, user)
    baseline.update({k: catalog[k] for k in ('assessed_kp_count', 'avg_mastery', 'mastered_topics', 'weak_topics')})
    if not baseline['answered_count']:
        baseline['known_topics'], baseline['gap_topics'] = catalog['mastered_topics'], catalog['weak_topics']
        baseline['entry_strategy'] = _entry_strategy(baseline['gap_topics'], baseline['known_topics'])
    extracted = _chat_dimensions(messages, catalog['existing_modules'])
    dimensions = {d: (extracted.get(d, []) or _texts(answers.get(d))) if mode == 'chat'
                  else (_texts(answers.get(d)) or extracted.get(d, []))
                  for d in ('goal', 'scope', 'depth', 'prior_knowledge')}
    raw = ai.get('requirements_draft', {})
    scope = dimensions['scope'] or _texts(raw.get('scope_inclusions'))
    exclusions = _texts(raw.get('scope_exclusions'))
    inclusions = []
    for item in scope:
        match = re.search(r'(?:排除|暂不(?:展开|学习)?)[：: ]*(.+)', item)
        if match:
            exclusions.append(match[1])
            item = item[:match.start()].strip('，,；; ')
        if item:
            inclusions.append(item)
    background = self_report or '；'.join(dimensions['prior_knowledge']) or raw.get('learner_background', '')
    draft = dict(learning_goal='；'.join(dimensions['goal']) or raw.get('learning_goal', ''),
        recommended_archetype=raw.get('recommended_archetype', 'auto'), scope_inclusions=inclusions,
        scope_exclusions=exclusions, depth_preference='；'.join(dimensions['depth']) or raw.get('depth_preference', ''),
        learner_background=background, baseline_summary=baseline,
        suggested_entry_topics=baseline['gap_topics'][:3] or _texts(raw.get('suggested_entry_topics')) or [m['name'] for m in catalog['existing_modules'][:2]],
        seed_modules=catalog['existing_modules'], seed_edges=catalog['existing_edges'])
    if draft['recommended_archetype'] not in ('auto', *PROFILES):
        draft['recommended_archetype'] = 'auto'
    missing = []
    for present, question in ((draft['learning_goal'], '你准备应对什么考试、课程或实际任务？'),
                              (draft['scope_inclusions'], '希望重点展开哪些章节？也可以回答“完整学科”。'),
                              (draft['depth_preference'], '你更需要概念框架、逐步推导计算，还是综合应用？'),
                              (background or baseline['assessed_kp_count'] >= 3 or baseline['answered_count'], '你学过哪些内容，哪些还不熟？可以自述或完成基础快测。')):
        if not present:
            missing.append(question)
    ready = not missing
    reply = (f'需求已整理：围绕“{draft["learning_goal"]}”，重点展开{ "、".join(inclusions)}，采用{draft["depth_preference"]}。{baseline["entry_strategy"]} 请确认后启动构建。'
             if ready else (ai.get('assistant_reply') or f'我们先明确需求。{missing[0]}'))
    return dict(subject=subject, mode=mode, catalog_match=catalog, needs_diagnostic=catalog['needs_diagnostic'], cards=cards,
                diagnostic_questions=questions, assistant_reply=reply, requirements_draft=draft, ready_to_build=ready)
