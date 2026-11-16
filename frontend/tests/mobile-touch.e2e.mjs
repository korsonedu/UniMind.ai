import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
import assert from 'node:assert/strict';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const user = { id: 1, username: 'mobile-test', nickname: '移动验证', role: 'student', has_completed_initial_assessment: true, avatar_url: '', tour_dismissed_at: '2026-01-01', tour_panel_dismissed_at:'2026-01-01' };
const browser = await chromium.launch({ headless: true, ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}) });
const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, serviceWorkers: 'block' });
const page = await context.newPage();
page.setDefaultTimeout(30000);
const errors = [];
page.on('pageerror', e => errors.push(e.message));
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
await context.addInitScript(({ user, locale }) => { localStorage.setItem('unimind-language', locale); if (!['/login', '/register'].includes(location.pathname)) localStorage.setItem('auth-storage', JSON.stringify({ state: { user }, version: 0 })); }, { user, locale: process.env.MOBILE_LOCALE || 'zh-CN' });
await context.routeWebSocket('**/ws/**', () => {});
const note = { id: 1, title: '移动端验证笔记', content: '手机上查看和编辑学习笔记。', notebook: null, tags: [], version: 1, is_favorite: false, deleted_at: null, created_at: '2026-11-15T00:00:00Z', updated_at: '2026-11-15T00:00:00Z' };
const course = { id: 1, title: '移动端触控课程', description: '移动端课程布局验证', video_file: '/media/test.mp4', courseware: null, reference_materials: null, elo_reward: 10, tags: [], created_at: '2026-11-15T00:00:00Z' };
const question = { id: 1, user: 1, user_detail: user, content: '手机上的学习步骤应该如何安排？', attachment: null, is_solved: false, is_starred: false, is_liked: false, is_followed: false, likes_count: 0, reply_count: 0, first_answer: null, answers: [], created_at: '2026-11-15T00:00:00Z', updated_at: '2026-11-15T00:00:00Z' };
const studyMessage = { id: 1, user_detail: user, content: '移动端自习消息验证', timestamp: '2026-11-15T00:00:00Z' };
const fixtures = {
  '/api/users/me/': user,
  '/api/users/learning/access/': { is_course_student: true, ai_usage: { used: 0, limit: 100, remaining: 100, base_remaining: 100, addon_remaining: 0, configured: true, unlimited: false, resets_at: '2026-12-01T00:00:00+08:00' }, addons: [] },
  '/api/notes/references/': { note_ids: [] },
  '/api/users/institution/me/features/': { is_platform_admin: false, has_course_catalog: true, features: ['ai.assistant','course.video','faq.system','study.room','quiz.exam','wrong.review'], institution: null },
  '/api/notifications/unread-count/': { count: 0 },
  '/api/notifications/': [],
  '/api/ai/bots/': [{ id: 1, name: '小宇', bot_type: 'planner', institution: null, is_active: true }],
  '/api/ai/history/': [],
  '/api/ai/projects/': [],
  '/api/notes/items/': [note],
  '/api/notes/notebooks/': [],
  '/api/notes/tags/': [],
  '/api/notes/ai-settings/': { enabled: false, acknowledged: false },
  '/api/courses/': { items: [course], total_pages: 1 },
  '/api/courses/1/': { ...course, cover_image: null, ai_outline_enabled: true, ai_subtitles_enabled: true, user_progress: null },
  '/api/courses/1/outline/': { status: 'completed', items: [] },
  '/api/courses/1/transcript/': { status: 'completed', segments: [] },
  '/api/courses/1/progress/': { status: 'ok' },
  '/api/courses/learning-progress/': [],
  '/api/courses/learning-activity/': { today: '2026-11-15', tracking_started_at: null, days: [], totals: [] },
  '/api/courses/watch-later/': [],
  '/api/qa/questions/': { count: 1, next: null, previous: null, results: [question] },
  '/api/users/online/': [],
  '/api/study/messages/': [studyMessage],
  '/api/users/plans/': [],
  '/api/users/workspace/': { available: true, role: 'admin', workspace: { name: 'Mobile workspace', description: '', joined_at: '', service_ends_at: '2027-01-01', service_active: true }, courses: [{ id: 1, title: 'Long mobile workspace course title for responsive layout validation', module: 'Module', duration: '10:00', filename: 'course.mp4', status: 'published', transcript: '', knowledge: [] }], members: [], invites: [], usage: [] },
  '/api/csrf/': { csrfToken: 'test-csrf' },
};
let hasCatalog = true;
const requests = [];
const unmatched = [];
await context.route('https://api.dicebear.com/**', route => route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><circle cx="32" cy="32" r="30" fill="#8fa89b"/></svg>' }));
// A zero-byte media fixture renders the player without exercising playback.
await context.route('**/media/test.mp4', route => route.fulfill({ contentType: 'video/mp4', body: Buffer.alloc(0) }));
await context.route('**/api/**', async route => {
  const path = new URL(route.request().url()).pathname;
  requests.push(path);
  if (!(path in fixtures)) {
    unmatched.push(path);
    await route.fulfill({ status: 500, json: { detail: `Missing test fixture: ${path}` } });
    return;
  }
  if (path === '/api/users/institution/me/features/') fixtures[path].has_course_catalog = hasCatalog;
  const data = path === '/api/notes/ai-settings/' && route.request().method() === 'PATCH' ? { enabled: false, acknowledged: true } : fixtures[path];
  await route.fulfill({ json: data });
});
const ready = {
  '/register': () => page.locator('#reg-email').waitFor(),
  '/login': () => page.locator('#login-email').waitFor(),
  '/settings/institution': () => page.locator('.iw-management').waitFor(),
  '/settings': () => page.locator('.um-settings-workspace').waitFor(),
  '/notes': () => page.locator('.notes-workspace').waitFor(),
  '/courses': () => page.locator('.um-app-main').getByText(course.title, { exact: true }).filter({ visible: true }).first().waitFor(),
  '/course/1': () => page.locator('.um-lesson-view video').waitFor(),
  '/qa': () => page.getByText(question.content, { exact: true }).waitFor(),
  '/study': () => page.getByText(studyMessage.content, { exact: true }).waitFor(),
  '/xiaoyu': () => page.locator('.um-native-agent textarea').first().waitFor(),
};
const results = [];
mkdirSync('releases/test-artifacts', { recursive: true });
try {
  for (const path of ['/login','/register','/settings/institution','/settings','/notes','/courses','/course/1','/qa','/study','/xiaoyu']) {
    await page.goto(`${process.env.MOBILE_BASE_URL || 'http://127.0.0.1:4173'}${path}`);
    console.log('Checking', path);
    await ready[path]();
    await page.waitForLoadState('networkidle');
    if (path === '/notes') {
      const dialog = page.getByRole('dialog');
      if (await dialog.isVisible()) {
      const box = await dialog.boundingBox();
      assert.ok(box.x >= 0 && box.x + box.width <= 390 && box.y >= 0 && box.y + box.height <= 844, 'notes onboarding fits the mobile viewport');
      results.push({ path: '/notes:onboarding', bounds: box, horizontalOverflow: false });
      await dialog.locator('button').filter({ hasText: /.+/ }).last().tap();
      await dialog.waitFor({ state: 'hidden' });
      }
      await page.getByText(note.title, { exact: true }).waitFor();
      await page.waitForLoadState('networkidle');
    }
    assert.deepEqual(unmatched, [], 'all API calls have an explicit contract fixture');
    assert.deepEqual(errors, [], `${path} console and uncaught errors`);
    const size = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
    assert.ok(size.scroll <= size.width, `${path} overflows: ${JSON.stringify(size)}`);
    const screenshot = `releases/test-artifacts/mobile-${process.env.MOBILE_LOCALE || 'zh-CN'}-${path.slice(1).replaceAll('/', '-')}.png`;
    await page.screenshot({ path: screenshot });
    results.push({ path, screenshot, ...size, ...(path === '/course/1' ? { verification: 'video player and workspace layout; playback not exercised' } : {}) });
  }

  hasCatalog = false;
  await page.goto(`${process.env.MOBILE_BASE_URL || 'http://127.0.0.1:4173'}/xiaoyu?panel=saved-courses`);
  const saved = page.locator('#sidebar-panel-saved-courses');
  await saved.getByText(course.title, { exact: true }).waitFor();
  const sidebar = await page.locator('#um-right-panel').boundingBox();
  assert.ok(sidebar && sidebar.x >= -1 && sidebar.x + sidebar.width <= 391, 'saved course sidebar fits viewport');
  const closeSidebar = page.locator('#um-notes-toggle');
  const closeBox = await closeSidebar.boundingBox();
  assert.ok(closeBox.width >= 44 && closeBox.height >= 44, 'sidebar touch target');
  await closeSidebar.tap();
  assert.equal(await page.locator('#um-right-panel').getAttribute('aria-hidden'), 'true');
  const navTargets = await page.locator('.um-app-mobile-links a').evaluateAll(nodes => nodes.map(node => { const r = node.getBoundingClientRect(); return { width: r.width, height: r.height }; }));
  assert.ok(navTargets.length && navTargets.every(r => r.width >= 44 && r.height >= 44), 'bottom navigation touch targets');
  const input = page.locator('.um-native-agent textarea').first();
  await input.tap();
  await page.setViewportSize({ width: 390, height: 520 });
  const composer = await input.boundingBox();
  assert.ok(composer && composer.y >= 0 && composer.y + composer.height <= 520, 'composer remains reachable in a reduced viewport');
  results.push({ path: '/xiaoyu:saved-courses', sidebar, navTargets, reducedViewportComposer: composer });
  assert.deepEqual(unmatched, [], 'all saved course API calls have fixtures');
  assert.deepEqual(errors, [], 'saved course and composer runtime errors');
  writeFileSync(`releases/test-artifacts/mobile-verification-${process.env.MOBILE_LOCALE || 'zh-CN'}.json`, JSON.stringify({ viewport: { width: 390, height: 844 }, results, requests, unmatched, errors }, null, 2));
  console.log(JSON.stringify({ results, unmatched, errors }, null, 2));
} finally {
  await browser.close();
}
