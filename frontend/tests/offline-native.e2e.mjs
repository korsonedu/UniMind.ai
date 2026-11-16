import assert from 'node:assert/strict';

// Optional local runner: PLAYWRIGHT_MODULE may point to an existing installation.
// No browser or packages are downloaded by this test.
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.UNIMIND_E2E_URL || 'http://127.0.0.1:4173';
const browser = await chromium.launch({ headless: true, ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}) });
const preferences = new Map([['unimind_native_auth_token', 'preserved-real-token']]);
const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, serviceWorkers: 'block' });
const errors = [];
let requests = 0;
try {
  await context.exposeBinding('nativePreferences', async (_, method, options) => {
    if (method === 'get') return { value: preferences.get(options.key) ?? null };
    if (method === 'set') preferences.set(options.key, options.value);
    if (method === 'remove') preferences.delete(options.key);
    return {};
  });
  await context.addInitScript(() => {
    localStorage.setItem('unimind-language', 'en');
    window.androidBridge = {};
    window.Capacitor = {
      PluginHeaders: [
        { name: 'Preferences', methods: ['get', 'set', 'remove'].map(name => ({ name, rtype: 'promise' })) },
        { name: 'App', methods: [{ name: 'addListener', rtype: 'callback' }, { name: 'removeListener', rtype: 'promise' }, { name: 'exitApp', rtype: 'promise' }] },
      ],
      nativePromise: async (plugin, method, options) => plugin === 'Preferences' ? window.nativePreferences(method, options) : {},
      nativeCallback: () => 'back',
    };
  });
  await context.route('**/api/**', route => { requests++; return route.abort('failed'); });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`${base}/login`);
  await page.getByRole('button', { name: /Offline trial|Try offline|离线试用/i }).click();
  await page.waitForURL(url => !url.pathname.startsWith('/login'));
  await page.goto(`${base}/notes/1`);
  const title = page.getByRole('textbox', { name: /Note title|笔记标题/i, exact: true });
  await title.fill('Persisted offline edit');
  await page.waitForTimeout(1800);
  await page.reload();
  await assert.doesNotReject(() => title.waitFor());
  assert.equal(await title.inputValue(), 'Persisted offline edit');
  assert.equal(preferences.get('unimind_native_auth_token'), 'preserved-real-token');
  assert.ok([...preferences.keys()].some(key => key.startsWith('unimind:offline:v1:-1:')));
  for (const path of ['/notes', '/practice', '/calendar', '/settings']) {
    await page.goto(base + path);
    await page.waitForTimeout(400);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), true, `${path} overflows`);
  }
  await page.goto(`${base}/practice`);
  const option = page.getByRole('button', { name: 'Spaced revision and active recall', exact: true });
  await option.tap();
  await page.getByRole('status').filter({ hasText: 'Correct.' }).waitFor();
  assert.ok((await option.boundingBox()).height >= 44);
  assert.equal(requests, 0, 'offline demo must never contact a backend');
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ pass: true, checks: ['zero backend requests', 'native demo persistence', 'real token preserved', 'notes survive reload', '390x844 routes', '44px practice touch target', 'English offline practice'], errors }));
} finally {
  await context.close();
  await browser.close();
}
