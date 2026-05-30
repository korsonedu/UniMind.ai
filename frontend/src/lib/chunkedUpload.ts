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

export interface OSSSignatureResult {
  upload_url: string;
  object_key: string;
  file_name: string;
  expires_in: number;
}

export async function getOSSSignature(fileName: string, fileType: string, contentType: string): Promise<OSSSignatureResult> {
  const res = await api.post('/courses/oss/signature/', {
    file_name: fileName,
    file_type: fileType,
    content_type: contentType,
  });
  return res.data;
}

export async function uploadToOSS(uploadUrl: string, file: File, onProgress?: (percent: number) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('PUT', uploadUrl, true);
    xhr.setRequestHeader('Content-Type', file.type);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };

    xhr.onload = () => {
      if (xhr.status === 200) {
        resolve();
      } else {
        reject(new Error(`上传失败: ${xhr.status}`));
      }
    };

    xhr.onerror = () => reject(new Error('上传失败'));
    xhr.send(file);
  });
}

export async function completeOSSUpload(objectKey: string, fileName: string, fileType: string, fileSize: number) {
  const res = await api.post('/courses/oss/complete/', {
    object_key: objectKey,
    file_name: fileName,
    file_type: fileType,
    file_size: fileSize,
  });
  return res.data;
}

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

  // 使用 OSS 直传（所有文件）
  if (onStatus) onStatus({ phase: 'init', totalChunks: 1, resumed: false });

  try {
    // 1. 获取签名 URL
    const signature = await getOSSSignature(video.name, 'video', video.type || 'video/mp4');

    // 2. 直传到 OSS
    await uploadToOSS(signature.upload_url, video, (percent) => {
      if (onProgress) onProgress(Math.round(percent * 0.9)); // 90% for upload
    });

    // 3. 通知后端上传完成
    const result = await completeOSSUpload(
      signature.object_key,
      video.name,
      'video',
      video.size
    );

    // 4. 创建课程记录
    const fd = new FormData();
    applyCommonFields(fd);
    fd.append('video_file_url', result.file_info.url);
    fd.append('video_object_key', signature.object_key);
    if (cover) fd.append('cover_image', cover);
    if (courseware) fd.append('courseware', courseware);

    const res = await api.post('/courses/', fd, { signal });
    if (onProgress) onProgress(100);
    if (onStatus) onStatus({ phase: 'completed', uploadId: 'oss-direct', totalChunks: 1 });
    clearStoredUploadId();
    return res.data;
  } catch (error) {
    console.error('OSS 直传失败，回退到分片上传:', error);
    // 回退到原来的分片上传逻辑
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
