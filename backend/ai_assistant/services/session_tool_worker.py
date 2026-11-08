"""JSON-in/JSON-out JavaScript in short-lived browser Workers, without site credentials."""
import json
import sys

from playwright.sync_api import sync_playwright


def run(data):
    payload = json.dumps(data, ensure_ascii=True, allow_nan=False).replace('<', '\\u003c')
    document = '''<!doctype html><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; worker-src blob:; connect-src 'none'; base-uri 'none'; form-action 'none'">
<script>
const {source, inputs} = PAYLOAD_JSON;
const wrapper = `
self.onmessage = async event => {
  try {
    const value = await run(event.data);
    const json = JSON.stringify(value, (_key, item) => {
      if (typeof item === 'number' && !Number.isFinite(item)) throw Error('Result must be finite');
      if (['undefined','function','symbol','bigint'].includes(typeof item)) throw Error('Result must be JSON');
      return item;
    });
    if (json.length > 8192) throw Error('Result is too large');
    self.postMessage({ok:true, value:JSON.parse(json)});
  } catch(error) { self.postMessage({ok:false,error:String(error).slice(0,700)}); }
};`;
(async () => {
  const results = [];
  try {
    for (const input of inputs) {
      const url = URL.createObjectURL(new Blob([source, '\\n', wrapper], {type:'text/javascript'}));
      const worker = new Worker(url);
      try {
        const response = await new Promise((resolve,reject) => {
          const timeout = setTimeout(() => reject(Error('JavaScript execution timed out')), 1200);
          worker.onmessage = event => { clearTimeout(timeout); resolve(event.data); };
          worker.onerror = event => { clearTimeout(timeout); reject(Error(event.message)); };
          worker.postMessage(input);
        });
        if (!response.ok) throw Error(response.error);
        results.push(response.value);
      } finally { worker.terminate(); URL.revokeObjectURL(url); }
    }
    parent.postMessage({ok:true,results}, '*');
  } catch(error) { parent.postMessage({ok:false,error:String(error).slice(0,700)}, '*'); }
})();
</script>'''.replace('PAYLOAD_JSON', payload)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, chromium_sandbox=True)
        context = browser.new_context(service_workers='block', accept_downloads=False)
        context.route('**/*', lambda route: route.abort())
        page = context.new_page()
        page.set_default_timeout(9000)
        page.set_content('<iframe sandbox="allow-scripts"></iframe>')
        page.evaluate("window.addEventListener('message', event => { if (event.source === document.querySelector('iframe').contentWindow) window.result = event.data; })")
        page.locator('iframe').evaluate('(frame, document) => frame.srcdoc = document', document)
        page.wait_for_function('window.result !== undefined')
        result = page.evaluate('window.result')
        browser.close()
        return result


if __name__ == '__main__':
    try:
        result = run(json.load(sys.stdin))
    except Exception as error:
        result = {'ok': False, 'error': str(error)[:700]}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
