"""Short-lived browser-only preview; generated code never executes in Python."""
import json
import sys

from playwright.sync_api import sync_playwright


def run(data):
    errors, results, messages = [], [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, chromium_sandbox=True)
        context = browser.new_context(service_workers='block', accept_downloads=False)
        context.route('**/*', lambda route: route.abort())
        page = context.new_page()
        page.set_default_timeout(1200)
        page.on('pageerror', lambda error: errors.append(str(error)[:500]))
        page.set_content('<iframe sandbox="allow-scripts" style="width:700px;height:600px"></iframe>')
        page.evaluate('''() => window.addEventListener('message', event => {
            if (event.source === document.querySelector('iframe').contentWindow && event.data?.channel === 'unimind-experiment') {
                const messages = window.experimentMessages ||= [];
                if (messages.length < 60) messages.push(event.data);
            }
        })''')
        page.locator('iframe').evaluate('(frame, document) => frame.srcdoc = document', data['document'])
        frame = page.frame_locator('iframe')
        frame.locator('body').wait_for()
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
        page.wait_for_timeout(100)
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
