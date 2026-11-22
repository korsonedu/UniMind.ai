"""Public catalog import, whole-tree alignment, regional routing and API editing."""
import importlib
import json
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings

from knowledge_builder import models
from knowledge_builder.public_asset_resolvers import (
    load_seed_public_assets as real_load_seeds,
    search_wikipedia_concepts as real_search_wiki,
)


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


@override_settings(UNIMIND_PUBLIC_ASSET_EDITION='intl')
@pytest.mark.parametrize('lang,scope', [('zh', 'intl'), ('en', 'intl')])
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
    chinese = dict(title='极限', url='https://oi-wiki.org/math/calculus/limits/',
                   asset_track='wiki', source_kind='wikipedia', region_scope='cn')
    english = dict(title='Limit', url='https://en.wikipedia.org/wiki/Limit',
                   asset_track='wiki', source_kind='wikipedia', region_scope='intl')
    def search(query, lang='zh', limit=5, fetcher=None, region_pref=''):
        assert limit == 5
        calls.append((query, lang, region_pref))
        return [chinese, english] if lang == 'zh' else [english]
    monkeypatch.setattr(isolated_public_catalog, 'search_wikipedia_concepts', search)
    path = f'/{tree.pk}/blocks/{block.pk}/resources/'
    domestic = auth_client.get(path)
    assert domestic.status_code == 200
    assert calls == [('极限', 'zh', 'cn')]
    assert domestic.data['wiki_candidates'] == [chinese]
    calls.clear()
    english_domestic = auth_client.get(path, HTTP_ACCEPT_LANGUAGE='en-US')
    assert english_domestic.status_code == 200
    assert calls == [('极限', 'zh', 'cn')]
    assert english_domestic.data['wiki_candidates'] == [chinese]
    calls.clear()
    with override_settings(UNIMIND_PUBLIC_ASSET_EDITION='intl'):
        international = auth_client.get(path, HTTP_ACCEPT_LANGUAGE='en-US')
    assert international.status_code == 200
    assert calls == [('极限', 'en', 'intl')]
    assert international.data['wiki_candidates'] == [english]
    block.short_title = ''
    block.save(update_fields=['short_title'])
    calls.clear()
    assert auth_client.get(path).status_code == 200
    assert calls == [('函数极限', 'zh', 'cn')]


@override_settings(UNIMIND_PUBLIC_ASSET_EDITION='cn')
@pytest.mark.parametrize('lang,region', [('zh', 'cn'), ('', 'cn'), ('en', 'cn')])
def test_region_preference_user_language(user, lang, region):
    from knowledge_builder.public_asset_service import get_region_preference
    user.preferred_language = lang
    assert get_region_preference(user) == region


def test_region_preference_accept_language_and_explicit_override(user):
    from knowledge_builder.public_asset_service import get_region_preference
    request = SimpleNamespace(headers={'Accept-Language': 'en-US,en;q=0.9'})
    assert get_region_preference(user, request) == 'cn'
    with override_settings(UNIMIND_PUBLIC_ASSET_EDITION='intl'):
        assert get_region_preference(user, request) == 'intl'
    assert get_region_preference(user, request, explicit_region='cn') == 'cn'
    assert get_region_preference(user, explicit_region='intl') == 'intl'


@override_settings(ROOT_URLCONF='knowledge_builder.urls', UNIMIND_PUBLIC_ASSET_EDITION='cn')
def test_region_catalog_and_mounted_resources_are_filtered(tree, user, auth_client):
    from knowledge_builder.public_asset_service import auto_mount_public_assets, ensure_subject_public_assets
    cn = catalog(tree)
    wiki = catalog(tree, title='极限词条', url='https://oi-wiki.org/math/calculus/limits/',
                   source_kind='wikipedia', asset_track='wiki')
    forbidden = [catalog(tree, title=f'极限旧条目{index}', url=url,
                         source_kind='wikipedia', asset_track='wiki', region_scope='cn')
                 for index, url in enumerate(FORBIDDEN_URLS)]
    # Historical rows may have the wrong region; the URL is also checked.
    block = tree.blocks.get(short_title='极限')
    for asset in forbidden:
        models.BlockResource.objects.create(build=tree, block=block, public_asset=asset,
            source_kind=asset.source_kind, title=asset.title, url=asset.url, region_scope='cn')
    assert {row.pk for row in ensure_subject_public_assets(tree.subject, 'cn')} == {cn.pk, wiki.pk}
    user.preferred_language = 'en'
    auto_mount_public_assets(tree)
    assert tree.block_resources.filter(public_asset=wiki).exists()
    for path in (f'/{tree.pk}/public-assets/', f'/{tree.pk}/blocks/{block.pk}/resources/'):
        response = auth_client.get(path, {'region': 'intl'}, HTTP_ACCEPT_LANGUAGE='en-US')
        assert response.status_code == 200 and response.data['region_pref'] == 'cn'
        assert_domestic_urls(response.data)
    with override_settings(UNIMIND_PUBLIC_ASSET_EDITION='intl'):
        response = auth_client.get(f'/{tree.pk}/public-assets/', HTTP_ACCEPT_LANGUAGE='en-US')
        assert response.data['region_pref'] == 'intl'
        urls = {row['url'] for row in response.data['catalog_assets']}
        # Properly classified international assets are retained and offered.
        intl_asset = catalog(tree, title='Limit', url='https://en.wikipedia.org/wiki/Limit_(mathematics)',
                             source_kind='wikipedia', asset_track='wiki', region_scope='intl')
        response = auth_client.get(f'/{tree.pk}/public-assets/', HTTP_ACCEPT_LANGUAGE='en-US')
        assert intl_asset.url in {row['url'] for row in response.data['catalog_assets']}
        assert 'https://baike.baidu.com/item/极限' not in urls


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


@override_settings(ROOT_URLCONF='knowledge_builder.urls', UNIMIND_CONTENT_INSTITUTION_ID='global')
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


@override_settings(UNIMIND_CONTENT_INSTITUTION_ID='global')
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
    wiki = catalog(tree, title='连续性能力1', url='https://oi-wiki.org/math/calculus/continuity/',
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


FORBIDDEN_URLS = (
    'https://zh.wikipedia.org/wiki/极限',
    'https://en.wikipedia.org/wiki/Limit',
    'https://www.youtube.com/watch?v=public',
    'https://youtu.be/public',
    'https://ocw.mit.edu/courses/calculus/',
    'https://www.khanacademy.org/math/calculus',
    'https://www.coursera.org/learn/calculus',
    'https://www.edx.org/learn/calculus',
    'https://baike.baidu.com/item/极限',
    'https://ｗｉｋｉｐｅｄｉａ.org/wiki/Limit',
    'https://ｂａｉｋｅ.baidu.com/item/极限',
)


def normalized_host(url):
    from urllib.parse import urlsplit
    return (urlsplit(url).hostname or '').encode('idna').decode('ascii').lower().rstrip('.')


def is_baidu_url(url):
    host = normalized_host(url)
    return host == 'baike.baidu.com' or host.endswith('.baike.baidu.com')


def assert_domestic_urls(value):
    blocked = ('wikipedia.org', 'youtube.com', 'youtu.be', 'ocw.mit.edu',
               'khanacademy.org', 'coursera.org', 'edx.org', 'baike.baidu.com')
    if isinstance(value, dict):
        for key, item in value.items():
            if key == 'url' and isinstance(item, str):
                host = normalized_host(item)
                assert not any(host == domain or host.endswith('.' + domain) for domain in blocked), item
            else:
                assert_domestic_urls(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            assert_domestic_urls(item)


@override_settings(UNIMIND_PUBLIC_ASSET_EDITION='cn')
@pytest.mark.parametrize('subject', ['金融431', '计算机408', '微积分', '线性代数', '通用'])
def test_domestic_seed_subjects_have_all_tracks(subject):
    assets = real_load_seeds(subject, 'cn')
    own = [asset for asset in assets if asset.get('subject') == subject]
    assert {'spine', 'spotlight', 'wiki'} <= {asset['asset_track'] for asset in own}
    assert_domestic_urls(assets)
    assert all(asset['region_scope'] != 'intl' for asset in assets)
    wiki = [asset for asset in own if asset['asset_track'] == 'wiki']
    assert all(asset['source_kind'] == 'wikipedia' for asset in wiki)


@override_settings(UNIMIND_PUBLIC_ASSET_EDITION='cn')
@pytest.mark.parametrize('lang', ['zh', 'en'])
def test_domestic_concept_search_uses_seeds_without_fetching(lang, monkeypatch, isolated_public_catalog):
    monkeypatch.setattr(isolated_public_catalog, 'load_seed_public_assets', real_load_seeds)
    def no_fetch(url):
        pytest.fail(f'Domestic wiki search must not fetch Wikipedia: {url}')
    results = real_search_wiki('矩阵', lang=lang, fetcher=no_fetch)
    assert results
    assert_domestic_urls(results)
    assert all(row['asset_track'] == 'wiki' and row['source_kind'] == 'wikipedia'
               and row['region_scope'] == 'cn' for row in results)


@override_settings(UNIMIND_PUBLIC_ASSET_EDITION='intl')
@pytest.mark.parametrize('lang', ['zh', 'en'])
def test_international_wikipedia_search_preserves_both_languages(lang):
    def fetch(url):
        assert url.startswith(f'https://{lang}.wikipedia.org/w/api.php?')
        return url, json.dumps({'query': {'search': [{'title': 'Limit', 'snippet': 'Limit definition'}]}})
    results = real_search_wiki('Limit', lang=lang, fetcher=fetch)
    assert len(results) == 1
    assert results[0]['url'] == f'https://{lang}.wikipedia.org/wiki/Limit'
    assert results[0]['region_scope'] == 'intl'


@override_settings(ROOT_URLCONF='knowledge_builder.urls', UNIMIND_PUBLIC_ASSET_EDITION='cn')
@pytest.mark.parametrize('url', FORBIDDEN_URLS)
@pytest.mark.parametrize('endpoint', ['tree', 'block'])
def test_domestic_manual_import_rejects_blocked_hosts(tree, auth_client, url, endpoint):
    path = f'/{tree.pk}/public-assets/' if endpoint == 'tree' else f'/{tree.pk}/blocks/{tree.blocks.first().pk}/resources/'
    response = auth_client.post(path + '?region=intl', {'url': url}, format='json', HTTP_ACCEPT_LANGUAGE='en-US')
    assert response.status_code == 400
    if is_baidu_url(url):
        assert '百度百科' in str(response.data)
    else:
        assert '当前为国内版环境' in str(response.data)
    assert tree.block_resources.count() == 0
    assert models.PublicAssetCatalog.objects.count() == 0


@override_settings(ROOT_URLCONF='knowledge_builder.urls', UNIMIND_PUBLIC_ASSET_EDITION='intl')
@pytest.mark.parametrize('url', FORBIDDEN_URLS[:4])
@pytest.mark.parametrize('endpoint', ['tree', 'block'])
def test_international_manual_import_allows_wikipedia_and_youtube(
        tree, auth_client, monkeypatch, isolated_public_catalog, url, endpoint):
    path = f'/{tree.pk}/public-assets/' if endpoint == 'tree' else f'/{tree.pk}/blocks/{tree.blocks.first().pk}/resources/'
    mock_public_page(monkeypatch, isolated_public_catalog, url,
                     '<title>极限</title><h1>极限</h1><p>极限定义</p>')
    response = auth_client.post(path, {'url': url}, format='json')
    assert response.status_code == 201
    resource = tree.block_resources.get()
    assert resource.region_scope == 'intl' and resource.url == url


@override_settings(ROOT_URLCONF='knowledge_builder.urls', UNIMIND_PUBLIC_ASSET_EDITION='intl')
def test_baidu_remains_disabled_in_international_edition(tree, auth_client):
    response = auth_client.post(f'/{tree.pk}/public-assets/',
        {'url': 'https://baike.baidu.com/item/极限'}, format='json')
    assert response.status_code == 400 and '百度百科' in str(response.data)


@pytest.mark.parametrize('host', ['oi-wiki.org', 'www.hello-algo.com'])
def test_open_wiki_resolution_extracts_title_summary_and_anchor(isolated_public_catalog, host):
    url = f'https://{host}/math/matrix/#definition'
    def fetch(request_url):
        assert request_url == url
        return url, '<title>矩阵 - Wiki</title><h1>矩阵</h1><p>矩阵是按行列排列的数组。</p><h2 id="definition">定义</h2>'
    result = isolated_public_catalog.resolve_public_asset_url(url, html_fetcher=fetch)
    assert result['title'] == '矩阵' and result['description'] == '矩阵是按行列排列的数组。'
    assert result['source_kind'] == 'wikipedia' and result['asset_track'] == 'wiki'
    assert result['region_scope'] == 'cn' and result['pedagogical_role'] == 'wiki_reference'
    assert result['url'] == url and result['locator'] == '#definition'
    assert result['segments'][0]['url'] == url


@pytest.mark.parametrize('url', [url for url in FORBIDDEN_URLS if not is_baidu_url(url)])
def test_all_blocked_international_domains_infer_intl(isolated_public_catalog, url):
    assert isolated_public_catalog.infer_region_scope(url) == 'intl'


@override_settings(ROOT_URLCONF='knowledge_builder.urls', UNIMIND_PUBLIC_ASSET_EDITION='cn')
def test_domestic_import_rejects_redirect_to_wikipedia(tree, auth_client, monkeypatch, isolated_public_catalog):
    monkeypatch.setattr('ai_assistant.services.learning_resources.public_text', lambda url:
        ('https://zh.wikipedia.org/wiki/极限', '<h1>极限</h1><p>定义</p>'))
    response = auth_client.post(f'/{tree.pk}/public-assets/', {'url': 'https://oi-wiki.org/math/limits/'}, format='json')
    assert response.status_code == 400 and '当前为国内版环境' in str(response.data)
    assert not models.PublicAssetCatalog.objects.exists()


@override_settings(ROOT_URLCONF='knowledge_builder.urls', UNIMIND_PUBLIC_ASSET_EDITION='cn')
def test_domestic_import_rejects_international_outline_segment(tree, auth_client, monkeypatch, isolated_public_catalog):
    url = 'https://www.bilibili.com/video/BV1outline01'
    mock_public_page(monkeypatch, isolated_public_catalog, url, '<title>微积分课程</title>')
    response = auth_client.post(f'/{tree.pk}/public-assets/', {
        'url': url, 'asset_track': 'spine',
        'outline_text': 'P1 极限 https://www.youtube.com/watch?v=public\nP2 导数 https://oi-wiki.org/math/calculus/'}, format='json')
    assert response.status_code == 400 and '当前为国内版环境' in str(response.data)
    assert not models.PublicAssetCatalog.objects.exists()


def test_domestic_seed_loader_filters_mislabeled_urls_and_segments(tmp_path, monkeypatch, isolated_public_catalog):
    good = dict(subject='通用', title='矩阵', url='https://oi-wiki.org/math/matrix/',
                source_kind='wikipedia', asset_track='wiki', region_scope='cn', segments=[])
    assets = [good]
    assets.extend(dict(good, url=url, region_scope='global') for url in FORBIDDEN_URLS)
    assets.append(dict(good, url='https://oi-wiki.org/math/matrix/intl/', region_scope='intl'))
    assets.append(dict(good, url='https://www.bilibili.com/video/BV1mixed', asset_track='spine',
                       segments=[dict(index=1, title='极限', url=FORBIDDEN_URLS[0])]))
    path = tmp_path / 'seed.json'
    path.write_text(json.dumps({'assets': assets}), encoding='utf-8')
    monkeypatch.setattr(isolated_public_catalog, '_SEED_PATH', path)
    results = real_load_seeds('通用', 'cn')
    assert results == [good]
    assert_domestic_urls(results)


@override_settings(ROOT_URLCONF='knowledge_builder.urls', UNIMIND_PUBLIC_ASSET_EDITION='cn')
def test_domestic_web_search_filters_forbidden_sources(tree, auth_client, monkeypatch):
    from xml.sax.saxutils import escape
    good = 'https://oi-wiki.org/math/calculus/limits/'
    xml = '<rss><channel>' + ''.join(
        f'<item><title>极限</title><link>{escape(url)}</link><description>极限定义</description></item>'
        for url in [*FORBIDDEN_URLS, good]) + '</channel></rss>'
    monkeypatch.setattr('ai_assistant.services.learning_resources.public_text', lambda url: (url, xml))
    path = f'/{tree.pk}/blocks/{tree.blocks.first().pk}/resources/'
    response = auth_client.get(path, {'query': '极限', 'region': 'intl'}, HTTP_ACCEPT_LANGUAGE='en-US')
    assert response.status_code == 200
    assert [item['url'] for item in response.data['web_candidates']] == [good]
    assert_domestic_urls(response.data)


@override_settings(UNIMIND_PUBLIC_ASSET_EDITION='intl')
def test_youtube_playlist_parser_preserves_international_series(isolated_public_catalog):
    url = 'https://www.youtube.com/playlist?list=public'
    videos = [{'playlistVideoRenderer': {'videoId': f'lecture{index}',
               'title': {'simpleText': title}}}
              for index, title in enumerate(['极限', '导数'], 1)]
    def fetch(request_url):
        assert request_url == url
        return url, '<title>微积分课程</title><script>' + json.dumps(videos) + '</script>'
    result = isolated_public_catalog.resolve_public_asset_url(url, html_fetcher=fetch)
    assert result['source_kind'] == 'youtube' and result['region_scope'] == 'intl'
    assert result['asset_track'] == 'spine'
    assert [row['title'] for row in result['segments']] == ['极限', '导数']
    assert [row['url'] for row in result['segments']] == [
        'https://www.youtube.com/watch?v=lecture1', 'https://www.youtube.com/watch?v=lecture2']


@override_settings(UNIMIND_PUBLIC_ASSET_EDITION='unknown')
def test_unknown_edition_keeps_domestic_region_and_seed_search(user, monkeypatch, isolated_public_catalog):
    from knowledge_builder.public_asset_service import get_region_preference
    user.preferred_language = 'en'
    request = SimpleNamespace(headers={'Accept-Language': 'en-US'}, query_params={'region': 'intl'})
    assert get_region_preference(user, request) == 'cn'
    seed = dict(title='矩阵', url='https://oi-wiki.org/math/linear-algebra/matrix/',
                subject='线性代数', description='矩阵定义', topic_keywords=['矩阵'],
                source_kind='wikipedia', asset_track='wiki', region_scope='cn')
    def seeds(subject='', region_pref='cn'):
        assert region_pref == 'cn'
        return [seed]
    monkeypatch.setattr(isolated_public_catalog, 'load_seed_public_assets', seeds)
    def no_fetch(url):
        pytest.fail(f'Unknown edition must keep domestic search: {url}')
    results = real_search_wiki('矩阵', lang='en', fetcher=no_fetch)
    assert [row['url'] for row in results] == [seed['url']]
    assert_domestic_urls(results)


@override_settings(ROOT_URLCONF='knowledge_builder.urls', UNIMIND_PUBLIC_ASSET_EDITION='cn')
@pytest.mark.parametrize('url', [FORBIDDEN_URLS[0], FORBIDDEN_URLS[2], FORBIDDEN_URLS[-1]])
def test_domestic_patch_rejects_legacy_forbidden_resource(tree, auth_client, url):
    block = tree.blocks.get(short_title='极限')
    target = tree.blocks.get(short_title='导数')
    resource = models.BlockResource.objects.create(build=tree, block=block,
        source_kind='web', title='历史资源', url=url, region_scope='cn', locator='旧定位')
    response = auth_client.patch(f'/{tree.pk}/blocks/{block.pk}/resources/?region=intl', {
        'resource_id': resource.pk, 'block_id': target.pk, 'locator': '新定位'}, format='json')
    assert response.status_code == 400
    assert ('百度百科' if is_baidu_url(url) else '当前为国内版环境') in str(response.data)
    resource.refresh_from_db()
    assert resource.block_id == block.pk and resource.locator == '旧定位'


def test_deepseek_search_parses_official_response_and_filters_web(monkeypatch):
    from knowledge_builder import public_asset_discovery as discovery
    monkeypatch.setattr('ai_engine.config._get_api_key', lambda: 'test-key')
    monkeypatch.delenv('TENCENT_WSA_SECRET_ID', raising=False)
    monkeypatch.delenv('TENCENT_WSA_SECRET_KEY', raising=False)
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        assert url == 'https://api.deepseek.com/v1/tools/search'
        assert kwargs['headers']['Authorization'] == 'Bearer test-key'
        assert kwargs['json'] == {'query': '合格投资者'}
        assert kwargs['timeout'] == 15
        payload = {'results': [
            {'title': '私募基金合格投资者定义', 'url': 'https://www.csrc.gov.cn/rules/investor',
             'snippet': '合格投资者认定条件', 'site_name': '中国证监会',
             'authority': 3, 'rerank_score': 0.91, 'date': '2025-01-01'},
            {'title': '重复', 'url': 'https://www.csrc.gov.cn/rules/investor#top'},
            {'title': '百科', 'url': 'https://baike.baidu.com/item/合格投资者'},
            {'title': '境外', 'url': 'https://www.youtube.com/watch?v=investor'},
        ]}
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)

    monkeypatch.setattr(discovery.httpx, 'post', post)
    parsed = discovery.DeepSeekSearchProvider().search('合格投资者')
    assert parsed[0]['summary'] == '合格投资者认定条件'
    assert parsed[0]['authority'] == 3 and parsed[0]['rerank_score'] == 0.91
    assert parsed[0]['provider'] == 'deepseek' and parsed[0]['site_name'] == '中国证监会'
    results = discovery.search_public_web('合格投资者', limit=8)
    assert len(results) == 1
    assert results[0]['url'] == 'https://www.csrc.gov.cn/rules/investor'
    assert len(calls) == 2


@pytest.mark.parametrize('candidate', [
    {'title': '私募股权合格投资者', 'url': 'https://baike.baidu.com/item/investor'},
    {'title': '私募股权合格投资者', 'url': 'https://www.youtube.com/watch?v=investor'},
    {'title': '私募股权合格投资者', 'url': 'http://www.csrc.gov.cn/investor'},
    {'title': '私募股权保过班 包过 扫码领取 免费领资料', 'summary': '加微信代报名',
     'url': 'https://example.cn/course'},
    {'title': '基金从业《证券投资基金基础知识》全套精讲', 'summary': '证券投资基金课程',
     'url': 'https://www.bilibili.com/video/BV1unrelated', 'asset_track': 'spine'},
    {'title': '基金从业《基金法律法规》精讲', 'summary': '基金法律法规考试',
     'url': 'https://www.bilibili.com/video/BV1lawonly', 'asset_track': 'spotlight'},
    {'title': '手机配件促销购买', 'summary': '商城秒杀', 'url': 'https://item.jd.com/123.html'},
])
def test_auto_discovery_quality_rejects_unsafe_noise_and_other_subject(candidate):
    from knowledge_builder.public_asset_discovery import evaluate_candidate_quality
    assert evaluate_candidate_quality(candidate, '基金从业《私募股权投资基金基础知识》',
                                      ['合格投资者', '合格投资者认定条件']) == 0


def test_auto_discovery_quality_prefers_current_authoritative_regulations():
    from knowledge_builder.public_asset_discovery import evaluate_candidate_quality
    candidate = dict(title='2025年私募基金合格投资者认定规定',
                     summary='私募股权投资基金合格投资者认定条件和资产要求',
                     url='https://www.csrc.gov.cn/rules/investor', authority=3,
                     rerank_score=0.95, asset_track='wiki')
    assert evaluate_candidate_quality(candidate, '基金从业《私募股权投资基金基础知识》',
                                      ['合格投资者', '合格投资者认定条件']) > 0
    assert evaluate_candidate_quality(dict(candidate, title='2016年私募基金合格投资者考试大纲',
        summary='2016年旧版法规考纲'), '基金从业《私募股权投资基金基础知识》', ['合格投资者']) < evaluate_candidate_quality(
            candidate, '基金从业《私募股权投资基金基础知识》', ['合格投资者'])


def test_bilibili_public_pages_drop_marketing_and_short_segments(monkeypatch):
    from knowledge_builder import public_asset_discovery as discovery
    pages = [
        {'page': 1, 'part': '扫码领取资料包', 'duration': 180},
        {'page': 2, 'part': '课程导读', 'duration': 30},
        {'page': 3, 'part': '合格投资者认定', 'duration': 900},
        {'page': 4, 'part': '私募基金募集', 'duration': 1200},
        {'page': 5, 'part': '股权投资基金运作', 'duration': 1800},
    ]

    def get(url, **kwargs):
        assert url == 'https://api.bilibili.com/x/web-interface/view'
        assert kwargs['params'] == {'bvid': 'BV1public001'}
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {
            'code': 0, 'data': {'title': '私募股权投资基金精讲', 'desc': '基金从业课程',
                'stat': {'view': 100000, 'favorite': 1000}, 'pubdate': 1735689600, 'pages': pages}})

    monkeypatch.setattr(discovery.httpx, 'get', get)
    candidate = dict(title='搜索标题', url='https://www.bilibili.com/video/BV1public001/?spm_id_from=test')
    result = discovery.enrich_bilibili_candidate(candidate)
    assert result['url'] == 'https://www.bilibili.com/video/BV1public001'
    assert result['title'] == '私募股权投资基金精讲' and result['asset_track'] == 'spine'
    assert [row['locator'] for row in result['segments']] == ['P3', 'P4', 'P5']
    assert [row['url'] for row in result['segments']] == [f'{result["url"]}?p={page}' for page in (3, 4, 5)]
    pages.pop()
    single = discovery.enrich_bilibili_candidate(candidate)
    assert single['asset_track'] == 'spotlight'


def test_bilibili_metadata_failure_keeps_search_result(monkeypatch):
    from knowledge_builder import public_asset_discovery as discovery
    def fail(*args, **kwargs):
        raise discovery.httpx.TimeoutException('offline fixture')
    monkeypatch.setattr(discovery.httpx, 'get', fail)
    result = discovery.enrich_bilibili_candidate(dict(title='合格投资者讲解',
        summary='私募基金合格投资者认定', url='https://www.bilibili.com/video/BV1public001'))
    assert result['title'] == '合格投资者讲解' and result['asset_track'] == 'spotlight'


@override_settings(ROOT_URLCONF='knowledge_builder.urls', UNIMIND_PUBLIC_ASSET_EDITION='cn')
def test_resource_vote_toggle_dismissal_visibility_and_index_aggregation(tree, user, auth_client):
    asset = catalog(tree)
    block = tree.blocks.first()
    row = models.BlockResource.objects.create(build=tree, block=block, public_asset=asset,
        title=asset.title, url=asset.url, source_kind='bilibili', origin='auto', locator='P1')
    index = models.ConceptAssetIndex.objects.create(subject_domain=tree.subject,
        concept_name='极限', public_asset=asset, segment_locator='P1')
    path = f'/{tree.pk}/blocks/{block.pk}/resources/'
    for vote, expected in ((1, (1, 0, 1)), (-1, (0, 1, -1)), (0, (0, 0, 0))):
        response = auth_client.post(path, {'action': 'vote', 'resource_id': row.pk, 'vote': vote}, format='json')
        assert response.status_code == 200
        assert tuple(response.data[key] for key in ('upvotes', 'downvotes', 'user_vote')) == expected
        index.refresh_from_db()
        assert (index.upvotes, index.downvotes) == expected[:2]
    assert not models.BlockResourceFeedback.objects.filter(resource=row).exists()
    assert auth_client.post(path, {'action': 'vote', 'resource_id': row.pk, 'vote': -1}, format='json').status_code == 200
    # Repeating one user's downvote must not inflate the aggregate.
    assert auth_client.post(path, {'action': 'vote', 'resource_id': row.pk, 'vote': -1}, format='json').data['downvotes'] == 1
    voter = get_user_model().objects.create_user(username='resource_second_voter')
    # Shared system trees are visible to both voters.
    tree.created_by = None
    tree.save(update_fields=('created_by',))
    auth_client.force_authenticate(user=voter)
    response = auth_client.post(path, {'action': 'vote', 'resource_id': row.pk, 'vote': -1}, format='json')
    assert response.status_code == 200 and response.data['downvotes'] == 2
    row.refresh_from_db()
    index.refresh_from_db()
    assert row.is_dismissed and index.is_disabled and index.downvotes == 2
    assert row.pk not in {item['id'] for item in auth_client.get(path).data['resources']}
    # A voter can undo feedback even after the resource disappears from the visible list.
    response = auth_client.post(path, {'action': 'vote', 'resource_id': row.pk, 'vote': 0}, format='json')
    assert response.status_code == 200 and response.data['user_vote'] == 0


@override_settings(ROOT_URLCONF='knowledge_builder.urls')
@pytest.mark.parametrize('payload', [
    {'resource_id': 0, 'vote': 1}, {'resource_id': -1, 'vote': 1},
    {'resource_id': 'oops', 'vote': 1}, {'resource_id': 1, 'vote': 2},
    {'resource_id': 1, 'vote': True}, {'resource_id': 1, 'vote': 1.5},
])
def test_resource_vote_rejects_invalid_values(tree, auth_client, payload):
    path = f'/{tree.pk}/blocks/{tree.blocks.first().pk}/resources/'
    assert auth_client.post(path, {'action': 'vote', **payload}, format='json').status_code == 400


@override_settings(ROOT_URLCONF='knowledge_builder.urls', UNIMIND_PUBLIC_ASSET_EDITION='cn')
def test_auto_discover_api_contract_and_summary_aliases(tree, user, auth_client, monkeypatch):
    from knowledge_builder import public_asset_discovery as discovery
    row = models.BlockResource.objects.create(build=tree, block=tree.blocks.first(),
        title='极限定义', url='https://oi-wiki.org/math/calculus/limit/', asset_track='wiki', origin='auto')
    models.BlockResourceFeedback.objects.create(resource=row, user=user, vote=1)
    calls = []
    def discover(build, user=None, request=None):
        calls.append((build.pk, user.pk, request is not None))
        return dict(mounted_count=1, discovered_assets_count=1, reused_concept_count=0,
                    mounted_summary={'spine_count': 0, 'spotlight_count': 0, 'wiki_count': 1}, resources=[row])
    monkeypatch.setattr(discovery, 'auto_discover_and_mount_public_assets', discover)
    path = f'/{tree.pk}/public-assets/'
    response = auth_client.post(path, {'action': 'auto_discover'}, format='json')
    assert response.status_code == 200
    assert calls == [(tree.pk, user.pk, True)]
    assert response.data['mounted_count'] == response.data['discovered_assets_count'] == 1
    assert response.data['reused_concept_count'] == 0
    assert response.data['asset_track'] == 'spotlight' and response.data['public_asset'] is None
    assert response.data['mounted_summary']['wiki_count'] == 1
    assert response.data['resources'][0]['user_vote'] == 1
    summary = auth_client.get(path).data['mounted_summary']
    for track in ('spine', 'spotlight', 'wiki'):
        assert summary[track] == summary[f'{track}_count']


@override_settings(UNIMIND_PUBLIC_ASSET_EDITION='cn')
def test_auto_discover_persists_reuses_and_disables_concept_index(user, monkeypatch):
    from knowledge_builder import public_asset_discovery as discovery
    subject = '基金从业《私募股权投资基金基础知识》'
    first = make_tree(user, subject=subject, titles=('合格投资者',))
    second = make_tree(user, subject=subject, titles=('合格投资者',))
    third = make_tree(user, subject=subject, titles=('合格投资者',))
    monkeypatch.setattr(discovery, 'auto_mount_public_assets', lambda *args, **kwargs: [])
    monkeypatch.setattr('knowledge_builder.block_study.auto_mount_internal_resources', lambda *args, **kwargs: [])
    candidate = dict(title='私募基金合格投资者认定条件',
        url='https://www.csrc.gov.cn/rules/qualified-investor',
        summary='私募股权投资基金合格投资者定义、认定条件与资产要求',
        authority=3, rerank_score=0.95, provider='deepseek', date='2025-01-01', asset_track='wiki')
    searches = []
    def search(query, **kwargs):
        searches.append(query)
        return [dict(candidate)]
    monkeypatch.setattr(discovery, 'search_public_web', search)
    discovery.auto_discover_and_mount_public_assets(first)
    assert searches and first.block_resources.exists()
    asset = models.PublicAssetCatalog.objects.get(url=candidate['url'])
    alignment = models.ConceptAssetIndex.objects.get(public_asset=asset, concept_name='合格投资者')
    assert alignment.quality_score > 0 and not alignment.is_disabled
    counts = (models.PublicAssetCatalog.objects.count(), first.block_resources.count(), models.ConceptAssetIndex.objects.count())
    discovery.auto_discover_and_mount_public_assets(first)
    assert counts == (models.PublicAssetCatalog.objects.count(), first.block_resources.count(), models.ConceptAssetIndex.objects.count())
    monkeypatch.setattr(discovery, 'search_public_web', lambda *args, **kwargs: [])
    reused = discovery.auto_discover_and_mount_public_assets(second)
    assert reused['reused_concept_count'] >= 1
    assert second.block_resources.filter(public_asset=asset, origin='auto', match_method='concept_index').exists()
    alignment.is_disabled = True
    alignment.save(update_fields=('is_disabled',))
    discovery.auto_discover_and_mount_public_assets(third)
    assert not third.block_resources.filter(public_asset=asset).exists()


@override_settings(ROOT_URLCONF='knowledge_builder.urls', UNIMIND_PUBLIC_ASSET_EDITION='cn')
def test_feedback_aggregates_same_concept_across_mounts(tree, user, auth_client):
    asset = catalog(tree)
    index = models.ConceptAssetIndex.objects.create(subject_domain=tree.subject,
        concept_name='极限', public_asset=asset, segment_locator='P1')
    rows = [models.BlockResource.objects.create(build=tree, block=block, public_asset=asset,
        title=asset.title, url=asset.url, source_kind='bilibili', origin='auto', locator='P1')
        for block in tree.blocks.all()[:2]]
    for row in rows:
        path = f'/{tree.pk}/blocks/{row.block_id}/resources/'
        assert auth_client.post(path, {'action': 'vote', 'resource_id': row.pk, 'vote': -1}, format='json').status_code == 200
    index.refresh_from_db()
    assert index.downvotes == 2 and index.is_disabled
    assert all(not models.BlockResource.objects.get(pk=row.pk).is_dismissed for row in rows)


@override_settings(ROOT_URLCONF='knowledge_builder.urls', UNIMIND_PUBLIC_ASSET_EDITION='cn')
def test_vote_respects_build_block_and_library_visibility(tree, user, auth_client):
    block, other_block = list(tree.blocks.all())[:2]
    stranger = get_user_model().objects.create_user(username='private_resource_owner')
    private_tree = make_tree(stranger)
    row = models.BlockResource.objects.create(build=tree, block=block,
        title='公开解释', url='https://oi-wiki.org/math/calculus/limit/')
    private_library = models.BlockResource.objects.create(build=tree, block=block,
        title='他人资料', url='https://example.cn/private', source_kind='library', created_by=stranger)
    payload = {'action': 'vote', 'resource_id': row.pk, 'vote': 1}
    assert auth_client.post(f'/{tree.pk}/blocks/{other_block.pk}/resources/', payload, format='json').status_code == 404
    assert auth_client.post(f'/{private_tree.pk}/blocks/{private_tree.blocks.first().pk}/resources/', payload, format='json').status_code == 404
    payload['resource_id'] = private_library.pk
    assert auth_client.post(f'/{tree.pk}/blocks/{block.pk}/resources/', payload, format='json').status_code == 404
    assert not models.BlockResourceFeedback.objects.exists()


@override_settings(UNIMIND_PUBLIC_ASSET_EDITION='cn')
def test_auto_discovery_caps_tracks_and_never_restores_dismissed_resource(user, monkeypatch):
    from knowledge_builder import public_asset_discovery as discovery
    build = make_tree(user, subject='私募股权投资基金', titles=('合格投资者',))
    build.atoms.update(goal_type='机制辨析')
    monkeypatch.setattr(discovery, 'auto_mount_public_assets', lambda *args, **kwargs: [])
    monkeypatch.setattr('knowledge_builder.block_study.auto_mount_internal_resources', lambda *args, **kwargs: [])
    def search(query, **kwargs):
        wiki = '定义 法规 权威' in query or 'site:amac.org.cn' in query
        host = 'www.csrc.gov.cn' if wiki else 'open-course.cn'
        return [dict(title=f'私募股权合格投资者定义详解 {index}',
            summary='合格投资者认定条件、资产要求与案例讲解', provider='deepseek',
            url=f'https://{host}/investor/{index}', authority=3 if wiki else 1)
            for index in range(6)]
    monkeypatch.setattr(discovery, 'search_public_web', search)
    discovery.auto_discover_and_mount_public_assets(build)
    assert build.block_resources.filter(asset_track='spotlight').count() == 3
    assert build.block_resources.filter(asset_track='wiki').count() == 2
    rejected = build.block_resources.filter(asset_track='spotlight').first()
    rejected.is_dismissed = True
    rejected.save(update_fields=('is_dismissed',))
    discovery.auto_discover_and_mount_public_assets(build)
    rejected.refresh_from_db()
    assert rejected.is_dismissed
    assert build.block_resources.filter(url=rejected.url).count() == 1
    assert build.block_resources.filter(asset_track='spotlight', is_dismissed=False).count() <= 3


@pytest.mark.parametrize('title,track', [
    ('【基金法规】第二章 基金募集', 'spine'),
    ('【基金基础】第三章 股权投资基金设立', 'spotlight'),
    ('【基金法律法规】合格投资者认定', 'wiki'),
    ('《证券投资基金基础知识》基金募集与设立', 'spotlight'),
])
def test_live_regression_wrong_exam_episode_cannot_borrow_series_summary(title, track):
    from knowledge_builder.public_asset_discovery import evaluate_candidate_quality
    # A mixed-subject playlist description must never override this episode's subject.
    candidate = dict(title=title, asset_track=track,
        url='https://www.bilibili.com/video/BV1mixedsubject?p=4',
        summary='基金从业科目三 私募股权投资基金基础知识 合格投资者 基金募集 股权投资基金设立')
    assert evaluate_candidate_quality(candidate, '基金从业《私募股权投资基金基础知识》',
        ['基金募集', '股权投资基金设立', '合格投资者']) == 0


@pytest.mark.parametrize('url,title,summary', [
    ('https://www.renrendoc.com/paper/123.html', '私募股权投资基金募集复习资料', '付费下载全文'),
    ('https://www.100xuexi.com/Ebook/123.html', '私募股权投资基金募集教材辅导', '购买本书扫码阅读'),
    ('https://www.mayizhixue.com/course/123', '私募股权投资基金募集课程介绍', '报班购买课程'),
    ('https://bkso.baidu.com/item/基金募集', '基金募集 - 百度百科', '私募股权投资基金募集定义'),
    ('https://open-course.cn/course/intro', '私募股权投资基金课程简介', '基金募集 合格投资者 点击购买课程'),
    ('https://open-course.cn/chapter/1', '证券市场技术分析与K线交易', '私募股权投资基金募集 合格投资者认定条件'),
])
def test_live_regression_rejects_paid_catalog_mirror_and_title_mismatch(url, title, summary):
    from knowledge_builder.public_asset_discovery import evaluate_candidate_quality
    assert evaluate_candidate_quality(dict(url=url, title=title, summary=summary, asset_track='spotlight'),
        '基金从业《私募股权投资基金基础知识》', ['基金募集', '合格投资者认定条件']) == 0


@override_settings(UNIMIND_PUBLIC_ASSET_EDITION='cn')
def test_live_regression_spine_episode_targets_block_instead_of_shared_subject(user, monkeypatch):
    from knowledge_builder import public_asset_discovery as discovery
    titles = ('私募基金概述', '基金组织形式', '基金募集', '基金设立', '投资策略',
              '尽职调查', '投资决策', '基金估值', '投后管理')
    build = make_tree(user, subject='基金从业《私募股权投资基金基础知识》', titles=titles)
    build.atoms.update(goal_type='机制辨析')
    monkeypatch.setattr(discovery, 'auto_mount_public_assets', lambda *args, **kwargs: [])
    monkeypatch.setattr('knowledge_builder.block_study.auto_mount_internal_resources', lambda *args, **kwargs: [])
    base = 'https://www.bilibili.com/video/BV1placement'
    candidate = dict(title='私募股权投资基金全套精讲', url=base, provider='deepseek',
                     summary='私募股权投资基金基础知识全套课程')
    def search(query, **kwargs):
        return [dict(candidate)] if '全套' in query or '课程 bilibili' in query else []
    monkeypatch.setattr(discovery, 'search_public_web', search)
    def metadata(url, **kwargs):
        return {'code': 0, 'data': {'title': candidate['title'], 'desc': candidate['summary'],
            'pages': [{'page': p, 'part': title, 'duration': 900}
                      for p, title in enumerate(('【私募股权】基金募集', '【私募股权】基金设立',
                                                 '【私募股权】投后管理', '【基金法规】基金募集'), 1)]}}
    monkeypatch.setattr(discovery.httpx, 'get', metadata)
    discovery.auto_discover_and_mount_public_assets(build)
    rows = list(build.block_resources.filter(asset_track='spine').order_by('locator'))
    assert [(row.locator, row.block.code) for row in rows] == [('P1', 'B3'), ('P2', 'B4'), ('P3', 'B9')]
    assert all(row.atom.name == row.block.short_title for row in rows)
    assert not build.block_resources.filter(locator='P4').exists()


@override_settings(UNIMIND_PUBLIC_ASSET_EDITION='cn')
def test_live_regression_targeted_spotlight_extracts_matching_page_from_series(user, monkeypatch):
    from knowledge_builder import public_asset_discovery as discovery
    build = make_tree(user, subject='私募股权投资基金', titles=('合格投资者',))
    build.atoms.update(goal_type='机制辨析')
    block = build.blocks.get()
    # The tree already has its one spine; a second series can still supply a targeted lecture.
    existing = catalog(build, title='私募股权主线课', asset_track='spine')
    models.BlockResource.objects.create(build=build, block=block, public_asset=existing,
        title=existing.title, url=existing.url, asset_track='spine', origin='auto')
    monkeypatch.setattr(discovery, 'auto_mount_public_assets', lambda *args, **kwargs: [])
    monkeypatch.setattr('knowledge_builder.block_study.auto_mount_internal_resources', lambda *args, **kwargs: [])
    base = 'https://www.bilibili.com/video/BV1targeted'
    candidate = dict(title='私募股权投资基金精讲', summary='私募股权全套精讲', url=base, provider='deepseek')
    monkeypatch.setattr(discovery, 'search_public_web',
        lambda query, **kwargs: [dict(candidate)] if '精讲 bilibili' in query or 'site:bilibili.com' in query else [])
    def metadata(url, **kwargs):
        return {'code': 0, 'data': {'title': candidate['title'], 'desc': candidate['summary'],
            'pages': [{'page': p, 'part': title, 'duration': 900}
                      for p, title in enumerate(('基金估值', '投后管理', '私募基金合格投资者认定条件'), 1)]}}
    monkeypatch.setattr(discovery.httpx, 'get', metadata)
    discovery.auto_discover_and_mount_public_assets(build)
    rows = list(build.block_resources.filter(asset_track='spotlight'))
    assert rows and all(row.url == base + '?p=3' and row.locator == 'P3' for row in rows)
    assert all(row.atom.name == '合格投资者' for row in rows)
    assert build.block_resources.filter(asset_track='spine').count() == 1


@pytest.mark.parametrize('title,summary', [
    ('私募基金信息披露管理系统产品宣传', '信息披露管理系统为私募股权基金提供服务'),
    ('公募REITs信息披露规则解析', '私募股权投资基金 信息披露 监管规定'),
    ('关于基金考试一切与应知应会考核宣传', '私募股权基金 信息披露 考试培训'),
    ('2020私募股权投资基金信息披露精讲', '私募基金信息披露与监管办法'),
])
def test_final_quality_regression_rejects_products_cross_domain_promos_and_stale_law(title, summary):
    from knowledge_builder.public_asset_discovery import evaluate_candidate_quality
    candidate = dict(title=title, summary=summary, date='2026-11-18',
        url='https://www.bilibili.com/video/BV1finalquality', asset_track='spotlight')
    assert evaluate_candidate_quality(candidate, '基金从业《私募股权投资基金基础知识》',
                                      ['信息披露', '私募基金信息披露要求']) == 0


def test_yuanbao_optional_credentials_signed_request_and_json_encoded_pages(monkeypatch):
    from knowledge_builder import public_asset_discovery as discovery
    calls = []
    def post(url, **kwargs):
        calls.append((url, kwargs))
        assert url == 'https://wsa.tencentcloudapi.com'
        assert json.loads(kwargs['content']) == {'Query': '合格投资者', 'Mode': 2}
        headers = kwargs['headers']
        assert headers['X-TC-Action'] == 'SearchPro'
        assert headers['X-TC-Version'] == '2025-05-08'
        assert headers['X-TC-Timestamp'] == '1735689600'
        assert headers['Host'] == 'wsa.tencentcloudapi.com'
        assert headers['Authorization'].startswith('TC3-HMAC-SHA256 Credential=test-secret-id/2025-01-01/wsa/tc3_request, ')
        assert 'SignedHeaders=content-type;host, Signature=' in headers['Authorization']
        signature = headers['Authorization'].rsplit('Signature=', 1)[-1]
        assert len(signature) == 64 and all(char in '0123456789abcdef' for char in signature)
        return {'Response': {'Pages': json.dumps([{
            'title': '私募基金合格投资者', 'url': 'https://www.amac.org.cn/rules/investor',
            'passage': '合格投资者认定条件', 'site': '中国证券投资基金业协会', 'score': 0.92,
        }], ensure_ascii=False)}}
    monkeypatch.setattr(discovery.httpx, 'post', post)
    monkeypatch.setattr(discovery.time, 'time', lambda: 1735689600)
    monkeypatch.delenv('TENCENT_WSA_SECRET_ID', raising=False)
    monkeypatch.delenv('TENCENT_WSA_SECRET_KEY', raising=False)
    provider = discovery.YuanbaoSearchProvider()
    assert provider.search('合格投资者') == [] and not calls
    monkeypatch.setenv('TENCENT_WSA_SECRET_ID', 'test-secret-id')
    assert provider.search('合格投资者') == [] and not calls
    monkeypatch.setenv('TENCENT_WSA_SECRET_KEY', 'test-secret-key')
    results = provider.search('合格投资者')
    assert len(calls) == 1 and len(results) == 1
    assert results[0]['summary'] == '合格投资者认定条件'
    assert results[0]['site_name'] == '中国证券投资基金业协会'
    assert results[0]['rerank_score'] == 0.92 and results[0]['provider'] == 'yuanbao'


@pytest.mark.parametrize('title,summary,labels', [
    ('私募基金管理人登记须知', '（2017年12月15日更新）私募基金内部控制和监管规定', ['内部控制']),
    ('中国证券投资基金业协会', '本书为私募股权基金课程推荐读物，介绍基金退出方式', ['退出']),
])
def test_wiki_rejects_explicitly_obsolete_revision_and_book_recommendation(title, summary, labels):
    from knowledge_builder.public_asset_discovery import evaluate_candidate_quality
    assert evaluate_candidate_quality(dict(title=title, summary=summary,
        date='2026-11-18', url='https://www.amac.org.cn/investread/article.html', asset_track='wiki'),
        '私募股权投资基金', labels) == 0


@pytest.mark.parametrize('goal,cognitive,minutes,expected', [
    ('概念辨析', '理解', 4, ('L1', '基础速通')),
    ('概念', '记忆', 4, ('L1', '基础速通')),
    ('', '理解', 4, ('L1', '基础速通')),
    (' 概念辨析 ', ' 理解 ', 8, ('L1', '基础速通')),
    ('实操计算', '理解', 4, ('L3', '硬核攻坚')),
    ('综合应用', '记忆', 4, ('L3', '硬核攻坚')),
    ('概念辨析', '评价', 4, ('L3', '硬核攻坚')),
    ('概念', '创造', 4, ('L3', '硬核攻坚')),
    ('机制辨析', '分析', 6, ('L3', '硬核攻坚')),
    ('机制辨析', '分析', 5, ('L2', '机制辨析')),
    ('概念辨析', '分析', 6, ('L2', '机制辨析')),
    ('机制', '理解', 4, ('L2', '机制辨析')),
    (None, None, None, ('L2', '机制辨析')),
])
def test_compute_atom_difficulty_rules(goal, cognitive, minutes, expected):
    from knowledge_builder.public_asset_service import compute_atom_difficulty
    atom = SimpleNamespace(goal_type=goal, cognitive_level=cognitive, granularity_minutes=minutes)
    assert compute_atom_difficulty(atom) == expected


@override_settings(UNIMIND_PUBLIC_ASSET_EDITION='cn')
@pytest.mark.parametrize('track', ['spotlight', 'spine'])
def test_auto_discovery_videos_target_only_matching_difficult_atoms(user, monkeypatch, track):
    from knowledge_builder import public_asset_discovery as discovery

    build = make_tree(user, subject='私募股权投资基金', titles=('合格投资者',))
    block = build.blocks.get()
    basic = build.atoms.get()
    basic.goal_type = '概念辨析'
    basic.save(update_fields=['goal_type'])
    step = block.steps.get()
    difficult = []
    for index, (name, goal) in enumerate((('收益分配机制', '机制辨析'), ('基金估值计算', '实操计算')), 2):
        atom = models.TreeAtomPoint.objects.create(
            build=build, module=basic.module, code=f'A{index}', name=name,
            goal_statement=f'掌握{name}', goal_type=goal, cognitive_level='分析',
            granularity_minutes=4, key_elements=[name])
        models.BlockStepAtom.objects.create(step=step, atom=atom, membership_type='core', position=index)
        difficult.append(atom)
    monkeypatch.setattr(discovery, 'auto_mount_public_assets', lambda *args, **kwargs: [])
    monkeypatch.setattr('knowledge_builder.block_study.auto_mount_internal_resources', lambda *args, **kwargs: [])
    videos = [dict(title=f'私募股权投资基金{name}详解', summary=f'{name}的定义和适用条件',
                   url=f'https://www.bilibili.com/video/BV1tier{index}',
                   source_kind='bilibili', asset_track='spotlight', provider='deepseek')
              for index, name in enumerate((basic.name, *(atom.name for atom in difficult)), 1)]
    wiki = dict(title='私募股权基金合格投资者定义', summary='合格投资者认定条件及资产要求',
                url='https://www.csrc.gov.cn/rules/qualified-investor',
                source_kind='web', asset_track='wiki', authority=3, provider='deepseek')
    if track == 'spine':
        series = dict(title='私募股权投资基金全套精讲', summary='私募股权投资基金完整课程',
                      url='https://www.bilibili.com/video/BV1tierSeries',
                      source_kind='bilibili', asset_track='spine', provider='deepseek',
                      segments=[dict(index=index, title=video['title'], summary=video['summary'],
                                     locator=f'P{index}', url=f"https://www.bilibili.com/video/BV1tierSeries?p={index}")
                                for index, video in enumerate(videos, 1)])
        candidates = [series, wiki]
    else:
        candidates = [*videos, wiki]
    monkeypatch.setattr(discovery, 'search_public_web', lambda *args, **kwargs: candidates)
    monkeypatch.setattr(discovery, 'enrich_bilibili_candidate', lambda row: row)

    discovery.auto_discover_and_mount_public_assets(build)

    mounted = list(block.resources.filter(asset_track=track))
    assert mounted and {row.atom_id for row in mounted} == {atom.pk for atom in difficult}
    assert not block.resources.filter(source_kind='bilibili', atom=basic).exists()
    basic_video_url = series['segments'][0]['url'] if track == 'spine' else videos[0]['url']
    assert not block.resources.filter(url=basic_video_url).exists()
    assert block.resources.filter(asset_track='wiki', atom=basic, url=wiki['url']).exists()


@override_settings(UNIMIND_PUBLIC_ASSET_EDITION='cn')
def test_auto_discovery_rejects_l1_concept_video_indexes_and_seed_mounts(tree, user, monkeypatch):
    from knowledge_builder import public_asset_discovery as discovery

    atom = tree.atoms.get(name='极限')
    video = catalog(tree)
    seed = catalog(tree, title='导数精讲', description='导数的定义和适用条件',
                   topic_keywords=['导数'], url='https://www.bilibili.com/video/BV1tierSeed')
    models.ConceptAssetIndex.objects.create(
        subject_domain=discovery.subject_domain(tree.subject), concept_name=atom.name,
        public_asset=video, segment_title=video.title, segment_url=video.url,
        asset_track='spotlight', quality_score=10)
    monkeypatch.setattr('knowledge_builder.block_study.auto_mount_internal_resources', lambda *args, **kwargs: [])
    monkeypatch.setattr(discovery, 'search_public_web', lambda *args, **kwargs: [])
    discovery.auto_discover_and_mount_public_assets(tree, user=user)
    assert not tree.block_resources.filter(public_asset_id__in=[video.pk, seed.pk]).exists()
