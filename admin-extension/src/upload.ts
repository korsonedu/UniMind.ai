import type { Gateway } from './types';

export async function upload(api: Gateway, course: number, field: string, file: File, progress: (percent: number) => void) {
  const job = await api<{ ticket: string; part_size: number; urls: string[] }>('uploads.start',
    { course, field, name: file.name, size: file.size, request_id: crypto.randomUUID() });
  try {
    for (let index = 0; index < job.urls.length; index++) {
      const body = file.slice(index * job.part_size, (index + 1) * job.part_size);
      let failure: unknown;
      for (let attempt = 0; attempt < 3; attempt++) {
        try {
          const result = await fetch(job.urls[index]!, { method: 'PUT', body, signal: AbortSignal.timeout(120000) });
          if (!result.ok) throw new Error('文件分片上传失败。');
          failure = undefined;
          break;
        } catch (error) { failure = error; }
      }
      if (failure) throw failure;
      progress(Math.round((index + 1) / job.urls.length * 95));
    }
    await api('uploads.complete', { ticket: job.ticket, request_id: crypto.randomUUID() });
    progress(100);
  } catch (error) {
    // Best effort: a lost completion response may already have attached the file.
    await api('uploads.cancel', { ticket: job.ticket, request_id: crypto.randomUUID() }).catch(() => {});
    throw error;
  }
}
