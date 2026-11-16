"""Public catalog import, whole-tree alignment, regional routing and API editing."""
import importlib
import json
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings

from knowledge_builder import models


pytestmark = [pytest.mark.django_db,
              pytest.mark.usefixtures('isolated_public_catalog')]


@pytest.fixture
def isolated_public_catalog(monkeypatch):
    """Keep recommendations deterministic and ensure tests never query a live wiki."""
    resolver = importlib.import_module('knowledge_builder.public_asset_resolvers')
    def unexpected_fetch(url):
        raise AssertionError(f'Unexpected live public fetch: {url}')
    monkeypatch.setattr(resolver, '_public_text', unexpected_fetch)
    monkeypatch.setattr(resolver, 'load_seed_public_assets', lambda *args, **kwargs: [])
    monkeypatch.setattr(resolver, 'search_wikipedia_concepts', lambda *args, **kwargs: [])
    return resolver


def make_tree(user, subject='微积分', titles=('极限', '连续性', '导数')):
    build = models.KnowledgeTreeBuild.objects.create(
        subject=subject, created_by=user, status='COMPLETED')
    module = models.TreeModule.objects.create(
        build=build, code='M1', title=subject, path=subject)
    for index, title in enumerate(titles, 1):
        block = models.LearningBlock.objects.create(
            build=build, code=f'B{index}', short_title=title,
            narrative_summary=f'理解{title}', layer=index, order=index)
        step = models.BlockStep.objects.create(
            block=block, step_index=1, step_title=f'{title}定义', step_role='概念')
        atom = models.TreeAtomPoint.objects.create(
            build=build, module=module, code=f'A{index}', name=title,
            goal_statement=f'理解{title}', parent_path=subject,
            goal_type='概念', cognitive_level='理解', granularity_minutes=4,
            key_elements=[f'{title}定义', f'{title}条件'], order=index)
        models.BlockStepAtom.objects.create(
            step=step, atom=atom, membership_type='core', position=0)
    return build


@pytest.fixture
def tree(user):
    return make_tree(user)


def catalog(build, **overrides):
    values = dict(
        subject=build.subject, title='极限直觉',
        url='https://www.bilibili.com/video/BV1public001/',
        source_kind='bilibili', asset_track='spotlight', region_scope='cn',
        description='极限定义与条件', topic_keywords=['极限'])
    values.update(overrides)
    return models.PublicAssetCatalog.objects.create(**values)


def series_data():
    base = 'https://www.bilibili.com/video/BV1public001/'
    return dict(title='微积分课程', url=base, source_kind='bilibili',
                asset_track='spine', region_scope='cn', description='微积分主线',
                topic_keywords=['微积分'], segments=[
                    dict(index=index, title=title, url=f'{base}?p={index}',
                         locator=f'P{index}', summary=title)
                    for index, title in enumerate(('极限', '第二讲', '导数'), 1)])


def mock_public_page(monkeypatch, resolver, url, html):
    def read(request_url, *args, **kwargs):
        assert request_url == url
        return url, html
    monkeypatch.setattr('ai_assistant.services.learning_resources.public_text', read)
    monkeypatch.setattr(resolver, '_public_text', read)


def test_bilibili_multipage_import_aligns_and_persists(
        tree, user, monkeypatch, isolated_public_catalog):
    from knowledge_builder.public_asset_service import import_tree_public_asset
    url = 'https://www.bilibili.com/video/BV1public001/'
    video = dict(title='微积分课程', desc='极限、连续性和导数', pages=[
        dict(page=index, part=title, cid=100 + index)
        for index, title in enumerate(('极限', '第二讲', '导数'), 1)])
    html = '<script>window.__INITIAL_STATE__=' + json.dumps(
        {'videoData': video}, ensure_ascii=False) + ';</script>'
    mock_public_page(monkeypatch, isolated_public_catalog, url, html)
    result = import_tree_public_asset(user, tree, {'url': url})
    assert result['asset_track'] == 'spine'
    assert result['mounted_count'] == 3
    saved = models.PublicAssetCatalog.objects.get(subject=tree.subject)
    assert saved.url == url.rstrip('/')
    assert saved.asset_track == 'spine' and len(saved.segments) == 3
    resources = list(tree.block_resources.order_by('locator'))
    assert [row.url for row in resources] == [f'{url.rstrip("/")}?p={i}' for i in (1, 2, 3)]
    assert [row.block.short_title for row in resources] == ['极限', '连续性', '导数']
    assert all(row.public_asset_id == saved.pk and row.pedagogical_role == 'series_episode'
               for row in resources)
    assert import_tree_public_asset(user, tree, {'public_asset_id': saved.pk})['mounted_count'] == 3
    assert tree.block_resources.count() == 3


def test_bilibili_single_episode_is_spotlight(
        tree, user, monkeypatch, isolated_public_catalog):
    from knowledge_builder.public_asset_service import import_tree_public_asset
    url = 'https://www.bilibili.com/video/BV1single001/'
    state = {'videoData': {'title': '导数的直观含义', 'desc': '导数定义',
                           'pages': [{'page': 1, 'part': '导数', 'cid': 1}]}}
    mock_public_page(monkeypatch, isolated_public_catalog, url,
                     '<script>window.__INITIAL_STATE__=' + json.dumps(state) + ';</script>')
    result = import_tree_public_asset(user, tree, {'url': url})
    row = result['resources'][0]
    assert result['mounted_count'] == 1 and row.asset_track == 'spotlight'
    assert row.source_kind == 'bilibili' and row.block.short_title == '导数'
    assert row.atom.name == '导数' and row.step.block_id == row.block_id


def test_series_unknown_titles_use_monotonic_order(tree, user):
    from knowledge_builder.public_asset_service import align_and_mount_spine_series
    resources = align_and_mount_spine_series(tree, series_data(), user=user)
    assert [row.block.short_title for row in resources] == ['极限', '连续性', '导数']
    assert all(row.asset_track == 'spine' for row in resources)


def test_github_repository_chapters_resolve_and_align(
        tree, user, monkeypatch, isolated_public_catalog):
    from knowledge_builder.public_asset_service import import_tree_public_asset
    url = 'https://github.com/public/calculus'
    html = '<title>微积分开源教程</title>' + ''.join(
        f'<a href="chapters/{filename}.md">{title}</a>'
        for filename, title in (('limits', '极限'), ('continuity', '连续性'), ('derivative', '导数')))
    mock_public_page(monkeypatch, isolated_public_catalog, url, html)
    result = import_tree_public_asset(user, tree, {'url': url})
    assert result['mounted_count'] == 3 and result['asset_track'] == 'spine'
    resources = result['resources']
    assert [row.block.short_title for row in resources] == ['极限', '连续性', '导数']
    assert [row.url for row in resources] == [
        f'{url}/blob/HEAD/chapters/{name}.md' for name in ('limits', 'continuity', 'derivative')]
    assert all(row.source_kind == 'github' and row.region_scope == 'global' for row in resources)


@pytest.mark.parametrize('lang,scope', [('zh', 'cn'), ('en', 'intl')])
def test_wikipedia_entry_preserves_anchor_and_wiki_track(
        tree, user, monkeypatch, isolated_public_catalog, lang, scope):
    from knowledge_builder.public_asset_service import import_tree_public_asset
    url = f'https://{lang}.wikipedia.org/wiki/Limit#Definition'
    mock_public_page(monkeypatch, isolated_public_catalog, url,
                     '<title>极限</title><h1>极限</h1><p>极限定义</p><h2 id="Definition">定义</h2>')
    result = import_tree_public_asset(user, tree, {'url': url})
    resource = result['resources'][0]
    assert result['mounted_count'] == 1 and resource.asset_track == 'wiki'
    assert resource.source_kind == 'wikipedia' and resource.region_scope == scope
    assert resource.url == url and resource.locator == '#Definition'
    assert resource.pedagogical_role == 'wiki_reference' and resource.atom.name == '极限'
    repeated = import_tree_public_asset(user, tree, {'public_asset_id': result['public_asset'].pk})
    assert repeated['resources'][0].pk == resource.pk
    assert repeated['resources'][0].url == url and repeated['resources'][0].locator == '#Definition'
    assert tree.block_resources.count() == 1


def test_custom_outline_supplies_missing_series_segments(
        tree, user, monkeypatch, isolated_public_catalog):
    from knowledge_builder.public_asset_service import import_tree_public_asset
    url = 'https://www.bilibili.com/video/BV1outline01'
    mock_public_page(monkeypatch, isolated_public_catalog, url, '<title>微积分课程</title>')
    result = import_tree_public_asset(user, tree, {
        'url': url, 'title': '自定义微积分主线', 'asset_track': 'spine',
        'outline_text': 'P1 极限\nP2 连续性\nP3 导数'})
    assert result['mounted_count'] == 3
    assert result['public_asset'].title == '自定义微积分主线'
    assert len(result['public_asset'].segments) == 3
    assert [row.block.short_title for row in result['resources']] == ['极限', '连续性', '导数']


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
def test_block_url_import_resolves_locator_and_persists_catalog(
        tree, auth_client, monkeypatch, isolated_public_catalog):
    block = tree.blocks.get(short_title='导数')
    url = 'https://www.bilibili.com/video/BV1single001?p=1&t=90'
    state = {'videoData': {'title': '导数的直观含义',
                           'pages': [{'page': 1, 'part': '导数', 'cid': 1}]}}
    mock_public_page(monkeypatch, isolated_public_catalog, url,
                     '<script>window.__INITIAL_STATE__=' + json.dumps(state) + ';</script>')
    response = auth_client.post(f'/{tree.pk}/blocks/{block.pk}/resources/',
                                {'url': url}, format='json')
    assert response.status_code == 201
    row = models.BlockResource.objects.get(pk=response.data['id'])
    assert row.source_kind == 'bilibili' and row.asset_track == 'spotlight'
    assert row.locator == 'P1 · 01:30' and row.region_scope == 'cn'
    assert row.url == url and row.atom.name == '导数'
    assert row.public_asset.subject == tree.subject and row.public_asset.url == url


def test_seed_catalog_sync_updates_and_filters_region(tree, monkeypatch, isolated_public_catalog):
    from knowledge_builder.public_asset_service import ensure_subject_public_assets
    seed = dict(title='极限种子讲解', url='https://www.bilibili.com/video/BV1seed0001',
                source_kind='bilibili', asset_track='spotlight', region_scope='cn',
                description='第一版', topic_keywords=['极限'], segments=[])
    monkeypatch.setattr(isolated_public_catalog, 'load_seed_public_assets',
                        lambda subject, region_pref: [seed])
    first = ensure_subject_public_assets(tree.subject)
    assert len(first) == 1 and first[0].subject == tree.subject
    seed['description'] = '更新后的介绍'
    again = ensure_subject_public_assets(tree.subject)
    assert len(again) == 1 and again[0].pk == first[0].pk
    assert again[0].description == '更新后的介绍'


def test_automatic_mount_selects_only_one_spine(tree):
    from knowledge_builder.public_asset_service import auto_mount_public_assets
    first_data = series_data()
    first = catalog(tree, title=first_data['title'], asset_track='spine',
                    segments=first_data['segments'], topic_keywords=['微积分'])
    second = catalog(tree, title='另一套微积分', url='https://github.com/public/other-calculus',
                     asset_track='spine', source_kind='github', region_scope='global',
                     segments=first_data['segments'], topic_keywords=['微积分'])
    auto_mount_public_assets(tree)
    assert tree.block_resources.filter(asset_track='spine').count() == 3
    assert len(set(tree.block_resources.filter(asset_track='spine').values_list('public_asset_id', flat=True))) == 1
    assert set(tree.block_resources.values_list('public_asset_id', flat=True)) <= {first.pk, second.pk}


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
def test_same_catalog_asset_can_be_attached_to_distinct_blocks(tree, auth_client):
    asset = catalog(tree)
    blocks = list(tree.blocks.order_by('order')[:2])
    for block in blocks:
        response = auth_client.post(f'/{tree.pk}/blocks/{block.pk}/resources/',
                                    {'public_asset_id': asset.pk}, format='json')
        assert response.status_code == 201
        assert response.data['block'] == block.pk
    resources = tree.block_resources.filter(public_asset=asset)
    assert resources.count() == 2
    assert set(resources.values_list('block_id', flat=True)) == {block.pk for block in blocks}


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
def test_block_wiki_recommendations_use_language_and_filter_intl(
        tree, auth_client, monkeypatch, isolated_public_catalog):
    block = tree.blocks.get(short_title='极限')
    atom = tree.atoms.get(name='极限')
    atom.name = '函数极限'
    atom.save(update_fields=['name'])
    calls = []
    chinese = dict(title='极限', url='https://zh.wikipedia.org/wiki/极限',
                   asset_track='wiki', source_kind='wikipedia', region_scope='cn')
    english = dict(title='Limit', url='https://en.wikipedia.org/wiki/Limit',
                   asset_track='wiki', source_kind='wikipedia', region_scope='intl')
    def search(query, lang='zh', limit=5, fetcher=None):
        assert limit == 5
        calls.append((query, lang))
        return [chinese, english] if lang == 'zh' else [english]
    monkeypatch.setattr(isolated_public_catalog, 'search_wikipedia_concepts', search)
    path = f'/{tree.pk}/blocks/{block.pk}/resources/'
    domestic = auth_client.get(path)
    assert domestic.status_code == 200
    assert calls == [('极限', 'zh')]
    assert domestic.data['wiki_candidates'] == [chinese]
    calls.clear()
    international = auth_client.get(path, HTTP_ACCEPT_LANGUAGE='en-US')
    assert international.status_code == 200
    assert calls == [('极限', 'en')]
    assert international.data['wiki_candidates'] == [english]
    block.short_title = ''
    block.save(update_fields=['short_title'])
    calls.clear()
    assert auth_client.get(path).status_code == 200
    assert calls == [('函数极限', 'zh')]


@pytest.mark.parametrize('lang,region', [('zh', 'cn'), ('', 'cn'), ('en', 'intl')])
def test_region_preference_user_language(user, lang, region):
    from knowledge_builder.public_asset_service import get_region_preference
    user.preferred_language = lang
    assert get_region_preference(user) == region


def test_region_preference_accept_language_and_explicit_override(user):
    from knowledge_builder.public_asset_service import get_region_preference
    request = SimpleNamespace(headers={'Accept-Language': 'en-US,en;q=0.9'})
    assert get_region_preference(user, request) == 'intl'
    assert get_region_preference(user, request, explicit_region='cn') == 'cn'
    assert get_region_preference(user, explicit_region='intl') == 'intl'


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
def test_region_catalog_and_mounted_resources_are_filtered(tree, user, auth_client):
    from knowledge_builder.public_asset_service import auto_mount_public_assets, ensure_subject_public_assets
    cn = catalog(tree)
    github = catalog(tree, title='连续性开源教程', url='https://github.com/public/calculus',
                     source_kind='github', region_scope='global', topic_keywords=['连续性'])
    zh_wiki = catalog(tree, title='极限', url='https://zh.wikipedia.org/wiki/极限',
                      source_kind='wikipedia', asset_track='wiki')
    youtube = catalog(tree, title='极限 English lecture', url='https://www.youtube.com/watch?v=public',
                      source_kind='youtube', region_scope='intl')
    en_wiki = catalog(tree, title='导数 Derivative', url='https://en.wikipedia.org/wiki/Derivative',
                      source_kind='wikipedia', asset_track='wiki', region_scope='intl',
                      topic_keywords=['导数'])
    assert {row.pk for row in ensure_subject_public_assets(tree.subject, 'cn')} == {cn.pk, github.pk, zh_wiki.pk}
    user.preferred_language = 'zh'
    auto_mount_public_assets(tree)
    assert not tree.block_resources.filter(region_scope='intl').exists()
    assert {'bilibili', 'github', 'wikipedia'} <= set(
        tree.block_resources.values_list('source_kind', flat=True))
    user.preferred_language = 'en'
    auto_mount_public_assets(tree)
    assert {youtube.pk, en_wiki.pk} <= set(
        tree.block_resources.filter(region_scope='intl').values_list('public_asset_id', flat=True))
    user.preferred_language = 'zh'
    url = f'/{tree.pk}/public-assets/'
    domestic = auth_client.get(url)
    assert domestic.status_code == 200
    assert not any(row['region_scope'] == 'intl' for row in domestic.data['catalog_assets'])
    english = auth_client.get(url, HTTP_ACCEPT_LANGUAGE='en-US')
    assert {youtube.pk, en_wiki.pk} <= {row['id'] for row in english.data['catalog_assets']}
    block = tree.blocks.get(short_title='极限')
    block_url = f'/{tree.pk}/blocks/{block.pk}/resources/'
    assert not any(row['region_scope'] == 'intl' for row in auth_client.get(block_url).data['resources'])
    assert any(row['region_scope'] == 'intl' for row in auth_client.get(block_url, {'region': 'intl'}).data['resources'])


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
def test_catalog_import_and_block_patch_validate_bindings(tree, user, auth_client):
    asset = catalog(tree)
    response = auth_client.post(f'/{tree.pk}/public-assets/', {'public_asset_id': asset.pk}, format='json')
    assert response.status_code == 201
    assert response.data['mounted_count'] == 1 and response.data['public_asset']['id'] == asset.pk
    row = models.BlockResource.objects.get(pk=response.data['resources'][0]['id'])
    url = f'/{tree.pk}/blocks/{row.block_id}/resources/'
    target_block = tree.blocks.get(short_title='导数')
    atom = tree.atoms.get(name='导数')
    response = auth_client.patch(url, dict(resource_id=row.pk, block_id=target_block.pk,
        atom_id=atom.pk, asset_track='wiki', pedagogical_role='wiki_reference', locator='定义'), format='json')
    assert response.status_code == 200
    row.refresh_from_db()
    assert (row.block_id, row.atom_id, row.asset_track, row.locator) == (target_block.pk, atom.pk, 'wiki', '定义')
    assert row.step.block_id == target_block.pk
    other = make_tree(user, subject='另一个主题')
    new_url = f'/{tree.pk}/blocks/{target_block.pk}/resources/'
    assert auth_client.patch(new_url, {'resource_id': row.pk, 'atom_id': other.atoms.first().pk}, format='json').status_code == 400
    assert auth_client.patch(new_url, {'resource_id': row.pk, 'block_id': other.blocks.first().pk}, format='json').status_code in (400, 404)
    row.refresh_from_db()
    assert row.block_id == target_block.pk and row.atom_id == atom.pk


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
def test_import_free_marketplace_only_and_owner_access(tree, user, auth_client):
    from quizzes.models import MarketplaceListing
    free = MarketplaceListing.objects.create(title='极限习题', subject=tree.subject,
        content_type='question_set', status='published', license_type='free')
    paid = MarketplaceListing.objects.create(title='极限付费课', subject=tree.subject,
        content_type='course', status='published', license_type='one_time')
    draft = MarketplaceListing.objects.create(title='极限草稿课', subject=tree.subject,
        content_type='course', status='draft', license_type='free')
    path = f'/{tree.pk}/public-assets/'
    response = auth_client.post(path, {'marketplace_listing_id': free.pk}, format='json')
    assert response.status_code == 201
    resource = models.BlockResource.objects.get(pk=response.data['resources'][0]['id'])
    assert resource.source_kind == 'marketplace' and resource.marketplace_listing_id == free.pk
    assert resource.url == '/courses'
    for listing in (paid, draft):
        assert auth_client.post(path, {'marketplace_listing_id': listing.pk}, format='json').status_code == 400
    other = get_user_model().objects.create_user(username='public_asset_other')
    auth_client.force_authenticate(user=other)
    assert auth_client.get(path).status_code == 404
    assert auth_client.post(path, {'marketplace_listing_id': free.pk}, format='json').status_code == 404


@override_settings(ROOT_URLCONF='knowledge_builder.urls', UNIMIND_CONTENT_INSTITUTION_ID=None)
def test_album_import_preserves_all_published_episodes(tree, auth_client):
    from courses.models import Album, Course, CourseModule
    album = Album.objects.create(name='微积分主线课')
    module = CourseModule.objects.create(name='公开微积分', is_public=True)
    published = [Course.objects.create(title=title, album_obj=album, module=module,
                 is_published=True, sort_order=index)
                 for index, title in enumerate(('极限', '连续性', '导数'), 1)]
    Course.objects.create(title='未发布课', album_obj=album, module=module, is_published=False)
    path = f'/{tree.pk}/public-assets/'
    response = auth_client.post(path, {'album_id': album.pk}, format='json')
    assert response.status_code == 201 and response.data['mounted_count'] == 3
    resources = list(tree.block_resources.order_by('id'))
    assert {row.course_id for row in resources} == {course.pk for course in published}
    assert all(row.url == '/courses' and row.asset_track == 'spine' for row in resources)
    assert len({row.block_id for row in resources}) == 3
    assert auth_client.post(path, {'album_id': album.pk}, format='json').status_code == 201
    assert tree.block_resources.count() == 3


@override_settings(UNIMIND_CONTENT_INSTITUTION_ID=None)
def test_pipeline_reuses_imported_three_tracks_and_marketplace(
        tree, user, monkeypatch, isolated_public_catalog):
    from ai_engine.ai_service import AIService
    from knowledge_builder.pipeline import create_build, run_build
    from knowledge_builder.public_asset_service import import_tree_public_asset
    from knowledge_builder.tests.test_pipeline_e2e import SemanticFixture
    from quizzes.models import MarketplaceListing
    fixture = SemanticFixture()
    monkeypatch.setattr(AIService, 'structured_output', fixture.ai)
    monkeypatch.setattr('knowledge_builder.embedding_client.httpx.post', fixture.http)
    spine = series_data()
    # These names are provided by the existing six-stage semantic fixture.
    spine['segments'][0]['title'] = '极限能力1'
    spine['segments'][2]['title'] = '连续性能力1'
    monkeypatch.setattr(isolated_public_catalog, 'resolve_public_asset_url', lambda *args, **kwargs: spine)
    imported = import_tree_public_asset(user, tree, {'url': spine['url']})
    spotlight = catalog(tree, title='极限能力1直觉', url='https://www.bilibili.com/video/BV1spotlight/',
                        topic_keywords=['极限能力1'])
    wiki = catalog(tree, title='连续性能力1', url='https://zh.wikipedia.org/wiki/连续性',
                   source_kind='wikipedia', asset_track='wiki', topic_keywords=['连续性能力1'])
    listing = MarketplaceListing.objects.create(title='极限能力1公开课', subject=tree.subject,
        content_type='course', status='published', license_type='free')
    stages = []
    built = run_build(create_build(tree.subject, created_by=user).pk, progress=stages.append)
    assert built.status == 'COMPLETED' and len(stages) == 6
    resources = built.block_resources.all()
    assert {'spine', 'spotlight', 'wiki'} <= set(resources.values_list('asset_track', flat=True))
    assert {imported['public_asset'].pk, spotlight.pk, wiki.pk} <= set(
        resources.values_list('public_asset_id', flat=True))
    assert resources.filter(source_kind='marketplace', marketplace_listing_id=listing.pk, url='/courses').exists()
    assert not resources.filter(region_scope='intl').exists()
