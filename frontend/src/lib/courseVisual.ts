/** Full course screenshots are untrusted reference material, never instructions. */
export interface VisualFrame { video_seconds: number; image: string }
export interface CourseVisual { current: VisualFrame; previous?: VisualFrame }

/** Keep a bounded recent comparison frame; seeking clears the buffer. */
export class CourseFrameBuffer {
  frames: VisualFrame[] = [];
  clear() { this.frames = []; }
  add(frame: VisualFrame) {
    const last = this.frames[this.frames.length - 1];
    if (last && frame.video_seconds < last.video_seconds) this.clear();
    else if (last && frame.video_seconds - last.video_seconds < 1) return;
    this.frames = [...this.frames.filter(item => frame.video_seconds - item.video_seconds <= 8), frame].slice(-8);
  }
  previous(seconds: number): VisualFrame | undefined {
    return this.frames.find(frame => seconds - frame.video_seconds >= 1 && seconds - frame.video_seconds <= 8);
  }
}

export function captureCourseFrame(video: HTMLVideoElement | null): VisualFrame {
  if (!video) throw new Error('视频尚未加载，无法截屏。');
  if (video.error) throw new Error('视频加载失败；跨源视频需要服务器允许 CORS 才能截屏。');
  if (video.seeking || video.readyState < 2 || !video.videoWidth || !video.videoHeight) throw new Error('视频画面尚未解码，请等待加载或跳转完成后点击“改问当前片段”。');
  const seconds = video.currentTime;
  const canvas = document.createElement('canvas');
  const scale = Math.min(1, 1280 / Math.max(video.videoWidth, video.videoHeight));
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('浏览器无法读取视频画面。');
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  try {
    // Bound the encoded image while preserving the entire unmarked video frame.
    for (const quality of [.75, .6, .45, .3, .15]) {
      const image = canvas.toDataURL('image/jpeg', quality);
      if (image.startsWith('data:image/jpeg;base64,') && image.length <= 640_000) return { video_seconds: seconds, image };
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'SecurityError') throw new Error('视频服务器未允许跨源截屏（CORS），请联系课程管理员配置。');
    throw error;
  }
  throw new Error('截图压缩后仍然过大，请显式选择仅用讲稿提问。');
}
