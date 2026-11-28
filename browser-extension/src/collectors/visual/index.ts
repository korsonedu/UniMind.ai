import type {
  PageCollectSnapshot,
  VideoRectInfo,
  VideoVisualPayload,
  VisualFrameSnapshot,
} from '../../shared/types';

export const MAX_FRAME_BYTES = 500 * 1024;
const MAX_IMAGE_EDGE = 1280;
const CAPTURE_TIMEOUT_MS = 1500;

export interface CropRect {
  sx: number;
  sy: number;
  sw: number;
  sh: number;
}

/** Convert CSS viewport coordinates into the visible screenshot's pixel coordinates. */
export function computeCropRect(
  rect: VideoRectInfo,
  imageWidth: number,
  imageHeight: number,
): CropRect | null {
  if (![rect.x, rect.y, rect.width, rect.height, imageWidth, imageHeight].every(Number.isFinite)
    || rect.width < 32 || rect.height < 32 || imageWidth <= 0 || imageHeight <= 0) return null;
  const scale = rect.viewportWidth > 0
    ? imageWidth / rect.viewportWidth
    : rect.devicePixelRatio;
  if (!Number.isFinite(scale) || scale <= 0) return null;
  const sx = Math.max(0, Math.min(imageWidth, rect.x * scale));
  const sy = Math.max(0, Math.min(imageHeight, rect.y * scale));
  const right = Math.max(0, Math.min(imageWidth, (rect.x + rect.width) * scale));
  const bottom = Math.max(0, Math.min(imageHeight, (rect.y + rect.height) * scale));
  return right > sx && bottom > sy ? { sx, sy, sw: right - sx, sh: bottom - sy } : null;
}

export function imageByteSize(image: string): number {
  const comma = image.indexOf(',');
  if (comma < 0 || !image.slice(0, comma).endsWith(';base64')) return Infinity;
  const encoded = image.slice(comma + 1);
  return Math.floor(encoded.length * 3 / 4) - (encoded.endsWith('==') ? 2 : encoded.endsWith('=') ? 1 : 0);
}

/** Choose the closest earlier usable frame, regardless of candidate order. */
export function pairFrames(
  current: VisualFrameSnapshot,
  candidates: Array<VisualFrameSnapshot | null | undefined>,
): VideoVisualPayload {
  const currentBytes = imageByteSize(current.image);
  const previous = candidates.filter((frame): frame is VisualFrameSnapshot => {
    if (!frame) return false;
    const elapsed = current.video_seconds - frame.video_seconds;
    const bytes = imageByteSize(frame.image);
    return elapsed > 0 && elapsed <= 15 && bytes <= MAX_FRAME_BYTES
      && currentBytes + bytes <= 1000 * 1024;
  }).sort((left, right) => right.video_seconds - left.video_seconds)[0];
  return { current, ...(previous ? { previous } : {}) };
}

async function blobDataUrl(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += 32768) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 32768));
  }
  return `data:image/jpeg;base64,${btoa(binary)}`;
}

export async function cropScreenshot(dataUrl: string, rect: VideoRectInfo): Promise<string> {
  const bitmap = await createImageBitmap(await (await fetch(dataUrl)).blob());
  try {
    const crop = computeCropRect(rect, bitmap.width, bitmap.height);
    if (!crop) throw new Error('播放器当前没有可见画面。');
    let scale = Math.min(1, MAX_IMAGE_EDGE / Math.max(crop.sw, crop.sh));
    // Very noisy frames may also need a smaller image after the three quality passes.
    for (let attempt = 0; attempt < 6; attempt++) {
      const canvas = new OffscreenCanvas(
        Math.max(1, Math.round(crop.sw * scale)),
        Math.max(1, Math.round(crop.sh * scale)),
      );
      const context = canvas.getContext('2d');
      if (!context) throw new Error('截图裁剪暂不可用。');
      context.drawImage(bitmap, crop.sx, crop.sy, crop.sw, crop.sh, 0, 0, canvas.width, canvas.height);
      for (const quality of [0.75, 0.6, 0.45]) {
        const blob = await canvas.convertToBlob({ type: 'image/jpeg', quality });
        if (blob.size <= MAX_FRAME_BYTES) return blobDataUrl(blob);
      }
      scale *= 0.7;
    }
    throw new Error('画面压缩后仍超过截图大小限制。');
  } finally {
    bitmap.close();
  }
}

interface CachedFrame {
  videoKey: string;
  frame: VisualFrameSnapshot;
}

const previousFrames = new Map<number, CachedFrame>();
const captureVersions = new Map<number, symbol>();

export function clearVisual(tabId: number): void {
  previousFrames.delete(tabId);
  captureVersions.delete(tabId);
}

async function captureFrame(tabId: number, rect: VideoRectInfo): Promise<string> {
  const tab = await chrome.tabs.get(tabId);
  if (!tab.active) throw new Error('当前视频标签页处于后台，已跳过截图。');
  const window = await chrome.windows?.get(tab.windowId);
  if (window?.state === 'minimized') throw new Error('视频窗口已最小化，已跳过截图。');
  const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'jpeg', quality: 85 });
  const activeTab = (await chrome.tabs.query({ active: true, windowId: tab.windowId }))[0];
  if (activeTab?.id !== tabId) throw new Error('截图期间切换了标签页，已跳过截图。');
  if (tab.url && activeTab.url && activeTab.url !== tab.url) {
    throw new Error('截图期间切换了视频页面，已跳过截图。');
  }
  return cropScreenshot(dataUrl, rect);
}

export async function collectVisual(
  tabId: number,
  snapshot: PageCollectSnapshot,
  timeoutMs = CAPTURE_TIMEOUT_MS,
): Promise<{ visual?: VideoVisualPayload; warnings: string[] }> {
  const videoKey = snapshot.descriptor.video_key;
  const cached = previousFrames.get(tabId);
  if (cached?.videoKey !== videoKey || cached.frame.video_seconds >= snapshot.video_seconds) {
    previousFrames.delete(tabId);
  }
  const version = Symbol();
  captureVersions.set(tabId, version);
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    let current = snapshot.direct_visual?.current;
    if (!current) {
      const rect = snapshot.cors_fallback_rect;
      if (!rect || rect.width < 32 || rect.height < 32) return { warnings: [] };
      const captureBudget = Math.min(CAPTURE_TIMEOUT_MS, timeoutMs);
      if (!(captureBudget > 0)) return { warnings: ['截图时间预算已耗尽，已继续获取其他上下文。'] };
      const image = await Promise.race([
        captureFrame(tabId, rect),
        new Promise<never>((_, reject) => {
          timer = setTimeout(() => reject(new Error('截图超时，已继续获取其他上下文。')), captureBudget);
        }),
      ]);
      current = { video_seconds: snapshot.video_seconds, image };
    }
    if (imageByteSize(current.image) > MAX_FRAME_BYTES) {
      return { warnings: ['当前画面超过截图大小限制，已跳过画面。'] };
    }
    if (captureVersions.get(tabId) !== version) return { warnings: [] };
    const visual = pairFrames(current, [
      snapshot.direct_visual?.previous,
      snapshot.previous_frame,
      previousFrames.get(tabId)?.frame,
    ]);
    previousFrames.set(tabId, { videoKey, frame: current });
    return { visual, warnings: [] };
  } catch (error) {
    return { warnings: [error instanceof Error ? error.message : '暂时无法截取视频画面。'] };
  } finally {
    if (timer !== undefined) clearTimeout(timer);
    if (captureVersions.get(tabId) === version) captureVersions.delete(tabId);
  }
}
