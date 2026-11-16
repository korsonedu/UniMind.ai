import test from 'node:test';
import assert from 'node:assert/strict';
import { DEMO_USER_ID, keepNativeSession, isOfflineDemo, setOfflineDemo, isNativeOffline, setNativeOffline, subscribeOffline } from '../src/lib/offlineSession.ts';
test('native cached identity survives unreachable server, reachable 401 revokes it; web remains gated', () => {
  assert.equal(keepNativeSession(true,false,true,true),true);
  assert.equal(keepNativeSession(true,false,true,true,401),false);
  assert.equal(keepNativeSession(true,false,true,true,403),false);
  assert.equal(keepNativeSession(false,false,true,true),false);
  assert.equal(keepNativeSession(true,false,true,false),false);
  assert.equal(keepNativeSession(true,false,true,true,500),true);
});
test('offline subscriptions observe state and unsubscribe cleanly', () => {
  let changes = 0;
  const unsubscribe = subscribeOffline(() => { changes++; });
  setNativeOffline(true);
  assert.equal(isNativeOffline(), true);
  unsubscribe();
  setNativeOffline(false);
  assert.equal(changes, 1);
});
test('demo identity is isolated and cannot be automatically revoked', () => {
  assert.ok(DEMO_USER_ID < 0);
  assert.equal(keepNativeSession(true,true,true,false,401),true);
  setOfflineDemo(true); setNativeOffline(false);
  assert.equal(isOfflineDemo(),true); assert.equal(isNativeOffline(),true);
  setOfflineDemo(false); assert.equal(isNativeOffline(),false);
});
