"""Public desktop downloads, following published desktop releases (including prereleases)."""

import re

import requests
from django.core.cache import cache
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class DesktopReleaseView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        data = cache.get('desktop-release')
        if data is not None:
            return Response(data)

        try:
            response = requests.get(
                'https://api.github.com/repos/korsonedu/UniMind.ai/releases',
                params={'per_page': 100},
                headers={'Accept': 'application/vnd.github+json'},
                timeout=10,
            )
            response.raise_for_status()
            releases = []
            for release in response.json():
                match = re.fullmatch(r'desktop-v(\d+)\.(\d+)\.(\d+)', release.get('tag_name', ''))
                if match and not release.get('draft') and release.get('published_at'):
                    releases.append((tuple(map(int, match.groups())), release))
            if not releases:
                return Response({'detail': '暂无桌面版本'}, status=503)

            _, release = max(releases, key=lambda item: item[0])
            version = release['tag_name'].removeprefix('desktop-v')
            # Current packages are hosted on our site; also accept GitHub assets.
            urls = re.findall(r'https://unimind-ai\.com/static/desktop/[^\s)]+', release.get('body') or '')
            urls += [asset['browser_download_url'] for asset in release.get('assets', [])
                     if asset.get('state') == 'uploaded']
            packages = {}
            for platform, suffix in [('mac', r'arm64(?:-unsigned)?\.dmg'),
                                     ('windows', r'x64(?:-unsigned)?-setup\.exe')]:
                pattern = rf'/UniMind-{re.escape(version)}-{suffix}$'
                url = next((url for url in urls if re.search(pattern, url)), None)
                if url:
                    packages[platform] = url
            if not packages:
                return Response({'detail': '最新版本安装包尚未就绪'}, status=503)

            data = {
                'version': version,
                'prerelease': release.get('prerelease', False),
                'packages': packages,
                'instructions': f'https://unimind-ai.com/static/desktop/{version}/INSTALL.txt',
            }
            cache.set('desktop-release', data, 300)
            return Response(data)
        except (requests.RequestException, ValueError):
            return Response({'detail': '暂时无法获取最新桌面版本，请稍后重试'}, status=503)
