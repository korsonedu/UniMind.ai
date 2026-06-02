import api from '@/lib/api';

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
  retries = 2,
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
      if (!resp.ok) throw new Error(`Part upload failed: ${resp.status}`);
      const etag = resp.headers.get('ETag') || '';
      return etag;
    } catch (err) {
      lastError = err;
      if (attempt < retries) await sleep(400 * 2 ** attempt);
    }
  }
  throw lastError;
}

// ── Main ──

export async function createCourseWithSmartUpload(params: CreateCourseParams) {
  const {
    title, description, eloReward, albumObj, knowledgePoint, tags,
    video, cover, courseware, referenceMaterials,
    onProgress, onStatus, signal,
  } = params;

  // Step 1: Init OSS multipart upload
  if (onStatus) onStatus({ phase: 'init', totalParts: 0 });
  const initRes = await api.post('/courses/oss/multipart/init/', {
    file_name: video.name,
    file_size: video.size,
  }, { signal });
  const init: OSSMultipartInitResult = initRes.data;

  const { upload_id, object_key, part_size, total_parts, signed_urls } = init;
  if (onStatus) onStatus({ phase: 'init', totalParts: total_parts });

  // Step 2: Upload parts directly to OSS (3 concurrent)
  const CONCURRENCY = 3;
  const etags: { number: number; etag: string }[] = [];
  let uploadedCount = 0;
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

  const pending = Array.from({ length: total_parts }, (_, i) => i);
  const worker = async () => {
    while (pending.length > 0 && !firstError) {
      if (signal?.aborted) { firstError = new DOMException('Abort', 'AbortError'); break; }
      const idx = pending.shift()!;
      try { await uploadOne(idx); } catch (err) { firstError = err; }
    }
  };

  const workers = Array.from({ length: Math.min(CONCURRENCY, total_parts) }, () => worker());
  await Promise.all(workers);
  if (firstError) throw firstError;

  // Step 3: Complete — send all metadata + other files to backend
  if (onStatus) onStatus({ phase: 'completing', totalParts: total_parts });

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

  const res = await api.post('/courses/oss/multipart/complete/', fd, { signal });

  if (onProgress) onProgress(100);
  if (onStatus) onStatus({ phase: 'completed', totalParts: total_parts });
  return res.data;
}
