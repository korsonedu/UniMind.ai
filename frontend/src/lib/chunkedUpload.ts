import api from '@/lib/api';

export interface ChunkedUploadInitResult {
  upload_id: string;
  pipeline_task_id?: number;
  max_chunk_size?: number;
  uploaded_chunks?: number[];
  resumed?: boolean;
}

export interface ChunkedUploadConfig {
  file: File;
  chunkSize: number;
  concurrency?: number;
  retriesPerChunk?: number;
  signal?: AbortSignal;
  onProgress?: (percent: number) => void;
  onStatus?: (status: ChunkedUploadStatus) => void;
  alreadyUploadedChunkIndexes?: number[];
  init: () => Promise<ChunkedUploadInitResult>;
  uploadChunk: (uploadId: string, chunkIndex: number, chunk: Blob) => Promise<void>;
}

export interface ChunkedUploadRunResult {
  uploadId: string;
  pipelineTaskId?: number;
  uploadedChunks: number[];
  resumed: boolean;
}

export type ChunkedUploadStatus =
  | { phase: 'init'; uploadId?: string; pipelineTaskId?: number; totalChunks: number; resumed: boolean }
  | { phase: 'uploading'; pipelineTaskId?: number; chunkIndex: number; totalChunks: number; uploadedCount: number }
  | { phase: 'retrying'; pipelineTaskId?: number; chunkIndex: number; totalChunks: number; attempt: number; maxAttempts: number }
  | { phase: 'merging'; uploadId: string; pipelineTaskId?: number; totalChunks: number }
  | { phase: 'completed'; uploadId: string; pipelineTaskId?: number; totalChunks: number };

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export async function uploadFileInChunks(config: ChunkedUploadConfig): Promise<ChunkedUploadRunResult> {
  const {
    file,
    chunkSize,
    concurrency = 3,
    retriesPerChunk = 2,
    signal,
    onProgress,
    onStatus,
    alreadyUploadedChunkIndexes = [],
    init,
    uploadChunk,
  } = config;

  const totalChunks = Math.ceil(file.size / chunkSize);
  const initResult = await init();
  const uploadId = initResult.upload_id;
  const pipelineTaskId = initResult.pipeline_task_id;
  if (!uploadId) throw new Error('上传会话创建失败');
  if (onStatus) onStatus({ phase: 'init', uploadId, pipelineTaskId, totalChunks, resumed: !!initResult.resumed });

  const uploadedSet = new Set<number>(
    [...alreadyUploadedChunkIndexes, ...(initResult.uploaded_chunks || [])]
      .filter((idx) => Number.isInteger(idx) && idx >= 0 && idx < totalChunks)
      .map((idx) => Number(idx))
  );

  const pending: number[] = [];
  for (let i = 0; i < totalChunks; i++) {
    if (!uploadedSet.has(i)) pending.push(i);
  }

  let firstError: unknown = null;

  const uploadOne = async (index: number): Promise<void> => {
    const start = index * chunkSize;
    const end = Math.min(start + chunkSize, file.size);
    const chunkBlob = file.slice(start, end);

    let attempt = 0;
    let done = false;
    let lastError: unknown = null;

    while (attempt <= retriesPerChunk && !done) {
      try {
        await uploadChunk(uploadId, index, chunkBlob);
        done = true;
      } catch (err) {
        lastError = err;
        attempt += 1;
        if (attempt <= retriesPerChunk) {
          if (onStatus) {
            onStatus({
              phase: 'retrying',
              pipelineTaskId,
              chunkIndex: index,
              totalChunks,
              attempt,
              maxAttempts: retriesPerChunk + 1,
            });
          }
          await sleep(400 * (2 ** (attempt - 1)));
        }
      }
    }

    if (!done) throw lastError || new Error(`分片 ${index} 上传失败`);

    uploadedSet.add(index);
    const doneCount = uploadedSet.size;
    if (onProgress) onProgress(Math.floor((doneCount / totalChunks) * 95));
    if (onStatus) onStatus({ phase: 'uploading', pipelineTaskId, chunkIndex: index, totalChunks, uploadedCount: uploadedSet.size });
  };

  const worker = async (): Promise<void> => {
    while (pending.length > 0 && !firstError) {
      if (signal?.aborted) {
        firstError = new DOMException('上传已取消', 'AbortError');
        break;
      }
      const index = pending.shift()!;
      try {
        await uploadOne(index);
      } catch (err) {
        firstError = err;
      }
    }
  };

  const workers: Promise<void>[] = [];
  for (let w = 0; w < Math.min(concurrency, pending.length); w++) {
    workers.push(worker());
  }
  await Promise.all(workers);

  if (firstError) throw firstError;

  return {
    uploadId,
    pipelineTaskId,
    uploadedChunks: Array.from(uploadedSet).sort((a, b) => a - b),
    resumed: !!initResult.resumed,
  };
}

export interface CreateCourseWithUploadParams {
  title: string;
  description: string;
  eloReward: number;
  albumObj?: string;
  knowledgePoint?: string;
  tags?: string[];
  video: File;
  cover?: File | null;
  courseware?: File | null;
  thresholdBytes: number;
  chunkSizeBytes: number;
  onProgress?: (percent: number) => void;
  onStatus?: (status: ChunkedUploadStatus) => void;
  resumeStorageKey?: string;
  signal?: AbortSignal;
}

export async function createCourseWithSmartUpload(params: CreateCourseWithUploadParams) {
  const {
    title,
    description,
    eloReward,
    albumObj,
    knowledgePoint,
    tags,
    video,
    cover,
    courseware,
    thresholdBytes,
    chunkSizeBytes,
    onProgress,
    onStatus,
    resumeStorageKey,
    signal,
  } = params;

  const canUseStorage = typeof window !== 'undefined';
  const effectiveResumeStorageKey = resumeStorageKey || `course-upload:${video.name}:${video.size}:${video.lastModified}`;
  const getStoredUploadId = () => {
    if (!canUseStorage) return '';
    try {
      return window.localStorage.getItem(effectiveResumeStorageKey) || '';
    } catch {
      return '';
    }
  };
  const setStoredUploadId = (uploadId: string) => {
    if (!canUseStorage || !uploadId) return;
    try {
      window.localStorage.setItem(effectiveResumeStorageKey, uploadId);
    } catch {
      // Ignore storage failures (private mode, quota, etc.)
    }
  };
  const clearStoredUploadId = () => {
    if (!canUseStorage) return;
    try {
      window.localStorage.removeItem(effectiveResumeStorageKey);
    } catch {
      // Ignore storage failures.
    }
  };

  const applyCommonFields = (fd: FormData) => {
    fd.append('title', title);
    fd.append('description', description);
    fd.append('elo_reward', String(eloReward));
    if (albumObj && albumObj !== '0') fd.append('album_obj', albumObj);
    if (knowledgePoint && knowledgePoint !== '0') fd.append('knowledge_point', knowledgePoint);
    if (tags && tags.length > 0) fd.append('tags', JSON.stringify(tags));
  };

  if (video.size <= thresholdBytes) {
    if (onStatus) onStatus({ phase: 'init', totalChunks: 1, resumed: false });
    const fd = new FormData();
    applyCommonFields(fd);
    fd.append('video_file', video);
    if (cover) fd.append('cover_image', cover);
    if (courseware) fd.append('courseware', courseware);
    const res = await api.post('/courses/', fd, {
      signal,
      onUploadProgress: (p) => {
        if (p.total && onProgress) onProgress(Math.round((p.loaded / p.total) * 100));
      },
    });
    if (onStatus) onStatus({ phase: 'completed', uploadId: 'single-part', totalChunks: 1 });
    clearStoredUploadId();
    return res.data;
  }

  const uploadResult = await uploadFileInChunks({
    file: video,
    chunkSize: chunkSizeBytes,
    signal,
    onProgress,
    onStatus,
    init: async () => {
      const totalChunks = Math.ceil(video.size / chunkSizeBytes);
      const resumeUploadId = getStoredUploadId();
      const res = await api.post('/courses/chunked/init/', {
        file_name: video.name,
        total_size: video.size,
        chunk_size: chunkSizeBytes,
        total_chunks: totalChunks,
        mime_type: video.type || 'application/octet-stream',
        resume_upload_id: resumeUploadId || undefined,
      });
      if (res.data?.upload_id) setStoredUploadId(res.data.upload_id);
      return res.data as ChunkedUploadInitResult;
    },
    uploadChunk: async (id, index, chunk) => {
      const fd = new FormData();
      fd.append('chunk_index', String(index));
      fd.append('chunk', chunk, `${video.name}.part${index}`);
      await api.post(`/courses/chunked/${id}/chunk/`, fd, {
        signal,
      });
    },
  });

  const completeFd = new FormData();
  applyCommonFields(completeFd);
  if (cover) completeFd.append('cover_image', cover);
  if (courseware) completeFd.append('courseware', courseware);
  if (onStatus) {
    onStatus({
      phase: 'merging',
      uploadId: uploadResult.uploadId,
      pipelineTaskId: uploadResult.pipelineTaskId,
      totalChunks: Math.ceil(video.size / chunkSizeBytes),
    });
  }
  const res = await api.post(`/courses/chunked/${uploadResult.uploadId}/complete/`, completeFd, {
    signal,
  });
  if (onStatus) {
    onStatus({
      phase: 'completed',
      uploadId: uploadResult.uploadId,
      pipelineTaskId: uploadResult.pipelineTaskId,
      totalChunks: Math.ceil(video.size / chunkSizeBytes),
    });
  }
  clearStoredUploadId();
  if (onProgress) onProgress(100);
  return res.data;
}
