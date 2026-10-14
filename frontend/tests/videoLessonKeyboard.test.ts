import assert from 'node:assert/strict';
import test from 'node:test';
import { shouldTogglePlayback } from '../src/pages/videoLessonKeyboard.ts';

test('space toggles playback from non-interactive page content', () => {
  assert.equal(shouldTogglePlayback({ key: ' ', code: 'Space', target: { tagName: 'DIV' } }), true);
});

test('space keeps the native behavior of interactive and editable targets', () => {
  for (const target of [
    { tagName: 'INPUT' },
    { tagName: 'TEXTAREA' },
    { tagName: 'SELECT' },
    { tagName: 'BUTTON' },
    { tagName: 'A' },
    { tagName: 'DIV', isContentEditable: true },
  ]) {
    assert.equal(shouldTogglePlayback({ key: ' ', code: 'Space', target }), false);
  }
});

test('space ignores repeats and modified shortcuts', () => {
  assert.equal(shouldTogglePlayback({ key: ' ', code: 'Space', repeat: true }), false);
  assert.equal(shouldTogglePlayback({ key: ' ', code: 'Space', ctrlKey: true }), false);
  assert.equal(shouldTogglePlayback({ key: ' ', code: 'Space', metaKey: true }), false);
  assert.equal(shouldTogglePlayback({ key: ' ', code: 'Space', altKey: true }), false);
  assert.equal(shouldTogglePlayback({ key: ' ', code: 'Space', shiftKey: true }), false);
});

test('other keys do not toggle playback', () => {
  assert.equal(shouldTogglePlayback({ key: 'Enter', code: 'Enter' }), false);
});
