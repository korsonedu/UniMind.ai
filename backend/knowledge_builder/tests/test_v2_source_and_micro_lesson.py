"""Tests for V2 Source-First TOC parsing, Tree-to-Tree alignment, AtomMicroLesson, and fast resource APIs."""
import zlib
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIClient

from ai_assistant.services.dsh_cards import build_learning_visual
from knowledge_builder import models, source_parsers

pytestmark = pytest.mark.django_db


@pytest.fixture
def client(user):
    api = APIClient()
    api.force_authenticate(user=user)
    return api


@pytest.fixture
def sample_tree(user):
    build = models.KnowledgeTreeBuild.objects.create(
        subject='私募股权投资基金',
        status=models.KnowledgeTreeBuild.Status.COMPLETED,
        created_by=user,
    )
    mod = models.TreeModule.objects.create(
        build=build, code='M1', title='基金组织形式与税负', path='M1', depth=1, order=1,
    )
    atom1 = models.TreeAtomPoint.objects.create(
        build=build, module=mod, code='A1', name='合伙型基金税负规则',
        goal_statement='区分合伙型与公司型基金的所得税穿透原则与双重征税差异。',
        parent_path='M1', goal_type='对比区分', granularity_minutes=4, cognitive_level='分析',
        key_elements=['先分后税', '自然人LP', '法人LP', '双重征税'],
        common_misconceptions=['合伙企业本身缴纳企业所得税'],
        order=1,
    )
    atom2 = models.TreeAtomPoint.objects.create(
        build=build, module=mod, code='A2', name='估值倍数计算与IRR推演',
        goal_statement='熟练运用市盈率法与现金流折现推导基金内部收益率 IRR。',
        parent_path='M1', goal_type='实操计算', granularity_minutes=6, cognitive_level='应用',
        key_elements=['市盈率倍数', 'IRR折现率', 'DPI与TVPI'],
        common_misconceptions=['混淆TVPI与已分配收益DPI'],
        order=2,
    )
    block = models.LearningBlock.objects.create(
        build=build, code='B1', short_title='基金组织与估值基础',
        narrative_summary='掌握合伙型税负穿透与核心估值指标。', layer=1, is_entry_block=True, order=1,
    )
    step = models.BlockStep.objects.create(
        block=block, step_index=1, step_title='核心机制与计算', step_role='foundation',
    )
    models.BlockStepAtom.objects.create(step=step, atom=atom1, membership_type='core', position=1)
    models.BlockStepAtom.objects.create(step=step, atom=atom2, membership_type='core', position=2)
    return build, block, atom1, atom2


def test_clean_resource_excerpt_strips_html_and_markdown():
    raw = '<script>alert(1)</script><div># 标题 **加粗** [外链](https://example.com)   正文内容</div>'
    cleaned = source_parsers.clean_resource_excerpt(raw)
    assert 'alert' not in cleaned
    assert '<div' not in cleaned
    assert 'https://example.com' not in cleaned
    assert '加粗' in cleaned and '正文内容' in cleaned


def test_markdown_and_pdf_parsers():
    md = (
        '# 第1章 组织形式\n'
        '## 1.1 合伙型基金税负规则\n'
        '合伙型基金实行先分后税原则，自然人LP与法人LP分别适用不同税率，避免双重征税。\n'
        '## 1.2 估值倍数与IRR计算\n'
        '常用市盈率倍数、DPI 与 TVPI 以及 IRR 折现率衡量收益。\n'
    )
    toc, sections = source_parsers.parse_markdown_or_text(md, title='协会教材')
    assert len(toc) == 1
    assert len(toc[0]['children']) == 2
    assert len(sections) == 3

    # Minimal valid PDF with a FlateDecode text stream
    stream_body = zlib.compress(b'BT /F1 12 Tf (Chapter 1 Private Equity Tax Rules and IRR Valuation) Tj ET')
    pdf_bytes = b'%PDF-1.4\n1 0 obj << /Length ' + str(len(stream_body)).encode() + b' >>\nstream\n' + stream_body + b'\nendstream\nendobj\n%%EOF'
    pdf_toc, pdf_sections = source_parsers.parse_pdf_bytes(pdf_bytes, filename='handbook.pdf')
    assert len(pdf_toc) == 1
    assert pdf_toc[0]['locator'] == 'P1'
    assert 'Private Equity' in next(iter(pdf_sections.values()))


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
def test_sources_create_align_verify_delete_and_micro_lesson_flow(client, sample_tree, monkeypatch):
    build, block, atom1, atom2 = sample_tree
    monkeypatch.setattr('ai_engine.config._get_api_key', lambda: '')

    # 1. Create Markdown source document with auto_align
    md_content = (
        '# 第2章 组织形式与税负\n'
        '## 2.1 合伙型基金税负规则\n'
        '合伙型基金遵循先分后税原则，自然人LP与法人LP分别计税，区别于公司型基金双重征税。\n'
        '## 2.2 估值倍数与IRR推演\n'
        '基金估值使用市盈率倍数，绩效衡量采用DPI与TVPI以及IRR折现率。\n'
    )
    create_resp = client.post(
        f'/{build.pk}/sources/',
        {
            'source_kind': 'markdown',
            'title': '基金从业协会教材',
            'content': md_content,
            'is_primary': True,
            'auto_align': True,
        },
        format='json',
    )
    assert create_resp.status_code == 201
    source_data = create_resp.data['source']
    assert source_data['parse_status'] == 'ready'
    assert source_data['node_count'] == 3
    assert create_resp.data['coverage']['aligned_atom_count'] >= 1
    source_id = source_data['id']

    # 2. List sources
    list_resp = client.get(f'/{build.pk}/sources/')
    assert list_resp.status_code == 200
    assert len(list_resp.data['sources']) == 1

    # 3. Manual re-align & verify/delete an alignment
    align_resp = client.post(f'/{build.pk}/sources/{source_id}/align/', {}, format='json')
    assert align_resp.status_code == 200
    alignments = align_resp.data['alignments']
    assert len(alignments) >= 1
    first_align_id = alignments[0]['id']

    patch_resp = client.patch(
        f'/{build.pk}/sources/{source_id}/alignments/{first_align_id}/',
        {'is_verified': True},
        format='json',
    )
    assert patch_resp.status_code == 200
    assert patch_resp.data['is_verified'] is True

    # 4. Block resources fast load (include_candidates=0) returns source_alignments without candidates
    fast_resp = client.get(f'/{build.pk}/blocks/{block.pk}/resources/?include_candidates=0')
    assert fast_resp.status_code == 200
    assert fast_resp.data['internal_candidates'] == []
    assert fast_resp.data['wiki_candidates'] == []
    assert len(fast_resp.data['source_alignments']) >= 1

    # 5. Micro-lesson GET before generation -> exists: False with grounded citations
    get_lesson = client.get(f'/{build.pk}/atoms/{atom1.pk}/micro-lesson/')
    assert get_lesson.status_code == 200
    assert get_lesson.data['exists'] is False
    assert get_lesson.data['difficulty_tier'] == 'L2'

    # 6. Micro-lesson POST lazy generation -> caches in DB & injects source citations
    gen_lesson = client.post(f'/{build.pk}/atoms/{atom1.pk}/micro-lesson/', {'style': 'balanced'}, format='json')
    assert gen_lesson.status_code == 200
    assert gen_lesson.data['exists'] is True
    assert gen_lesson.data['version'] == 1
    assert gen_lesson.data['is_source_grounded'] is True
    assert len(gen_lesson.data['visuals']) == 1
    assert gen_lesson.data['visuals'][0]['type'] == 'comparison_table'
    assert gen_lesson.data['quick_check']['answer'] in ('A', 'B', 'C', 'D')

    # Subsequent GET hits cache directly
    cached_lesson = client.get(f'/{build.pk}/atoms/{atom1.pk}/micro-lesson/')
    assert cached_lesson.status_code == 200
    assert cached_lesson.data['exists'] is True
    assert cached_lesson.data['version'] == 1

    # Regenerate increments version
    regen_lesson = client.post(
        f'/{build.pk}/atoms/{atom1.pk}/micro-lesson/',
        {'regenerate': True, 'style': 'exam'},
        format='json',
    )
    assert regen_lesson.status_code == 200
    assert regen_lesson.data['version'] == 2
    assert regen_lesson.data['style'] == 'exam'

    # L3 atom produces storyboard visual
    l3_lesson = client.post(f'/{build.pk}/atoms/{atom2.pk}/micro-lesson/', {}, format='json')
    assert l3_lesson.status_code == 200
    assert l3_lesson.data['difficulty_tier'] == 'L3'
    assert l3_lesson.data['visuals'][0]['type'] == 'storyboard'

    # 7. Delete alignment & source
    del_align = client.delete(f'/{build.pk}/sources/{source_id}/alignments/{first_align_id}/')
    assert del_align.status_code == 204
    del_source = client.delete(f'/{build.pk}/sources/{source_id}/')
    assert del_source.status_code == 204
    assert not models.TreeSourceDocument.objects.filter(pk=source_id).exists()


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
def test_sources_multipart_markdown_file_upload_and_bilibili_outline(client, sample_tree):
    build, _, _, _ = sample_tree
    uploaded = SimpleUploadedFile('notes.md', '# 第一讲 基金税务\n合伙型基金先分后税。'.encode('utf-8'), content_type='text/markdown')
    resp = client.post(f'/{build.pk}/sources/', {'file': uploaded}, format='multipart')
    assert resp.status_code == 201
    assert resp.data['source']['source_kind'] == 'markdown'
    assert resp.data['source']['node_count'] == 1

    bili_resp = client.post(
        f'/{build.pk}/sources/',
        {
            'source_kind': 'bilibili_series',
            'title': '基金精讲合集',
            'url': 'https://www.bilibili.com/video/BV1xx411c7mD',
            'outline_text': 'P1 合伙型基金税负规则\nP2 估值倍数与IRR计算',
        },
        format='json',
    )
    assert bili_resp.status_code == 201
    assert bili_resp.data['source']['node_count'] == 2
    assert bili_resp.data['source']['toc_tree'][0]['locator'] == 'P1'


def test_dsh_visual_cards_validate_v2_multimodal_types():
    cd = build_learning_visual({
        'type': 'concept_diagram',
        'payload': {
            'title': '合伙税负流程',
            'layout': 'flow',
            'nodes': [
                {'id': 'n1', 'label': '基金实现收益', 'detail': '项目退出分红'},
                {'id': 'n2', 'label': '先分后税', 'detail': '穿透至各合伙人纳税', 'highlight': True},
            ],
            'edges': [{'from': 'n1', 'to': 'n2', 'label': '分配'}],
        },
    })
    assert cd is not None and cd['type'] == 'concept_diagram'

    ct = build_learning_visual({
        'type': 'comparison_table',
        'payload': {
            'title': '公司型 vs 合伙型',
            'columns': ['公司型', '合伙型'],
            'rows': [{'dimension': '税负', 'cells': ['双重征税', '先分后税'], 'pitfall': '合伙企业不缴企业所得税'}],
        },
    })
    assert ct is not None and ct['type'] == 'comparison_table'

    sb = build_learning_visual({
        'type': 'storyboard',
        'payload': {
            'title': 'IRR 推导板书',
            'frames': [
                {'step': 1, 'heading': '写出净现值方程', 'board': '令 NPV = 0', 'formula': r'\sum \frac{CF_t}{(1+IRR)^t}=0'},
                {'step': 2, 'heading': '试算插值求解', 'board': '找一正一负两个折现率做线性插值'},
            ],
        },
    })
    assert sb is not None and sb['type'] == 'storyboard'
