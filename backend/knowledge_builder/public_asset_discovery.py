"""Domestic public search, conservative automatic alignment and reusable concept assets.

Network failures never invent learning resources. Persisted feedback is a tombstone:
rerunning discovery cannot restore dismissed resources or disabled alignments.
"""
import hashlib
import hmac
import json
import logging
import math
import os
import re
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from django.db import transaction

from ai_engine import config
from .models import BlockResource, ConceptAssetIndex, PublicAssetCatalog
from .public_asset_service import (
    _asset_text, _binding, _blocks, _normalized, _score, _text,
    align_and_mount_spine_series, auto_mount_public_assets,
    public_asset_allowed, store_public_asset,
)

logger = logging.getLogger(__name__)
MARKETING = re.compile(r'保过班|包过|押题密卷|加微信|扫码领取|免费领资料|代报名')
PART_MARKETING = re.compile(r'扫码|领取|加微|加群|客服|资料包|免费领|押题密卷|公众号领|网盘|提取码|报名咨询')
NOISE_HOSTS = ('taobao.com', 'tmall.com', 'jd.com', 'zhaopin.com', 'liepin.com', 'boss.com', 'doc88.com', 'docin.com', '100xuexi.com', 'renrendoc.com', 'mayizhixue.com', '51job.com', 'bkso.baidu.com', '163.com', 'kaoyan.com', 'jz.docin.com')


def _number(value, default=0.0):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (ValueError, TypeError):
        return default


def normalize_public_url(url):
    try:
        parts = urlsplit(str(url or '').strip())
        if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.port not in (None, 443):
            return ''
        host = parts.hostname.lower().rstrip('.')
        if host == 'bilibili.com' or host.endswith('.bilibili.com'):
            match = re.search(r'/video/(BV[a-zA-Z0-9]+)', parts.path)
            if match:
                # Page is retained for concept URLs; search deduplication uses the base.
                page = dict(parse_qsl(parts.query)).get('p', '')
                suffix = '?p=' + str(int(page)) if page.isdigit() and int(page) > 0 else ''
                return 'https://www.bilibili.com/video/' + match.group(1) + suffix
        query = [(key, val) for key, val in parse_qsl(parts.query) if not key.lower().startswith(('utm_', 'spm', 'from', 'share_'))]
        return urlunsplit(('https', host, parts.path or '/', urlencode(sorted(query)), ''))
    except (TypeError, ValueError):
        return ''


def _rows(payload):
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            return []
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ('results', 'search_results', 'SearchResults', 'Results', 'WebPages', 'web_pages', 'Pages', 'pages', 'data', 'Response'):
        value = payload.get(key)
        if isinstance(value, (list, dict, str)):
            result = _rows(value)
            if result:
                return result
    return []


def _normalize_result(item, provider):
    if isinstance(item, str):
        try:
            item = json.loads(item)
        except ValueError:
            return None
    if not isinstance(item, dict):
        return None
    url = normalize_public_url(item.get('url') or item.get('link') or item.get('Url'))
    if not url:
        return None
    return dict(title=str(item.get('title') or item.get('Title') or '')[:200], url=url,
                summary=str(item.get('summary') or item.get('snippet') or item.get('passage') or item.get('content') or item.get('Content') or '')[:600],
                site_name=str(item.get('site_name') or item.get('site') or item.get('SiteName') or ''),
                authority=int(_number(item.get('authority'), 1)), rerank_score=_number(item.get('rerank_score', item.get('score'))),
                date=item.get('date') or item.get('Date') or '', provider=provider)


class SearchProvider(ABC):
    @abstractmethod
    def search(self, query):
        """Return normalized public results, or an empty list on provider failure."""


class DeepSeekSearchProvider(SearchProvider):
    def __init__(self, fetcher=None):
        self.fetcher = fetcher

    def _post(self, endpoint, payload):
        key = config._get_api_key()
        if not key:
            return {}
        try:
            response = (self.fetcher or httpx.post)(
                'https://api.deepseek.com/v1/tools/' + endpoint,
                headers={'Authorization': 'Bearer ' + key}, json=payload, timeout=15)
            if isinstance(response, (dict, list)):
                return response
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError, OSError) as exc:
            # Avoid response/request repr: it may contain credentials.
            logger.warning('DeepSeek %s unavailable (%s)', endpoint, type(exc).__name__)
            return {}

    def search(self, query):
        return [result for item in _rows(self._post('search', {'query': query}))
                if (result := _normalize_result(item, 'deepseek'))]

    def fetch(self, url):
        return self._post('fetch', {'url': url})


class YuanbaoSearchProvider(SearchProvider):
    def __init__(self, fetcher=None):
        self.fetcher = fetcher

    def search(self, query):
        secret_id, secret_key = os.getenv('TENCENT_WSA_SECRET_ID'), os.getenv('TENCENT_WSA_SECRET_KEY')
        if not secret_id or not secret_key:
            return []
        timestamp = int(time.time())
        date = datetime.fromtimestamp(timestamp, timezone.utc).strftime('%Y-%m-%d')
        payload = json.dumps({'Query': query, 'Mode': 2}, ensure_ascii=False, separators=(',', ':'))
        digest = lambda data: hashlib.sha256(data.encode()).hexdigest()
        canonical = 'POST\n/\n\ncontent-type:application/json; charset=utf-8\nhost:wsa.tencentcloudapi.com\n\ncontent-type;host\n' + digest(payload)
        scope = date + '/wsa/tc3_request'
        string_to_sign = 'TC3-HMAC-SHA256\n' + str(timestamp) + '\n' + scope + '\n' + digest(canonical)
        sign = lambda key, data: hmac.new(key, data.encode(), hashlib.sha256).digest()
        key = sign(sign(sign(('TC3' + secret_key).encode(), date), 'wsa'), 'tc3_request')
        signature = hmac.new(key, string_to_sign.encode(), hashlib.sha256).hexdigest()
        headers = {'Content-Type': 'application/json; charset=utf-8', 'Host': 'wsa.tencentcloudapi.com',
                   'X-TC-Action': 'SearchPro', 'X-TC-Version': '2025-05-08', 'X-TC-Timestamp': str(timestamp),
                   'Authorization': f'TC3-HMAC-SHA256 Credential={secret_id}/{scope}, SignedHeaders=content-type;host, Signature={signature}'}
        try:
            response = (self.fetcher or httpx.post)('https://wsa.tencentcloudapi.com', headers=headers, content=payload.encode(), timeout=15)
            if not isinstance(response, dict):
                response.raise_for_status()
                response = response.json()
            return [result for item in _rows(response) if (result := _normalize_result(item, 'yuanbao'))]
        except (httpx.HTTPError, ValueError, OSError) as exc:
            logger.warning('Yuanbao search unavailable (%s)', type(exc).__name__)
            return []


def search_public_web(query, region_pref='cn', limit=8, fetcher=None):
    found = {}
    for provider in (DeepSeekSearchProvider(fetcher), YuanbaoSearchProvider(fetcher)):
        for row in provider.search(query):
            url = normalize_public_url(row['url'])
            if url and public_asset_allowed({'url': url}, region_pref):
                previous = found.get(url)
                if previous is None or row['rerank_score'] > previous['rerank_score']:
                    found[url] = dict(row, url=url)
    return sorted(found.values(), key=lambda row: -row['rerank_score'])[:max(0, limit)]


def enrich_bilibili_candidate(candidate, fetcher=None):
    result = dict(candidate)
    url = normalize_public_url(result.get('url'))
    if not url:
        return result
    result['url'] = url
    host = urlsplit(url).hostname or ''
    match = re.search(r'/video/(BV[a-zA-Z0-9]+)', urlsplit(url).path)
    if not (host == 'bilibili.com' or host.endswith('.bilibili.com')) or not match:
        return result
    base_url = 'https://www.bilibili.com/video/' + match.group(1)
    result.update(url=base_url, source_kind='bilibili', asset_track='spotlight')
    try:
        response = (fetcher or httpx.get)('https://api.bilibili.com/x/web-interface/view', params={'bvid': match.group(1)}, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if not isinstance(response, dict):
            response.raise_for_status()
            response = response.json()
        data = response.get('data')
        if response.get('code') != 0 or not isinstance(data, dict):
            return result
        result.update(title=data.get('title') or result.get('title', ''),
                      summary=data.get('desc') or result.get('summary', ''), pubdate=data.get('pubdate'),
                      view=data.get('stat', {}).get('view', 0), favorite=data.get('stat', {}).get('favorite', 0))
        pages = []
        for page in data.get('pages') or []:
            duration = _number(page.get('duration'))
            title = str(page.get('part') or '')
            if (0 < duration < 90) or PART_MARKETING.search(title):
                continue
            number = int(_number(page.get('page'), 1))
            pages.append(dict(index=number, title=title[:200], url=f'{base_url}?p={number}',
                              locator=f'P{number}', duration=duration, summary=title))
        result['metadata_verified'] = True
        result['pages'] = pages
        if not pages:
            result['quality_rejected'] = True
        elif len(pages) >= 3:
            result.update(asset_track='spine', segments=pages)
        else:
            # Never link to a removed intro P1 when the useful episode is P2.
            result.update(url=pages[0]['url'], locator=pages[0]['locator'], segments=[],
                          summary=f"{pages[0]['title']} {result.get('summary', '')}")
    except (httpx.HTTPError, ValueError, OSError, TypeError) as exc:
        logger.info('Bilibili metadata unavailable (%s)', type(exc).__name__)
    return result


def _subject_terms(subject):
    if '私募' in subject or '股权' in subject:
        return ['私募股权', '股权投资', '私募基金', '基金从业']
    return [term for term in re.split(r'[《》\s，,、（）()]+', subject) if len(term) >= 2]


def subject_domain(subject):
    # Stable across introductory/advanced trees for the same discipline.
    if '私募' in subject or '股权' in subject:
        return '私募股权投资基金'
    return _normalized(subject)[:120]


# These are professional concepts rather than shared exam/domain boilerplate.
# Match block titles first so an incidental atom keyword cannot dominate alignment.
_PROFESSIONAL_TERMS = (
    '合格投资者', '募集', '推介', '组织形式', '资金来源', '合伙型', '公司型', '契约型',
    '创业投资', '政府引导基金', '母基金', '设立', '备案', '登记', '托管', '外包',
    '内部控制', '合规风控', '风险控制', '风险管理', '尽职调查', '尽调', '投决', '投资决策', '项目开发',
    '估值', '净值', '核算', '投后管理', '增值服务', '退出', '瀑布', '分配',
    '信息披露', '监管体制', '行业自律', '自律管理', '职业道德', '违规责任', '法律责任',
)
_ALIASES = {'尽调': ['尽职调查'], '尽职调查': ['尽调'], '投决': ['投资决策'],
            '监管体制': ['监管机构', '监管部门'], '行业自律': ['自律管理', '基金业协会'],
            '合规风控': ['风险控制', '风险管理'], '组织形式': ['合伙型', '公司型', '契约型'],
            '职业道德': ['廉洁从业', '受托人义务', '诚信义务'],
            '违规责任': ['法律责任', '违法违规', '自律处分', '行政责任', '刑事责任', '警示函'],
            '瀑布': ['收益分配']}


def _specific_terms(labels):
    labels = [_text(label) for label in labels if _text(label)]
    for label in labels:
        terms = [term for term in _PROFESSIONAL_TERMS if term in label]
        if terms:
            return list(dict.fromkeys(terms + [alias for term in terms for alias in _ALIASES.get(term, [])]))
        if ('界定' in label or '辨析' in label) and ('私募股权' in label or '股权基金' in label):
            return ['股权投资基金概念', '股权投资基金的概念', '股权投资基金特点', '股权投资基金的特点', '股权投资基金定义', '私募股权基金概念', '股权投资基金概述', '股权投资基金基础']
    # Generic disciplines: retain actual label phrases while discarding framing words.
    result = []
    for label in labels[:6]:
        label = re.split(r'如何|怎么|怎样|是什么|的定义|定义与|与|及|、', label)[0]
        label = re.sub(r'^(理解|掌握|认识|了解)|[？?。]', '', label).strip()
        if 2 <= len(label) <= 18 and label not in ('基金', '投资', '管理', '方式', '机制', '学习', '课程'):
            result.append(label)
    return list(dict.fromkeys(result))


def _specific_score(text, labels):
    normalized = _normalized(text)
    terms = _specific_terms(labels)
    return sum(10 + len(term) for term in terms if _normalized(term) in normalized)


def _official_wiki_host(host):
    return (host == 'gov.cn' or host.endswith('.gov.cn') or host.endswith('.edu.cn') or
            any(host == domain or host.endswith('.' + domain) for domain in
                ('amac.org.cn', 'oi-wiki.org', 'hello-algo.com', 'pbc.gov.cn')))


def _trusted_wiki_url(url):
    parts = urlsplit(url)
    return _official_wiki_host(parts.hostname or '') or (
        parts.hostname in ('github.com', 'gitee.com') and
        any(token in parts.path for token in ('/wiki', '/blob/', '/tree/')))


def _other_subject_part(title, subject=''):
    tagged = re.search(r'【[^】]*(?:基金法规|基金基础|科目一|科目二)[^】]*】|\[(?:基金法规|基金基础|科目一|科目二)\]', title)
    return bool(tagged or (re.search(r'基金法律法规|证券投资基金基础知识', title) and not re.search(r'私募|股权|科目三', title)))


def evaluate_candidate_quality(candidate, subject, target_labels):
    url = normalize_public_url(candidate.get('url'))
    if not url or not public_asset_allowed(dict(candidate, url=url), 'cn') or candidate.get('quality_rejected'):
        return 0.0
    host = urlsplit(url).hostname or ''
    if host == 'peixun.amac.org.cn' or ('amac.org.cn' in host and '/learn' in urlsplit(url).path):
        return 0.0
    if any(host == domain or host.endswith('.' + domain) for domain in NOISE_HOSTS):
        return 0.0
    title = _text(candidate.get('title'))
    financial = '私募' in subject or '股权' in subject
    if financial and '管理系统' in title:
        return 0.0
    if financial and re.search(r'REITs?', title, re.I) and not re.search(r'私募|股权', title):
        return 0.0
    if re.search(r'考试一切|应知应会考核|备考攻略', title):
        return 0.0
    if '模考卷' in title and not re.search(r'解析|讲解|讲评', title):
        return 0.0
    if re.search(r'课程介绍|课程简介|课程目录|课程大纲|课程推荐|购买课程|报班|网校课程|课程套餐|模拟试卷|真题试卷|题库下载|百度百科|征求意见稿|培训平台|课程中心|系统软件|软件产品', title):
        return 0.0
    text = ' '.join((title, _text(candidate.get('summary') or candidate.get('description')), _text(candidate.get('segments'))))
    if MARKETING.search(text) and not re.search(r'概念|定义|原理|案例|解析|讲解|法律|条例', title):
        return 0.0
    if re.search(r'招聘|求职|二手交易|购买下载|付费下载|灌水', title):
        return 0.0
    track = candidate.get('asset_track', 'spotlight')
    if track == 'wiki' and re.search(r'本书|推荐读物|书籍推荐', text):
        return 0.0
    if track == 'wiki' and not _trusted_wiki_url(url):
        return 0.0
    terms = _subject_terms(subject)
    subject_hit = any(term in text for term in terms)
    labels = [_text(label) for label in target_labels if _text(label)]
    exact_hit = any(len(_normalized(label)) >= 2 and _normalized(label) in _normalized(text) for label in labels)
    relevance = _score(text, labels)
    other_subject = ('私募' in subject or '股权' in subject) and re.search(r'基金法律法规|证券投资基金基础知识', title) and not re.search(r'私募|股权', title)
    if ('私募' in subject or '股权' in subject) and _other_subject_part(title):
        return 0.0
    # Broad subject overlap alone does not justify block-level attachment.
    if track == 'spine':
        if not subject_hit or other_subject:
            return 0.0
    elif not _specific_score((title + ' ' + _text(candidate.get('summary') or candidate.get('description'))) if track == 'wiki' else title, labels):
        return 0.0
    years = [int(year) for year in re.findall(r'(?<!\d)(20\d{2})(?!\d)', title + ' ' + str(candidate.get('date', '')))]
    regulatory = bool(re.search(r'法规|法律|考纲|大纲|条例|监管|办法|信息披露|托管|内控|内部控制', text))
    title_years = [int(year) for year in re.findall(r'(?<!\d)(20\d{2})(?!\d)', title)]
    updated_years = [int(year) for year in re.findall(r'(20\d{2})年\d{1,2}月\d{1,2}日更新', text)]
    if regulatory and updated_years and max(updated_years) <= 2019:
        return 0.0
    if regulatory and ((title_years and max(title_years) <= 2019) or (years and max(years) <= 2019)):
        return 0.0
    if regulatory and financial and title_years and max(title_years) <= 2020:
        return 0.0
    authority = _number(candidate.get('authority'), 1)
    official = host == 'gov.cn' or host.endswith('.gov.cn') or host == 'amac.org.cn' or host.endswith('.amac.org.cn')
    score = min(75.0, float(relevance if track == 'spine' else _specific_score(title + ' ' + _text(candidate.get('summary') or candidate.get('description')), labels))) + min(10.0, max(0.0, _number(candidate.get('rerank_score'))) * 10)
    score += 12 if official or authority >= 3 else 0
    score += 5 if any(2023 <= year <= 2026 for year in years) else 0
    score += 8 if subject_hit else 0
    return max(1.0, score)


def _catalog_data(candidate, track=None):
    from .public_asset_resolvers import detect_source_kind
    return dict(title=candidate.get('title', '')[:200], url=candidate['url'],
                source_kind=candidate.get('source_kind') or detect_source_kind(candidate['url']),
                asset_track=track or candidate.get('asset_track', 'spotlight'), region_scope='cn',
                description=_text(candidate.get('summary') or candidate.get('description'))[:10000],
                topic_keywords=candidate.get('topic_keywords', []), segments=candidate.get('segments', []),
                locator=candidate.get('locator', ''))


def _disabled(asset_id, locator):
    return ConceptAssetIndex.objects.filter(public_asset_id=asset_id, segment_locator=locator, is_disabled=True).exists()


@transaction.atomic
def _mount_candidate(build, details, data, asset, score, method, user=None, target_atom=None):
    block = details[0]
    type(block).objects.select_for_update().get(pk=block.pk)
    if _disabled(asset.pk, data.get('locator', '')):
        return None, False
    # Identity excludes creator: repeated invocation by another user must not duplicate.
    existing = block.resources.filter(url=data['url'], locator=data.get('locator', '')).first()
    if existing is not None:
        return (None, False) if existing.is_dismissed else (existing, False)
    track = data['asset_track']
    if track in ('spotlight', 'wiki') and block.resources.filter(origin='auto', asset_track=track, is_dismissed=False).count() >= (3 if track == 'spotlight' else 2):
        return None, False
    if track == 'spine':
        type(build).objects.select_for_update().get(pk=build.pk)
        if build.block_resources.filter(asset_track='spine', is_dismissed=False).exclude(public_asset=asset).exists():
            return None, False
    binding_text = data.get('description') if data.get('locator') else _asset_text(data)
    binding_text = binding_text or data['title']
    if target_atom is None and details[2]:
        ranked = sorted(details[2], key=lambda row: (
            _specific_score(binding_text, [row.atom.name, row.atom.key_elements]),
            _score(binding_text, [row.atom.name])), reverse=True)
        assignment = ranked[0]
        if _specific_score(binding_text, [assignment.atom.name, assignment.atom.key_elements]):
            target_atom = assignment.atom_id
    step, atom = _binding(details, binding_text, target_atom)
    resource = BlockResource.objects.create(build=build, block=block, step=step, atom=atom,
        public_asset=asset, source_kind=data['source_kind'], asset_track=data['asset_track'],
        title=data['title'], url=data['url'], locator=data.get('locator', ''), excerpt=data['description'],
        region_scope='cn', origin='auto', match_method=method, match_score=score,
        pedagogical_role='series_episode' if data['asset_track'] == 'spine' else ('wiki_reference' if data['asset_track'] == 'wiki' else 'concept_intuition'),
        created_by=user if getattr(user, 'is_authenticated', False) else None)
    return resource, True


def _index_resource(resource, details, score):
    if not resource.public_asset_id:
        return
    assignments = details[2]
    # Only record the actually aligned concept; don't claim all concepts in a block.
    atom = resource.atom
    if atom is None:
        ranked = sorted(assignments, key=lambda row: -_score(resource.title + ' ' + resource.excerpt, [row.atom.name, row.atom.key_elements]))
        atom = ranked[0].atom if ranked and _score(resource.title + ' ' + resource.excerpt, [ranked[0].atom.name]) > 0 else None
    if atom is None:
        return
    ConceptAssetIndex.objects.get_or_create(subject_domain=subject_domain(resource.build.subject),
        concept_name=atom.name, public_asset_id=resource.public_asset_id, segment_locator=resource.locator,
        defaults=dict(goal_statement=atom.goal_statement, key_elements=atom.key_elements,
                      segment_title=resource.title, segment_url=resource.url, asset_track=resource.asset_track,
                      pedagogical_role=resource.pedagogical_role, quality_score=score))


def _summary(resources):
    result = {track: sum(row.asset_track == track for row in resources) for track in ('spine', 'spotlight', 'wiki')}
    return result | {track + '_count': value for track, value in result.items()}


def auto_discover_and_mount_public_assets(build, user=None, request=None):
    from .block_study import auto_mount_internal_resources, visible_block_resources
    user = user or build.created_by
    before = set(build.block_resources.values_list('pk', flat=True))
    auto_mount_internal_resources(build)
    auto_mount_public_assets(build)
    details = _blocks(build)
    discovered_ids, reused_ids = set(), set()
    metadata_cache = {}

    def enrich(row):
        url = normalize_public_url(row.get('url'))
        if url not in metadata_cache:
            metadata_cache[url] = enrich_bilibili_candidate(dict(row, url=url))
        return metadata_cache[url]

    def count(block, track):
        return block.resources.filter(origin='auto', asset_track=track, is_dismissed=False).count()

    # Reuse verified concept alignments before any network search.
    spine_resources = build.block_resources.filter(asset_track='spine', is_dismissed=False)
    has_spine = spine_resources.exists()
    spine_asset_id = spine_resources.values_list('public_asset_id', flat=True).first()
    for detail in details:
        names = {assignment.atom.name: assignment.atom_id for assignment in detail[2]}
        indexes = ConceptAssetIndex.objects.filter(subject_domain=subject_domain(build.subject), concept_name__in=names, is_disabled=False).select_related('public_asset').order_by('-quality_score', 'pk')
        for index in indexes:
            if index.asset_track == 'spine':
                if has_spine and spine_asset_id != index.public_asset_id:
                    continue
            elif count(detail[0], index.asset_track) >= (2 if index.asset_track == 'wiki' else 3):
                continue
            data = _catalog_data(dict(title=index.segment_title or index.public_asset.title,
                url=index.segment_url or index.public_asset.url, source_kind=index.public_asset.source_kind,
                summary=f'{index.concept_name} {index.goal_statement} {index.segment_title}', locator=index.segment_locator), index.asset_track)
            if not public_asset_allowed(data, 'cn') or not normalize_public_url(data['url']):
                continue
            resource, created = _mount_candidate(build, detail, data, index.public_asset, index.quality_score, 'concept_index', user, names[index.concept_name])
            if created:
                reused_ids.add(resource.pk)
                if index.asset_track == 'spine':
                    spine_asset_id = index.public_asset_id
                    has_spine = True

    if not build.block_resources.filter(asset_track='spine', is_dismissed=False).exists():
        candidates = {}
        core_subject = '私募股权 科目三' if '私募' in build.subject or '股权' in build.subject else (_subject_terms(build.subject)[0] if _subject_terms(build.subject) else build.subject)
        for query in (f'{core_subject} 精讲 全套 site:bilibili.com', f'{core_subject} 课程 site:bilibili.com'):
            for row in search_public_web(query, limit=8):
                item = enrich(row)
                if item.get('asset_track') == 'spine' and item.get('segments'):
                    score = evaluate_candidate_quality(item, build.subject, [build.subject])
                    if score:
                        valid_parts = [part for part in item['segments'] if not _other_subject_part(part['title'])]
                        covered = sum(any(_specific_score(part['title'], detail[3]) for part in valid_parts) for detail in details)
                        if covered:
                            candidates[item['url']] = (covered, len(valid_parts), score, item)
        if candidates:
            _, _, score, candidate = max(candidates.values(), key=lambda pair: pair[:3])
            # Keep only episodes with substantive block alignment; never interpolate noise.
            segments = [segment for segment in candidate['segments'] if not _other_subject_part(segment['title']) and any(evaluate_candidate_quality(
                dict(candidate, title=segment['title'], summary=segment.get('summary', ''), segments=[], asset_track='spotlight'), build.subject, detail[3]) for detail in details)]
            if segments:
                data = _catalog_data(dict(candidate, segments=segments), 'spine')
                data.update(origin='auto', match_method=candidate.get('provider', 'deepseek') + '_search', match_score=score)
                asset = store_public_asset(build, data, user)
                discovered_ids.add(asset.pk)
                # A lecture may cover multiple blocks, but each needs a professional hit.
                anchored = []
                for segment in segments:
                    for detail in details:
                        if not _specific_score(segment['title'], detail[3]):
                            continue
                        text = segment.get('summary') or segment['title']
                        assignments = sorted(detail[2], key=lambda row: (
                            _specific_score(text, [row.atom.name, row.atom.key_elements]),
                            _score(text, [row.atom.name])), reverse=True)
                        target_atom_id = assignments[0].atom_id if assignments else None
                        anchored.append(dict(segment, target_block_id=detail[0].pk,
                                             target_atom_id=target_atom_id))
                # Tree-specific anchors stay out of the reusable catalog metadata.
                resources = align_and_mount_spine_series(build,
                    dict(data, segments=anchored, strict_alignment=True), user, asset)
                for resource in resources:
                    _index_resource(resource,
                        next(detail for detail in details if detail[0].pk == resource.block_id), score)

    for detail in details:
        block = detail[0]
        for track, cap, suffix in (('spotlight', 3, '精讲 bilibili'), ('wiki', 2, '定义 法规 权威')):
            if count(block, track) >= cap:
                continue
            # A filled track is already useful; subsequent runs search only missing tracks.
            if block.resources.filter(asset_track=track, is_dismissed=False).exists():
                continue
            finance = '私募' in build.subject or '股权' in build.subject
            core_subject = '私募股权' if finance else (_subject_terms(build.subject)[0] if _subject_terms(build.subject) else build.subject)
            keywords = ' '.join(_specific_terms(detail[3])[:2]) or block.short_title
            query = f'{core_subject} {keywords} ' + ('讲解 site:bilibili.com/video' if track == 'spotlight' else ('定义 site:amac.org.cn' if finance else '专业 wiki 定义'))
            terms = _specific_terms(detail[3]) or [block.short_title]
            queries = [query]
            for term in terms[:3]:
                if track == 'spotlight':
                    queries.append(f'{"基金从业" if finance else core_subject} {term} site:bilibili.com/video')
                elif finance:
                    queries.extend((f'私募基金 {term} site:amac.org.cn', f'私募基金 {term} site:csrc.gov.cn'))
                else:
                    queries.append(f'{core_subject} {term} 专业 wiki 定义')
            ranked = []
            for query in dict.fromkeys(queries):
                for row in search_public_web(query, limit=8):
                    candidate = enrich(row)
                    host = urlsplit(candidate.get('url', '')).hostname or ''
                    official = host.endswith('.gov.cn') or host == 'amac.org.cn' or host.endswith('.amac.org.cn')
                    if track == 'wiki':
                        if not _trusted_wiki_url(candidate.get('url', '')):
                            continue
                    if track == 'spotlight' and official:
                        continue
                    if candidate.get('asset_track') == 'spine':
                        if track != 'spotlight':
                            continue
                        parts = [part for part in candidate.get('segments', []) if
                                 not _other_subject_part(part['title']) and _specific_score(part['title'], detail[3])]
                        if not parts:
                            continue
                        part = max(parts, key=lambda item: _specific_score(item['title'], detail[3]))
                        candidate = dict(candidate, title=f"{candidate['title']} · {part['title']}",
                                         url=part['url'], locator=part['locator'], segments=[],
                                         summary=part.get('summary') or part['title'])
                    candidate = dict(candidate, asset_track=track)
                    score = evaluate_candidate_quality(candidate, build.subject, detail[3])
                    if score:
                        ranked.append((score, candidate))
                if ranked:
                    break
            for score, candidate in sorted(ranked, key=lambda pair: -pair[0]):
                if count(block, track) >= cap:
                    break
                data = _catalog_data(candidate, track)
                asset = store_public_asset(build, data, user)
                with transaction.atomic():
                    resource, created = _mount_candidate(build, detail, data, asset, score, candidate.get('provider', 'deepseek') + '_search', user)
                    if resource:
                        discovered_ids.add(asset.pk)
                        _index_resource(resource, detail, score)
    resources = sorted([resource for detail in details for resource in visible_block_resources(user, detail[0], request=request)], key=lambda row: row.pk)
    summary = _summary(resources)
    result = dict(mounted_count=sum(resource.pk not in before for resource in resources),
                  discovered_assets_count=len(discovered_ids), reused_concept_count=len(reused_ids),
                  asset_track='spotlight', public_asset=None, mounted_summary=summary, resources=resources)
    stats = dict(build.stats or {})
    stats['resource_mount'] = {key: value for key, value in result.items() if key not in ('resources', 'public_asset')}
    build.stats = stats
    build.save(update_fields=['stats', 'updated_at'])
    return result
