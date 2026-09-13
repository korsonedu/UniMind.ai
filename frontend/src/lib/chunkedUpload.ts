import api from '@/lib/api';
import { toast } from 'sonner';

// ── Types ──

export interface OSSMultipartInitResult {
  upload_id: string;
  object_key: string;
  part_size: number;
  total_parts: number;
  signed_urls: string[];
}

export type UploadStatus =
  | { phase: 'init'; totalParts: number }
  | { phase: 'uploading'; partIndex: number; totalParts: number; uploadedCount: number }
  | { phase: 'retrying'; partIndex: number; totalParts: number; attempt: number; maxAttempts: number }
  | { phase: 'completing'; totalParts: number }
  | { phase: 'completed'; totalParts: number };

export interface CreateCourseParams {
  title: string;
  description: string;
  eloReward: number;
  albumObj?: string;
  knowledgePoint?: string;
  tags?: string[];
  video: File;
  cover?: File | null;
  courseware?: File | null;
  referenceMaterials?: File | null;
  onProgress?: (percent: number) => void;
  onStatus?: (status: UploadStatus) => void;
  signal?: AbortSignal;
}

// ── Helpers ──

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

async function uploadPartWithRetry(
  signedUrl: string,
  chunk: Blob,
  retries = 4,
  signal?: AbortSignal,
): Promise<string> {
  let lastError: unknown;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const resp = await fetch(signedUrl, {
        method: 'PUT',
        body: chunk,
        signal,
      });
      if (!resp.ok) throw new Error(`分片上传失败（HTTP ${resp.status}）`);
      const etag = resp.headers.get('ETag') || '';
      return etag;
    } catch (err) {
      // fetch 网络中断抛的是 TypeError("Failed to fetch")，对用户没有意义，换成可读提示
      lastError = err instanceof TypeError
        ? new Error('视频上传中断，请检查网络后重试')
        : err;
      if (attempt < retries) await sleep(500 * 2 ** attempt);
    }
  }
  throw lastError;
}

// ── Screen Wake Lock（上传期间阻止屏幕自动休眠，避免长时间传输被中断）──

type WakeLockSentinelLike = { release: () => Promise<void> };
let wakeLock: WakeLockSentinelLike | null = null;

async function acquireWakeLock() {
  try {
    const wl = (navigator as unknown as {
      wakeLock?: { request: (type: string) => Promise<WakeLockSentinelLike> };
    }).wakeLock;
    if (!wl?.request) return;
    wakeLock = await wl.request('screen');
  } catch {
    // 浏览器不支持或被拒绝，忽略
  }
}

function releaseWakeLock() {
  try {
    wakeLock?.release?.();
  } catch {
    // ignore
  }
  wakeLock = null;
}

// ── 断点续传记录（localStorage）──

const PENDING_PREFIX = 'pending_course_upload:';
const PENDING_TTL_MS = 7 * 24 * 3600 * 1000;

interface PendingUpload {
  uploadId: string;
  objectKey: string;
  partSize: number;
  totalParts: number;
  createdAt: number;
}

function fileKeyOf(file: File): string {
  return `${file.name}|${file.size}|${file.lastModified}`;
}

function loadPendingUpload(key: string): PendingUpload | null {
  try {
    const raw = localStorage.getItem(PENDING_PREFIX + key);
    if (!raw) return null;
    const data = JSON.parse(raw) as PendingUpload;
    if (!data?.uploadId || Date.now() - (data.createdAt || 0) > PENDING_TTL_MS) {
      localStorage.removeItem(PENDING_PREFIX + key);
      return null;
    }
    return data;
  } catch {
    return null;
  }
}

function savePendingUpload(key: string, data: PendingUpload) {
  try {
    localStorage.setItem(PENDING_PREFIX + key, JSON.stringify(data));
  } catch {
    // 隐私模式或超出配额：续传能力降级，不影响本次上传
  }
}

function clearPendingUpload(key: string) {
  try {
    localStorage.removeItem(PENDING_PREFIX + key);
  } catch {
    // ignore
  }
}

// ── Main ──

export async function createCourseWithSmartUpload(params: CreateCourseParams) {
  await acquireWakeLock();
  try {
    return await runUpload(params);
  } finally {
    releaseWakeLock();
  }
}

async function runUpload(params: CreateCourseParams) {
  const {
    title, description, eloReward, albumObj, knowledgePoint, tags,
    video, cover, courseware, referenceMaterials,
    onProgress, onStatus, signal,
  } = params;

  // Step 1: 优先续传未完成的上传，否则重新初始化
  const fileKey = fileKeyOf(video);
  let upload_id = '';
  let object_key = '';
  let part_size = 0;
  let total_parts = 0;
  let signed_urls: string[] = [];
  let resumedParts: { number: number; etag: string }[] = [];
  let resumed = false;

  const saved = loadPendingUpload(fileKey);
  if (saved) {
    try {
      const res = await api.post('/courses/oss/multipart/resign/', {
        upload_id: saved.uploadId,
        object_key: saved.objectKey,
        total_parts: saved.totalParts,
      }, { signal });
      signed_urls = res.data.signed_urls;
      resumedParts = res.data.uploaded_parts || [];
      upload_id = saved.uploadId;
      object_key = saved.objectKey;
      part_size = saved.partSize;
      total_parts = saved.totalParts;
      resumed = true;
      const pct = total_parts ? Math.floor((resumedParts.length / total_parts) * 90) : 0;
      toast.info(`检测到未完成的上传，从 ${pct}% 继续`);
    } catch {
      // 分片已被 OSS 清理或记录过期，退回全新上传
      clearPendingUpload(fileKey);
    }
  }

  if (!resumed) {
    if (onStatus) onStatus({ phase: 'init', totalParts: 0 });
    const initRes = await api.post('/courses/oss/multipart/init/', {
      file_name: video.name,
      file_size: video.size,
    }, { signal });
    const init: OSSMultipartInitResult = initRes.data;
    ({ upload_id, object_key, part_size, total_parts, signed_urls } = init);
    savePendingUpload(fileKey, {
      uploadId: upload_id,
      objectKey: object_key,
      partSize: part_size,
      totalParts: total_parts,
      createdAt: Date.now(),
    });
  }
  if (onStatus) onStatus({ phase: 'init', totalParts: total_parts });

  // Step 2: Upload parts directly to OSS (3 concurrent)
  const CONCURRENCY = 3;
  const etags: { number: number; etag: string }[] = [...resumedParts];
  const uploadedNumbers = new Set(resumedParts.map(p => p.number));
  let uploadedCount = resumedParts.length;
  let firstError: unknown = null;

  const uploadOne = async (index: number) => {
    const start = index * part_size;
    const end = Math.min(start + part_size, video.size);
    const chunk = video.slice(start, end);

    if (onStatus) onStatus({ phase: 'uploading', partIndex: index, totalParts: total_parts, uploadedCount });

    const etag = await uploadPartWithRetry(signed_urls[index], chunk, 2, signal);
    etags.push({ number: index + 1, etag });
    uploadedCount++;
    if (onProgress) onProgress(Math.floor((uploadedCount / total_parts) * 90));
    if (onStatus) onStatus({ phase: 'uploading', partIndex: index, totalParts: total_parts, uploadedCount });
  };

  // 跳过已上传的分片，只补传缺失的
  const pending = Array.from({ length: total_parts }, (_, i) => i)
    .filter(i => !uploadedNumbers.has(i + 1));
  const worker = async () => {
    while (pending.length > 0 && !firstError) {
      if (signal?.aborted) { firstError = new DOMException('Abort', 'AbortError'); break; }
      const idx = pending.shift()!;
      try { await uploadOne(idx); } catch (err) { firstError = err; }
    }
  };

  const workers = Array.from({ length: Math.min(CONCURRENCY, Math.max(pending.length, 1)) }, () => worker());
  await Promise.all(workers);
  if (firstError) {
    const isCancelled = firstError instanceof DOMException && firstError.name === 'AbortError';
    if (isCancelled) {
      // 用户主动取消：释放 OSS 分片并清除续传记录
      await api.post('/courses/oss/multipart/abort/', { upload_id, object_key }).catch(() => {});
      clearPendingUpload(fileKey);
    }
    // 网络中断等其他失败：保留分片和记录，重选同一文件即可续传
    throw firstError;
  }

  // Step 3: Complete — send all metadata + other files to backend
  if (onStatus) onStatus({ phase: 'completing', totalParts: total_parts });

  // 按分片编号升序提交（续传时 etags 来自已传与新传两处）
  etags.sort((a, b) => a.number - b.number);

  const fd = new FormData();
  fd.append('upload_id', upload_id);
  fd.append('object_key', object_key);
  fd.append('parts', JSON.stringify(etags));
  fd.append('title', title);
  fd.append('description', description);
  fd.append('elo_reward', String(eloReward));
  if (albumObj && albumObj !== '0') fd.append('album_obj', albumObj);
  if (knowledgePoint && knowledgePoint !== '0') fd.append('knowledge_point', knowledgePoint);
  if (tags && tags.length > 0) fd.append('tags', JSON.stringify(tags));
  if (cover) fd.append('cover_image', cover);
  if (courseware) fd.append('courseware', courseware);
  if (referenceMaterials) fd.append('reference_materials', referenceMaterials);

  try {
    const res = await api.post('/courses/oss/multipart/complete/', fd, { signal });
    clearPendingUpload(fileKey);
    if (onProgress) onProgress(100);
    if (onStatus) onStatus({ phase: 'completed', totalParts: total_parts });
    return res.data;
  } catch (err) {
    // 分片已被合并，续传记录失去意义；这类失败多为专辑校验等业务错误
    clearPendingUpload(fileKey);
    throw err;
  }
}
