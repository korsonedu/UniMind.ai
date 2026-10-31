import assert from 'node:assert/strict';
import test from 'node:test';
import { sameOrigin, validResource, validSource } from './security';

test('navigation stays on the app origin', () => {
  const source = 'https://unimind-ai.com/xiaoyu';
  assert.equal(sameOrigin(source, 'https://unimind-ai.com/login'), true);
  for (const target of [
    'https://unimind-ai.com.evil.test/',
    'https://evil.test/',
    'file:///etc/passwd',
    'javascript:alert(1)',
    'https://name@unimind-ai.com/',
  ]) {
    assert.equal(sameOrigin(source, target), false, target);
  }
});

test('resources open only safe web urls', () => {
  const source = 'http://127.0.0.1:5175/xiaoyu';
  for (const target of [
    'https://unimind-ai.com/media/course.pdf',
    'https://files.example.test/course.pdf',
    'http://127.0.0.1:5175/media/image.png',
  ]) {
    assert.equal(validResource(source, target, true), true, target);
  }
  for (const target of [
    'file:///etc/passwd',
    'javascript:alert(1)',
    'https://name:secret@example.test/',
    'http://example.test/file',
    'http://127.0.0.1:8000/admin/',
    'mailto:test@example.test',
  ]) {
    assert.equal(validResource(source, target, true), false, target);
  }
});

test('http sources are development loopback only', () => {
  assert.equal(validSource('https://unimind-ai.com/', false), true);
  assert.equal(validSource('http://127.0.0.1:5175/xiaoyu', true), true);
  assert.equal(validSource('http://127.0.0.1:5175/xiaoyu', false), false);
  assert.equal(validSource('http://example.test/', true), false);
  assert.equal(validSource('https://name:secret@unimind-ai.com/', true), false);
});
