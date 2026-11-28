"""Short-lived browser-only preview; generated code never executes in Python."""
import base64
import hashlib
import json
import subprocess
import sys

from playwright.sync_api import Error, expect, sync_playwright


def run(data):
    capture = data.get('capture_screenshots', False)
    initial_selector = data.get('initial_selector')
    if capture and sys.platform.startswith('linux'):
        fonts = subprocess.run(['/usr/bin/fc-match', '-f', '%{lang}', ':lang=zh-cn'],
            capture_output=True, text=True, timeout=1)
        if fonts.returncode or 'zh-cn' not in fonts.stdout.split('|'):
            return {'ok': False, 'errors': ['运行器缺少中文字体，无法可靠检查文字布局，尚未挂载。'], 'checks': []}
    errors, results, screenshots = [], [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, chromium_sandbox=True)
        context = browser.new_context(service_workers='block', accept_downloads=False,
            device_scale_factor=1, viewport={'width': 740, 'height': 800})
        context.route('**/*', lambda route: route.abort())
        page = context.new_page()
        page.set_default_timeout(2000)
        page.on('pageerror', lambda error: errors.append(str(error)[:500]))
        page.set_content('<style>html,body{margin:0;padding:0;overflow:hidden}</style>'
            '<iframe sandbox="allow-scripts" style="display:block;border:0;width:700px;height:800px"></iframe>')
        page.evaluate('''() => window.addEventListener('message', event => {
            if (event.source === document.querySelector('iframe').contentWindow && event.data?.channel === 'unimind-experiment') {
                const messages = window.experimentMessages ||= [];
                if (messages.length < 60) messages.push(event.data);
            }
        })''')
        page.locator('iframe').evaluate('(frame, document) => frame.srcdoc = document', data['document'])
        frame = page.frame_locator('iframe')
        body = frame.locator('body')
        body.wait_for(state='attached')

        def check_render(width, phase=None):
            page.locator('iframe').evaluate('(element, width) => element.style.width = `${width}px`', width)
            body.evaluate('''() => new Promise(resolve => {
                requestAnimationFrame(() => requestAnimationFrame(resolve));
            })''')
            height = body.evaluate('''body => {
                const visibility = {visibilityProperty: true, opacityProperty: true};
                const height = body.getBoundingClientRect().height;
                if (height <= 20 || !body.checkVisibility(visibility)) return null;
                const hasContent = body.innerText.trim() || [...body.querySelectorAll('svg,canvas,input,button')].some(node => {
                    const box = node.getBoundingClientRect();
                    return box.width > 0 && box.height > 0 && node.checkVisibility(visibility);
                });
                if (!hasContent) return null;
                const style = getComputedStyle(body);
                return Math.ceil(height + parseFloat(style.marginTop) + parseFloat(style.marginBottom));
            }''')
            if height is None:
                error = f'讲解卡片在 {width}px 宽度下没有可见内容。'
                if error not in errors:
                    errors.append(error)
                return
            if initial_selector and body.evaluate('body => body.scrollWidth > innerWidth + 2'):
                error = f'组件在 {width}px 宽度下发生横向溢出。'
                if error not in errors:
                    errors.append(error)
            height = max(180, min(800, height))
            page.locator('iframe').evaluate('(element, height) => element.style.height = `${height}px`', height)
            if capture and phase and not errors:
                png = page.screenshot(clip={'x': 0, 'y': 0, 'width': width, 'height': height}, type='png', scale='css',
                    animations='disabled', caret='hide', timeout=3000)
                if (len(screenshots) >= 8 or len(png) > 512 * 1024
                        or sum(item['bytes'] for item in screenshots) + len(png) > 2 * 1024 * 1024):
                    errors.append('讲解截图超过审查容量，请简化画面后重试。')
                else:
                    screenshots.append({'id': f'{phase}-{width}', 'width': width, 'height': height,
                        'phase': phase, 'bytes': len(png), 'sha256': hashlib.sha256(png).hexdigest(),
                        'png': base64.b64encode(png).decode('ascii')})

        check_render(700, phase='initial')
        if initial_selector:
            check_render(360)
            expect(frame.locator(initial_selector)).to_be_visible(timeout=1200)
        if capture:
            check_render(360, phase='initial')
            check_render(700)
        for index, check in enumerate(data['checks']):
            target = frame.locator(check['expect_selector'])
            expected_text = check.get('expect_text')
            phase = 'precondition'
            try:
                if expected_text is None and target.is_visible():
                    raise ValueError('目标在操作前已可见，请选择仅在结果状态下出现的元素。')
                phase = 'action'
                control = frame.locator(check['selector'])
                if check['action'] == 'click':
                    control.click()
                else:
                    control.evaluate('''(element, value) => {
                        element.value = value;
                        element.dispatchEvent(new Event('input', {bubbles:true}));
                        element.dispatchEvent(new Event('change', {bubbles:true}));
                    }''', check.get('value', ''))
                phase = 'assertion'
                if expected_text is None:
                    expect(target).to_be_visible(timeout=1200)
                elif expected_text == '':
                    expect(target).to_have_text('', timeout=1200)
                else:
                    expect(target).to_contain_text(expected_text, timeout=1200)
                if capture:
                    phase = 'render'
                    check_render(700, phase=f'check-{index + 1}')
                elif initial_selector:
                    check_render(360)
                results.append({'selector': check['selector'], 'ok': True})
            except Exception as error:
                failure = {'selector': check['selector'], 'ok': False, 'phase': phase,
                           'expect_selector': check['expect_selector'], 'error': str(error)[:600]}
                if phase in ('precondition', 'assertion'):
                    try:
                        failure['observed'] = target.evaluate_all('''elements => ({
                            matches: elements.length,
                            text: (elements[0]?.textContent ?? '').trim().slice(0, 300)
                        })''')
                    except Error:
                        pass
                results.append(failure)
        check_render(700)
        check_render(360, phase='final')
        messages = page.evaluate('window.experimentMessages || []')
        errors.extend(str(item.get('message', ''))[:500] for item in messages if item.get('type') == 'error')
        text = body.inner_text()[:1800]
        browser.close()
    return {'ok': not errors and all(item['ok'] for item in results),
        'errors': errors[:5], 'checks': results, 'text': text,
        'document_sha256': hashlib.sha256(data['document'].encode()).hexdigest(),
        'note': '仅核验浏览器运行及指定交互，不证明教学内容或公式正确。',
        **({'layout_checked': True} if initial_selector else {}),
        **({'screenshots': screenshots} if capture else {})}


if __name__ == '__main__':
    try:
        result = run(json.load(sys.stdin))
    except Exception as error:
        result = {'ok': False, 'errors': [str(error)[:600]], 'checks': []}
    print(json.dumps(result, ensure_ascii=False))
