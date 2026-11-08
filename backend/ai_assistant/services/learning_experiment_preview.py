"""Short-lived browser-only preview; generated code never executes in Python."""
import json
import subprocess
import sys

from playwright.sync_api import sync_playwright


def run(data):
    if sys.platform.startswith('linux'):
        fonts = subprocess.run(['/usr/bin/fc-match', '-f', '%{lang}', ':lang=zh-cn'],
            capture_output=True, text=True, timeout=1)
        if fonts.returncode or 'zh-cn' not in fonts.stdout.split('|'):
            return {'ok': False, 'errors': ['运行器缺少中文字体，无法可靠检查文字布局，尚未挂载。'], 'checks': []}
    errors, results, messages = [], [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, chromium_sandbox=True)
        context = browser.new_context(service_workers='block', accept_downloads=False)
        context.route('**/*', lambda route: route.abort())
        page = context.new_page()
        page.set_default_timeout(1200)
        page.on('pageerror', lambda error: errors.append(str(error)[:500]))
        page.set_content('<iframe sandbox="allow-scripts" style="width:700px;height:360px"></iframe>')
        page.evaluate('''() => window.addEventListener('message', event => {
            if (event.source === document.querySelector('iframe').contentWindow && event.data?.channel === 'unimind-experiment') {
                const messages = window.experimentMessages ||= [];
                if (messages.length < 60) messages.push(event.data);
            }
        })''')
        page.locator('iframe').evaluate('(frame, document) => frame.srcdoc = document', data['document'])
        frame = page.frame_locator('iframe')
        frame.locator('body').wait_for()
        def check_layout(width, height=360):
            page.locator('iframe').evaluate('''(element, size) => {
                element.style.width = `${size[0]}px`;
                element.style.height = `${size[1]}px`;
            }''', [width, height])
            page.wait_for_timeout(100)
            overflow = frame.locator('html').evaluate('''element => {
                const clipped = [...document.querySelectorAll('*')].filter(node => {
                    const style = getComputedStyle(node);
                    return (/hidden|clip/.test(style.overflowX) && node.scrollWidth > node.clientWidth + 2)
                        || (/hidden|clip/.test(style.overflowY) && node.scrollHeight > node.clientHeight + 2);
                }).slice(0, 3).map(node => ({
                    element: node.tagName + (node.id ? '#' + node.id : '') + (node.getAttribute('class') ? '.' + node.getAttribute('class') : ''),
                    available: [node.clientWidth, node.clientHeight], content: [node.scrollWidth, node.scrollHeight]
                }));
                return element.scrollWidth > innerWidth + 2 || element.scrollHeight > innerHeight + 2 || clipped.length
                    ? {page: [element.scrollWidth, element.scrollHeight], clipped} : null;
            }''')
            if overflow:
                error = f'讲解内容超出 {width}×{height}，请精简布局，不能隐藏截断：{json.dumps(overflow, ensure_ascii=False)}'
                if error not in errors:
                    errors.append(error)
            overlaps = frame.locator('svg').evaluate_all('''svgs => {
                const found = [];
                for (const svg of svgs) {
                    const labels = [...svg.querySelectorAll('text')].filter(node => node.closest('svg') === svg).map(node => {
                        const box = node.getBoundingClientRect(), style = getComputedStyle(node);
                        return {text: node.textContent.trim().slice(0, 60), x: box.x, y: box.y, w: box.width, h: box.height,
                            visible: style.visibility !== 'hidden' && Number(style.opacity) > 0};
                    }).filter(label => label.text && label.visible && label.w > 0 && label.h > 0);
                    for (let i = 0; i < labels.length; i++) {
                        for (let j = i + 1; j < labels.length; j++) {
                            const a = labels[i], b = labels[j];
                            const w = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
                            const h = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
                            if (w > 1 && h > 1 && w * h > Math.min(a.w * a.h, b.w * b.h) * .15) {
                                found.push({labels: [a.text, b.text], overlap: [Math.round(w), Math.round(h)],
                                    bounds_css_px: [a, b].map(label => [label.x, label.y, label.w, label.h].map(value => Math.round(value)))});
                                if (found.length === 3) return found;
                            }
                        }
                    }
                }
                return found;
            }''')
            for overlap in overlaps:
                error = f'SVG标签重叠（{width}px宽）：{json.dumps(overlap, ensure_ascii=False)}。请分开标签或将图例移到图外，不要缩小字号掩盖。'
                if error not in errors:
                    errors.append(error)

        check_layout(700)
        for check in data['checks']:
            try:
                control = frame.locator(check['selector'])
                if check['action'] == 'click':
                    control.click()
                else:
                    control.evaluate('''(element, value) => {
                        element.value = value;
                        element.dispatchEvent(new Event('input', {bubbles:true}));
                        element.dispatchEvent(new Event('change', {bubbles:true}));
                    }''', check.get('value', ''))
                from playwright.sync_api import expect
                expect(frame.locator(check['expect_selector'])).to_contain_text(check['expect_text'], timeout=1200)
                results.append({'selector': check['selector'], 'ok': True})
            except Exception as error:
                results.append({'selector': check['selector'], 'ok': False, 'error': str(error)[:600]})
        check_layout(700)
        check_layout(360, 420)
        messages = page.evaluate('window.experimentMessages || []')
        errors.extend(str(item.get('message', ''))[:500] for item in messages if item.get('type') == 'error')
        text = frame.locator('body').inner_text()[:1800]
        browser.close()
    return {'ok': not errors and all(item['ok'] for item in results),
        'errors': errors[:5], 'checks': results, 'text': text,
        'note': '仅核验浏览器运行及指定交互，不证明教学内容或公式正确。'}


if __name__ == '__main__':
    try:
        result = run(json.load(sys.stdin))
    except Exception as error:
        result = {'ok': False, 'errors': [str(error)[:600]], 'checks': []}
    print(json.dumps(result, ensure_ascii=False))
