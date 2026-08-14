import os
import logging
import subprocess
import tempfile
import sys

logger = logging.getLogger(__name__)


def _html_to_pdf(html_string: str, output_path: str):
    """使用 Playwright Chromium headless 将 HTML 渲染为 PDF

    通过独立子进程运行 Playwright，完全隔离 Python 解释器生命周期，
    避免 Python 3.14+ 在解释器 shutdown 时 ThreadPoolExecutor 拒绝新任务的问题。
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
        f.write(html_string)
        html_path = f.name

    try:
        script = (
            "import sys, json\n"
            "from playwright.sync_api import sync_playwright\n"
            f"with open({html_path!r}, 'r', encoding='utf-8') as f:\n"
            "    content = f.read()\n"
            "with sync_playwright() as p:\n"
            "    browser = p.chromium.launch(headless=True)\n"
            "    page = browser.new_page()\n"
            "    page.set_content(content, wait_until='networkidle')\n"
            "    page.pdf(\n"
            f"        path={output_path!r},\n"
            "        format='A4',\n"
            "        margin={'top': '15mm', 'bottom': '15mm', 'left': '15mm', 'right': '15mm'},\n"
            "        print_background=True,\n"
            "    )\n"
            "    browser.close()\n"
            "print('OK')\n"
        )
        result = subprocess.run(
            [sys.executable, '-c', script],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Playwright 子进程渲染失败 (exit={result.returncode}): {result.stderr.strip()}")
        if 'OK' not in result.stdout:
            raise RuntimeError(f"Playwright 子进程异常: {result.stderr.strip() or result.stdout.strip()}")
    finally:
        try:
            os.unlink(html_path)
        except OSError:
            pass
