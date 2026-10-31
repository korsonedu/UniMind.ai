import assert from 'node:assert/strict';
import test from 'node:test';
import { clampLessonWidth, isLessonSidebarNarrow, lessonDragBounds, lessonSplitBounds } from '../src/components/course/lessonSplitBounds.ts';

test('desktop split trades real video width for a bounded readable sidebar', () => {
  const available = 1356;
  const bounds = lessonSplitBounds(available, 1080, 4 / 3, 320, 28);
  assert.deepEqual(bounds, { min: 688, max: 1008 });
  for (const value of [-100, 688, 800, 1008, 5000]) {
    const width = clampLessonWidth(value, bounds);
    const sidebar = available - 28 - width;
    assert.ok(sidebar >= 320 && sidebar <= 640);
    assert.ok(width / (4 / 3) <= 1080 * .7);
  }
  assert.equal(clampLessonWidth(1008 - 100, bounds), 908);
  assert.equal(clampLessonWidth(908 + 100, bounds), 1008);
});

test('available width limits landscape video before the height cap', () => {
  assert.deepEqual(lessonSplitBounds(900, 900, 16 / 9, 300, 20), { min: 320, max: 580 });
});

test('portrait or short windows keep their native ratio without impossible minimums', () => {
  const portrait = lessonSplitBounds(800, 600, 9 / 16, 320, 28);
  assert.deepEqual(portrait, { min: 236.25, max: 236.25 });
  assert.equal(clampLessonWidth(1000, portrait), 236.25);
  assert.deepEqual(lessonSplitBounds(200, 600, 4 / 3, 320, 28), { min: 0, max: 0 });
});

test('divider follows the drag into a real narrow sidebar beyond the normal video cap', () => {
  const bounds = lessonSplitBounds(1356, 1080, 4 / 3, 320, 28);
  const dragging = lessonDragBounds(1356, 28, bounds);
  assert.deepEqual(dragging, { min: 688, max: 1296 });
  assert.equal(clampLessonWidth(1008 + 120, dragging), 1128, 'line and video continue moving together');
  assert.equal(isLessonSidebarNarrow(1128, 1356, 28), false, 'a 200px sidebar does not trigger collapse');
  assert.equal(isLessonSidebarNarrow(1247, 1356, 28), false, '81px remains outside the target');
  assert.equal(isLessonSidebarNarrow(1248, 1356, 28), true, 'only the final 80px activates the hint');
  assert.equal(1356 - 28 - clampLessonWidth(5000, dragging), 32, 'edge keeps only a 32px target strip');
  assert.equal(clampLessonWidth(1128, bounds), 1008, 'release outside target returns a readable width');
});

test('manual expansion and collapse can use the entire parent beyond the compact height cap', () => {
  const full = 1568;
  const compact = 720 * .7 * (16 / 9) + 320 + 28;
  const normal = lessonSplitBounds(compact, 720, 16 / 9, 320, 28);
  const manual = lessonSplitBounds(full, 720, 16 / 9, 320, 28, true);
  assert.equal(manual.max, 1220);
  assert.ok(manual.max > normal.max, 'manual width no longer stops at 70dvh');
  const rightEdge = lessonDragBounds(full, 28, normal);
  assert.equal(rightEdge.max, 1508);
  assert.ok(full >= rightEdge.max, 'hiding the sidebar never shrinks the video');
  assert.equal(full - rightEdge.max, 28 + 32, 'collapse reclaims both gap and narrow strip');
  assert.equal(clampLessonWidth(normal.max, rightEdge), normal.max, 'switching budgets keeps the line at its current width');
  assert.equal(lessonSplitBounds(compact, 720, 16 / 9, 320, 28).max, normal.max, 'restoring compact mode restores its reading width');
});
