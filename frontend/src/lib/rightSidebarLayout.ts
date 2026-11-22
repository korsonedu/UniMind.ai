export const MIN_SIDEBAR_WIDTH = 320;
export const COLLAPSE_THRESHOLD = 160;
export const MIN_MAIN_WIDTH = 280;
export const MAX_SPLIT_RATIO = 0.75;

export type SidebarSnap = 'fullscreen' | 'collapse' | null;
export type SidebarDragPreview = { width: number; snap: SidebarSnap };

export function maxSplitWidth(containerWidth: number) {
  const available = Math.max(0, containerWidth);
  const min = Math.min(MIN_SIDEBAR_WIDTH, available);
  return Math.max(min, Math.min(Math.floor(available * MAX_SPLIT_RATIO), available - MIN_MAIN_WIDTH));
}

export function clampSidebarWidth(width: number, containerWidth: number) {
  const min = Math.min(MIN_SIDEBAR_WIDTH, Math.max(0, containerWidth));
  return Math.min(maxSplitWidth(containerWidth), Math.max(min, width));
}

export function fullscreenSnapThreshold(containerWidth: number) {
  // Beyond this width the main pane no longer has a comfortable split layout.
  return maxSplitWidth(containerWidth);
}

export function sidebarDragPreview(width: number, containerWidth: number): SidebarDragPreview {
  const next = Math.max(0, Math.min(containerWidth, width));
  return {
    width: next,
    snap: next <= COLLAPSE_THRESHOLD ? 'collapse' : next > fullscreenSnapThreshold(containerWidth) ? 'fullscreen' : null,
  };
}
