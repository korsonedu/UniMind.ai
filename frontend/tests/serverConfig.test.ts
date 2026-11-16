import assert from 'node:assert/strict';
import { test, mock } from 'node:test';
import { Capacitor } from '@capacitor/core';
import { normalizeServerOrigin, getApiBaseUrl, getWsBaseUrl, setServerOrigin, resolveAssetUrl, SERVER_ORIGIN_STORAGE_KEY } from '../src/lib/serverConfig.ts';

test('服务器地址校验拒绝凭据和非 HTTP 协议，并规范化 Origin', () => {
  assert.equal(normalizeServerOrigin(' https://unimind-ai.com/ '), 'https://unimind-ai.com');
  assert.equal(normalizeServerOrigin('192.168.1.8:8000', { defaultScheme: 'http' }), 'http://192.168.1.8:8000');
  for (const value of ['javascript:alert(1)', 'file:///tmp/data', 'https://user:secret@example.org', '', 'http://']) {
    assert.equal(normalizeServerOrigin(value), null);
  }
});

test('原生 API、WS 和媒体跟随当前服务器，静态资源留在包内', () => {
  const data = new Map<string, string>();
  const original = Object.getOwnPropertyDescriptor(globalThis, 'window');
  Object.defineProperty(globalThis, 'window', { configurable: true, value: {
    localStorage: { getItem: (key: string) => data.get(key) ?? null, setItem: (key: string, value: string) => data.set(key, value) },
    dispatchEvent: () => true,
  } });
  mock.method(Capacitor, 'isNativePlatform', () => true);
  try {
    setServerOrigin('http://127.0.0.1:8000/');
    assert.equal(data.get(SERVER_ORIGIN_STORAGE_KEY), 'http://127.0.0.1:8000');
    assert.equal(getApiBaseUrl(), 'http://127.0.0.1:8000/api');
    assert.equal(getWsBaseUrl(), 'ws://127.0.0.1:8000');
    assert.equal(resolveAssetUrl('/media/video.mp4'), 'http://127.0.0.1:8000/media/video.mp4');
    assert.equal(resolveAssetUrl('/assets/app.js'), '/assets/app.js');
    setServerOrigin('https://unimind-ai.com');
    assert.equal(getApiBaseUrl(), 'https://unimind-ai.com/api');
    assert.equal(getWsBaseUrl(), 'wss://unimind-ai.com');
    assert.equal(resolveAssetUrl('https://cdn.example.org/a.png'), 'https://cdn.example.org/a.png');
  } finally {
    mock.restoreAll();
    if (original) Object.defineProperty(globalThis, 'window', original);
    else Reflect.deleteProperty(globalThis, 'window');
  }
});
