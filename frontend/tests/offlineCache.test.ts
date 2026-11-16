import test from 'node:test';
import assert from 'node:assert/strict';
import { nativeCacheKey } from '../src/lib/offlineCacheKey.ts';
import { demoPlaybackStage } from '../src/lib/demoPlayback.ts';
import { readFileSync } from 'node:fs';
import { stripTypeScriptTypes } from 'node:module';
import vm from 'node:vm';

// Exercise the production cache with native storage/network boundaries replaced.
// Node's built-in TS stripping keeps this runnable without a browser or bundler.
function cacheHarness() {
  const persisted = new Map<string, string>();
  const reads: string[] = [];
  let origin = 'https://server-a.example';
  let calls = 0;
  let delay: ((key: string) => Promise<{ value: string | null }>) | null = null;
  const source = ['offlineData.ts', 'offlineDemoApi.ts'].map(file => stripTypeScriptTypes(readFileSync(new URL(`../src/lib/${file}`, import.meta.url), 'utf8'))
    .replace(/^import .*;\r?\n/gm, '').replace(/^export \{.*\};\r?$/gm, '').replace(/^export /gm, '')).join('\n');
  const cache = vm.runInNewContext(`${source}\n;({ loadOfflineCache, resetOfflineCache, updateLocalDemo, cacheNote, queueNoteSave, flushOfflineOutbox, demoRequest })`, {
    Date, Map, Set, Promise, AbortController, crypto, setTimeout, clearTimeout,
    navigator: { onLine: true }, window: { dispatchEvent: () => {} }, CustomEvent: class {},
    isNativePlatform: () => true, getServerOrigin: () => origin, nativeCacheKey,
    DEMO_USER_ID: -1, OFFLINE_MESSAGE: 'Connect to a server', t: (message: string) => message, URL,
    createDemoNotes: () => [{ id: 1, title: 'Demo', content: '', version: 1, updated_at: '2026-01-01' }],
    createDemoNotebooks: () => [], axios: { isAxiosError: () => false },
    api: { patch: async () => { calls++; throw new Error('Unexpected network'); }, post: async () => { calls++; throw new Error('Unexpected network'); } },
    Preferences: {
      get: async ({ key }: { key: string }) => { reads.push(key); return delay ? delay(key) : { value: persisted.get(key) ?? null }; },
      set: async ({ key, value }: { key: string; value: string }) => { persisted.set(key, value); },
    },
  });
  return { cache, persisted, reads, calls: () => calls, origin: (value: string) => { origin = value; }, delay: (value: typeof delay) => { delay = value; } };
}

test('native storage isolates demo, accounts, and server origins', () => {
  const keys = [nativeCacheKey(-1, 'http://localhost'), nativeCacheKey(1, 'http://localhost'), nativeCacheKey(2, 'http://localhost'), nativeCacheKey(1, 'https://unimind-ai.com')];
  assert.equal(new Set(keys).size, keys.length);
  for (const id of [0, NaN, Infinity, 1.5, Number.MAX_SAFE_INTEGER + 1]) assert.throws(() => nativeCacheKey(id, 'http://localhost'));
});

test('demo playback clamps invalid stages and never mutates local learning steps', () => {
  const steps = Object.freeze(['read', 'recall', 'review']);
  assert.deepEqual(demoPlaybackStage(steps, 1), ['read']);
  assert.deepEqual(demoPlaybackStage(steps, 2.8), ['read', 'recall']);
  assert.deepEqual(demoPlaybackStage(steps, 99), [...steps]);
  for (const stage of [-1, NaN, Infinity]) assert.deepEqual(demoPlaybackStage(steps, stage), []);
  assert.deepEqual(steps, ['read', 'recall', 'review']);
});

test('native demo edits persist separately and never sync into a real account', async () => {
  const harness = cacheHarness();
  await harness.cache.updateLocalDemo((cache: { notes: { title: string }[] }) => { cache.notes[0].title = 'Edited'; });
  const key = nativeCacheKey(-1, 'https://server-a.example');
  assert.equal(JSON.parse(harness.persisted.get(key)!).notes[0].title, 'Edited');
  assert.equal((await harness.cache.loadOfflineCache(7)).notes.length, 0);
  await harness.cache.flushOfflineOutbox(-1);
  assert.equal(harness.calls(), 0);
  harness.cache.resetOfflineCache();
  assert.equal((await harness.cache.loadOfflineCache(-1)).notes[0].title, 'Edited');
});

test('late native reads cannot hydrate data into another server origin', async () => {
  const harness = cacheHarness();
  let complete!: (value: { value: string | null }) => void;
  harness.delay(() => new Promise(resolve => { complete = resolve; }));
  const first = harness.cache.loadOfflineCache(7);
  harness.origin('https://server-b.example');
  const second = harness.cache.loadOfflineCache(7);
  harness.delay(null);
  complete({ value: JSON.stringify({ version: 1, userId: 7, notes: [{ title: 'Secret A' }], notebooks: [], tags: [], practice: {}, outbox: [], updatedAt: '' }) });
  assert.equal(await first, null);
  assert.equal((await second).notes.length, 0);
  assert.ok(harness.reads.at(-1)?.includes(encodeURIComponent('https://server-b.example')));
});

test('an origin change cancels a pending write instead of writing into the new server partition', async () => {
  const harness = cacheHarness();
  await harness.cache.loadOfflineCache(-1);
  const write = harness.cache.updateLocalDemo((cache: { notes: { title: string }[] }) => { cache.notes[0].title = 'Pending'; });
  harness.origin('https://server-b.example');
  await assert.rejects(write);
  assert.equal(harness.persisted.size, 0);
  harness.cache.resetOfflineCache();
});

test('offline adapter follows current workspace and saved-course schemas without granting administration', async () => {
  const { cache } = cacheHarness();
  const workspace = await cache.demoRequest('get', '/users/workspace/');
  assert.equal(workspace.role, null);
  assert.equal(workspace.available, false);
  assert.equal(workspace.members.length, 0);
  const courses = await cache.demoRequest('get', '/courses/', {}, { saved: 1 });
  assert.equal(courses.items.length, 0);
  assert.equal(courses.total_pages, 1);
  await assert.rejects(cache.demoRequest('post', '/users/workspace/join/', { code: 'example' }));
  await assert.rejects(cache.demoRequest('get', '/knowledge-builder/'));
  cache.resetOfflineCache();
});

test('offline note edits and permanent deletion persist without creating a real-account outbox', async () => {
  const { cache, calls } = cacheHarness();
  const note = await cache.demoRequest('post', '/notes/items/', { title: 'New note' });
  await cache.demoRequest('patch', `/notes/items/${note.id}/`, { title: 'Edited note' });
  cache.resetOfflineCache();
  assert.equal((await cache.demoRequest('get', `/notes/items/${note.id}/`)).title, 'Edited note');
  await cache.demoRequest('delete', `/notes/items/${note.id}/?permanent=1`);
  await assert.rejects(cache.demoRequest('get', `/notes/items/${note.id}/`));
  assert.equal((await cache.loadOfflineCache(-1)).outbox.length, 0);
  assert.equal(calls(), 0);
  cache.resetOfflineCache();
});
