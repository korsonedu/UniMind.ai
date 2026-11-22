import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import test from 'node:test';
import ts from 'typescript';
import type { SidebarResizeHandle } from '../src/components/SidebarResizeHandle.tsx';
import * as sidebarLayout from '../src/lib/rightSidebarLayout.ts';
import { clampSidebarWidth, COLLAPSE_THRESHOLD, fullscreenSnapThreshold, maxSplitWidth, MIN_MAIN_WIDTH, MIN_SIDEBAR_WIDTH, sidebarDragPreview } from '../src/lib/rightSidebarLayout.ts';

test('comfortable split widths use the workspace budget without the old drawer cap', () => {
  assert.equal(maxSplitWidth(1400), 1050);
  assert.equal(maxSplitWidth(1000), 720);
  assert.equal(maxSplitWidth(768), 488);
  assert.equal(clampSidebarWidth(900, 1400), 900);
  assert.equal(clampSidebarWidth(1100, 1000), 720);
  assert.equal(clampSidebarWidth(100, 1400), MIN_SIDEBAR_WIDTH);
});

test('narrow and empty workspaces never invert the minimum and maximum', () => {
  for (const available of [0, 100, 319, 320, 400, 599, 600, 601, 710, 1000, 2000]) {
    const max = maxSplitWidth(available);
    const min = Math.min(MIN_SIDEBAR_WIDTH, available);
    assert.ok(min <= max && max <= available);
    assert.ok(fullscreenSnapThreshold(available) >= max);
    for (const width of [-100, 0, 160, 320, 480, 680, 900, 5000]) {
      const clamped = clampSidebarWidth(width, available);
      assert.ok(clamped >= min && clamped <= max);
      if (available >= MIN_SIDEBAR_WIDTH + MIN_MAIN_WIDTH) assert.ok(available - clamped >= MIN_MAIN_WIDTH);
    }
  }
});

test('dragging follows every pixel, including beyond the usable split limit', () => {
  for (const width of [320, 321, 400, 641, 800, 1049, 1050]) {
    assert.deepEqual(sidebarDragPreview(width, 1400), { width, snap: null });
  }
  assert.deepEqual(sidebarDragPreview(1051, 1400), { width: 1051, snap: 'fullscreen' });
  assert.deepEqual(sidebarDragPreview(1350, 1400), { width: 1350, snap: 'fullscreen' });
  assert.deepEqual(sidebarDragPreview(2000, 1400), { width: 1400, snap: 'fullscreen' });
  assert.deepEqual(sidebarDragPreview(-100, 1400), { width: 0, snap: 'collapse' });
});

test('both snap zones cancel as soon as the pointer returns to split space', () => {
  assert.equal(sidebarDragPreview(COLLAPSE_THRESHOLD, 1000).snap, 'collapse');
  assert.equal(sidebarDragPreview(COLLAPSE_THRESHOLD + 1, 1000).snap, null);
  assert.equal(sidebarDragPreview(200, 1000).width, 200, 'subminimum previews remain continuous until release');
  assert.equal(clampSidebarWidth(200, 1000), 320, 'release restores the readable minimum');
  const threshold = fullscreenSnapThreshold(1000);
  assert.equal(sidebarDragPreview(threshold + 1, 1000).snap, 'fullscreen');
  assert.equal(sidebarDragPreview(threshold, 1000).snap, null);
  assert.deepEqual(sidebarDragPreview(650, 1000), { width: 650, snap: null }, 'dragging out of fullscreen reaches split space');
});

// Execute the real pointer handlers without mounting a DOM or running effects.
function resizeHandle(fullscreen = false) {
  const require = createRequire(import.meta.url);
  const source = readFileSync(new URL('../src/components/SidebarResizeHandle.tsx', import.meta.url), 'utf8');
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  });
  const exports = {} as { SidebarResizeHandle: typeof SidebarResizeHandle };
  const dependencies = {
    react: { useRef: (current: unknown) => ({ current }), useEffect: () => {} },
    '@/i18n': { t: (value: string) => value, useLocale: () => {} },
    '@/lib/rightSidebarLayout': sidebarLayout,
  };
  new Function('require', 'exports', outputText)(
    (name: string) => name in dependencies ? dependencies[name as keyof typeof dependencies] : require(name),
    exports,
  );
  const commits: [number, boolean][] = [];
  const previews: (sidebarLayout.SidebarDragPreview | null)[] = [];
  const handle = {
    focus: () => {},
    setPointerCapture: () => {},
    releasePointerCapture: () => {},
  };
  const element = exports.SidebarResizeHandle({
    width: fullscreen ? 1400 : 400, splitWidth: 400, containerWidth: 1400, fullscreen, preview: null,
    onPreview: (next: sidebarLayout.SidebarDragPreview | null) => previews.push(next),
    onCommit: (width: number, nextFullscreen: boolean) => commits.push([width, nextFullscreen]),
    onCollapse: () => assert.fail('this gesture must not collapse the sidebar'),
  });
  const pointer = (clientX: number) => ({ clientX, button: 0, pointerId: 1, currentTarget: handle, preventDefault() {} });
  return { props: element.props, pointer, commits, previews };
}

test('a sweep through split widths into fullscreen remembers the width before the drag', () => {
  const { props, pointer, commits, previews } = resizeHandle();
  props.onPointerDown(pointer(1000));
  for (const x of [900, 700, 500, 350, 349, 100, 0]) props.onPointerMove(pointer(x));
  assert.deepEqual(previews.at(-1), { width: 1400, snap: 'fullscreen' });
  props.onPointerUp(pointer(0));
  assert.deepEqual(commits, [[400, true]]);
  assert.equal(previews.at(-1), null);
});

test('release in split space commits the released width, including when leaving fullscreen', () => {
  for (const fullscreen of [false, true]) {
    for (const width of [650, 200]) {
      const { props, pointer, commits } = resizeHandle(fullscreen);
      const startX = fullscreen ? 0 : 1000;
      const endX = 1400 - width;
      props.onPointerDown(pointer(startX));
      props.onPointerMove(pointer(endX));
      props.onPointerUp(pointer(endX));
      assert.deepEqual(commits, [[Math.max(MIN_SIDEBAR_WIDTH, width), false]]);
    }
  }
});

test('returning from the fullscreen snap zone before release commits a split width', () => {
  const { props, pointer, commits } = resizeHandle();
  props.onPointerDown(pointer(1000));
  props.onPointerMove(pointer(0));
  props.onPointerMove(pointer(750));
  props.onPointerUp(pointer(750));
  assert.deepEqual(commits, [[650, false]]);
});

test('fullscreen controls restore the remembered split width', () => {
  const { props, commits } = resizeHandle(true);
  props.onDoubleClick();
  props.onKeyDown({ key: 'Enter', preventDefault() {} });
  assert.deepEqual(commits, [[400, false], [400, false]]);
});
