import assert from 'node:assert/strict';
import test from 'node:test';
import { previewDirectoryWidth, resolveDirectoryWidth } from '../src/hooks/useDirectoryWidth.ts';

test('侧栏在最小宽度和收起阈值之间保持最小宽度', () => {
  assert.equal(previewDirectoryWidth(199, 100), 200);
  assert.equal(previewDirectoryWidth(101, 100), 200);
});

test('侧栏缩到一半后收起', () => {
  assert.equal(previewDirectoryWidth(100, 100), 0);
  assert.equal(previewDirectoryWidth(99, 100), 0);
});

test('未拖到一半就松手时回到最小宽度', () => {
  assert.equal(resolveDirectoryWidth(150, 100), 200);
});

test('所有可收起侧栏默认共享一半宽度阈值', () => {
  assert.equal(previewDirectoryWidth(101), 200);
  assert.equal(previewDirectoryWidth(100), 0);
  assert.equal(previewDirectoryWidth(99), 0);
});
