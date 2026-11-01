export function lessonSplitBounds(available: number, viewportHeight: number, aspectRatio: number, sidebarMinimum: number, gap: number, expanded = false) {
  const max = Math.max(0, Math.min(expanded ? Infinity : viewportHeight * .7 * aspectRatio, available - gap - sidebarMinimum));
  // Keep both columns useful. Portrait media may naturally be narrower than 320px.
  const min = Math.min(max, Math.max(320, available - gap - 640));
  return { min, max };
}

export function clampLessonWidth(value: number, bounds: { min: number; max: number }) {
  return Math.min(bounds.max, Math.max(bounds.min, value));
}

export function lessonDragBounds(available: number, gap: number, readableBounds: { min: number; max: number }) {
  const max = Math.max(0, available - gap - 32);
  return { min: Math.min(readableBounds.min, max), max };
}

export function isLessonSidebarNarrow(videoWidth: number, available: number, gap: number) {
  return available - gap - videoWidth <= 80;
}
