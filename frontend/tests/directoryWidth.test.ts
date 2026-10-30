import assert from 'node:assert/strict';
import test from 'node:test';
import { previewDirectoryWidth, resolveDirectoryWidth } from '../src/hooks/useDirectoryWidth.ts';

test('拖拽低于最小宽度时保持最小宽度', () => {
  assert.equal(previewDirectoryWidth(179), 180);
  assert.equal(previewDirectoryWidth(91), 180);
  assert.equal(previewDirectoryWidth(400), 288);
});

test('侧栏缩到最小宽度一半后收起', () => {
  assert.equal(previewDirectoryWidth(90), 0);
  assert.equal(previewDirectoryWidth(89), 0);
});

test('未拖到一半就松手时回到最小宽度', () => {
  assert.equal(resolveDirectoryWidth(120), 180);
  assert.equal(resolveDirectoryWidth(89), 0);
});
