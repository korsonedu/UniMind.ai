import assert from 'node:assert/strict';
import test from 'node:test';
import { captureCourseFrame, CourseFrameBuffer } from '../src/lib/courseVisual.ts';

test('comparison buffer retains at most eight recent full frames', () => {
  const buffer = new CourseFrameBuffer();
  for (let time = 0; time <= 12; time += .25) buffer.add({ video_seconds: time, image: `full-frame-${time}` });
  assert.equal(buffer.frames.length, 8);
  assert.equal(buffer.frames[0].video_seconds, 5);
  assert.equal(buffer.previous(13)?.video_seconds, 5);
  assert.equal(buffer.previous(30), undefined);
  assert.ok(buffer.frames.every(frame => Object.keys(frame).sort().join() === 'image,video_seconds'));
});

test('seeking clears previous frames', () => {
  const buffer = new CourseFrameBuffer();
  buffer.add({ video_seconds: 100, image: 'before' });
  buffer.clear();
  assert.equal(buffer.previous(101), undefined);
  buffer.add({ video_seconds: 100, image: 'before' });
  buffer.add({ video_seconds: 2, image: 'after' });
  assert.equal(buffer.frames.length, 1);
  assert.equal(buffer.frames[0].image, 'after');
});

test('capture uses the entire unmarked video image and freezes its time', () => {
  const operations: unknown[][] = [];
  const canvas = { width: 0, height: 0, getContext: () => ({ drawImage: (...args: unknown[]) => operations.push(args) }), toDataURL: () => 'data:image/jpeg;base64,fixture' };
  const saved = globalThis.document;
  Object.defineProperty(globalThis, 'document', { configurable: true, value: { createElement: () => canvas } });
  try {
    const video = { currentTime: 123.25, videoWidth: 1920, videoHeight: 1080, readyState: 2, seeking: false };
    const frame = captureCourseFrame(video as HTMLVideoElement);
    video.currentTime = 130;
    assert.deepEqual(frame, { video_seconds: 123.25, image: 'data:image/jpeg;base64,fixture' });
    assert.deepEqual([canvas.width, canvas.height], [1280, 720]);
    assert.deepEqual(operations, [[video, 0, 0, 1280, 720]]);
  } finally { Object.defineProperty(globalThis, 'document', { configurable: true, value: saved }); }
});

test('capture rejects an unavailable or seeking video', () => {
  assert.throws(() => captureCourseFrame(null), /尚未加载/);
  assert.throws(() => captureCourseFrame({ readyState: 1 } as HTMLVideoElement), /尚未解码/);
  assert.throws(() => captureCourseFrame({ readyState: 2, seeking: true } as HTMLVideoElement), /跳转完成/);
});
