import { createFile } from 'mp4box';
import { apiUrl } from '../../lib/api';
import type { ActiveVideoDescriptor, DashAudioTrackMeta, TranscriptSegmentItem } from '../../shared/types';
import mediaRules from '../../../public/rules/dnr-media.json';

export const MAX_MEDIA_BYTES = 3.5 * 1024 * 1024;
export const MAX_AUDIO_BYTES = 4 * 1024 * 1024;

let headersInstallation: Promise<void> | undefined;

export function installMediaHeaders(): Promise<void> {
  if (!headersInstallation) {
    const rules = (mediaRules as chrome.declarativeNetRequest.Rule[]).map(rule => ({
      ...rule,
      id: 1000 + rule.id,
      condition: { ...rule.condition, initiatorDomains: [chrome.runtime.id] },
    }));
    headersInstallation = chrome.declarativeNetRequest.updateSessionRules({
      removeRuleIds: rules.map(rule => rule.id),
      addRules: rules,
    }).catch(error => { headersInstallation = undefined; throw error; });
  }
  return headersInstallation;
}

interface BoxLocation { type: string; start: number; size: number; headerSize: number }
export interface SidxReference {
  reference_type: number;
  referenced_size: number;
  subsegment_duration: number;
}
export interface SidxIndex {
  start: number;
  size: number;
  timescale: number;
  earliest_presentation_time: number;
  first_offset: number;
  references: SidxReference[];
}
export interface MediaSegment { startSeconds: number; endSeconds: number; byteStart: number; byteEnd: number }
export interface MediaRange {
  rangeStart: number;
  rangeEnd: number;
  clipStartSeconds: number;
  clipEndSeconds: number;
  narrowed: boolean;
}
export interface ParsedDashIndex { initBytes: ArrayBuffer; index: SidxIndex; segments: MediaSegment[] }
export interface AudioSnippetResult {
  available: boolean;
  segments: TranscriptSegmentItem[];
  warnings: string[];
  clipStartSeconds?: number;
}
interface AudioAuth { serverOrigin: string; token: string; fetcher?: typeof fetch }
export interface UploadAudioSnippetOptions extends AudioAuth {
  descriptor: ActiveVideoDescriptor;
  audio: Blob;
  clipStartSeconds: number;
  filename?: string;
}
export interface TranscribeDashOptions extends AudioAuth {
  descriptor: ActiveVideoDescriptor;
  track: DashAudioTrackMeta;
  targetSeconds: number;
}

function uint64(view: DataView, offset: number): number {
  const value = view.getUint32(offset) * 2 ** 32 + view.getUint32(offset + 4);
  if (!Number.isSafeInteger(value)) throw new Error('音频索引偏移超出可读取范围。');
  return value;
}

function boxesIn(buffer: ArrayBuffer): BoxLocation[] {
  const view = new DataView(buffer);
  const boxes: BoxLocation[] = [];
  for (let start = 0; start + 8 <= view.byteLength;) {
    const type = String.fromCharCode(...new Uint8Array(buffer, start + 4, 4));
    const shortSize = view.getUint32(start);
    const headerSize = shortSize === 1 ? 16 : 8;
    if (start + headerSize > view.byteLength) break;
    const size = shortSize === 1 ? uint64(view, start + 8) : shortSize || view.byteLength - start;
    if (size < headerSize || start + size > view.byteLength) break;
    boxes.push({ type, start, size, headerSize });
    start += size;
  }
  return boxes;
}

// ISO 14496-12 fallback for runtimes whose mp4box build does not expose references.
export function parseSidxFallback(buffer: ArrayBuffer): SidxIndex | null {
  const box = boxesIn(buffer).find(item => item.type === 'sidx');
  if (!box) return null;
  const view = new DataView(buffer, box.start, box.size);
  let offset = box.headerSize;
  if (offset + 12 > box.size) throw new Error('音频 sidx 索引不完整。');
  const version = view.getUint8(offset);
  if (version > 1) throw new Error('音频 sidx 版本暂不支持。');
  offset += 8;
  const timescale = view.getUint32(offset);
  offset += 4;
  const timeSize = version === 0 ? 4 : 8;
  if (offset + timeSize * 2 + 4 > box.size) throw new Error('音频 sidx 索引不完整。');
  const readTime = (at: number) => version === 0 ? view.getUint32(at) : uint64(view, at);
  const earliest_presentation_time = readTime(offset);
  const first_offset = readTime(offset + timeSize);
  offset += timeSize * 2 + 2;
  const count = view.getUint16(offset);
  offset += 2;
  if (offset + count * 12 > box.size) throw new Error('音频 sidx 引用不完整。');
  const references: SidxReference[] = [];
  for (let i = 0; i < count; i++, offset += 12) {
    const reference = view.getUint32(offset);
    references.push({
      reference_type: reference >>> 31,
      referenced_size: reference & 0x7fffffff,
      subsegment_duration: view.getUint32(offset + 4),
    });
  }
  return { start: box.start, size: box.size, timescale, earliest_presentation_time, first_offset, references };
}

function indexSegments(index: SidxIndex): MediaSegment[] {
  if (!(index.timescale > 0) || !index.references.length) throw new Error('音频 sidx 没有可用时间索引。');
  let byteStart = index.start + index.size + index.first_offset;
  let time = index.earliest_presentation_time;
  return index.references.map(reference => {
    if (reference.reference_type !== 0) throw new Error('音频使用嵌套 sidx 索引，已跳过局部转写。');
    if (!(reference.referenced_size > 0) || !(reference.subsegment_duration > 0)) {
      throw new Error('音频 sidx 子段为空。');
    }
    const byteEnd = byteStart + reference.referenced_size - 1;
    const endTime = time + reference.subsegment_duration;
    if (!Number.isSafeInteger(byteStart) || !Number.isSafeInteger(byteEnd) || !Number.isSafeInteger(endTime)) {
      throw new Error('音频 sidx 数值超出可读取范围。');
    }
    const segment = { byteStart, byteEnd, startSeconds: time / index.timescale, endSeconds: endTime / index.timescale };
    byteStart = byteEnd + 1;
    time = endTime;
    return segment;
  });
}

function hasEncryption(buffer: ArrayBuffer): boolean {
  const view = new DataView(buffer);
  const bytes = new Uint8Array(buffer);
  for (let offset = 4; offset + 4 <= bytes.length; offset++) {
    const type = String.fromCharCode(...bytes.subarray(offset, offset + 4));
    if (['pssh', 'sinf', 'enca', 'encv'].includes(type)) {
      const size = view.getUint32(offset - 4);
      if (size >= 8 && offset - 4 + size <= buffer.byteLength) return true;
    }
  }
  return false;
}

export function parseDashIndex(header: ArrayBuffer, initRange?: string): ParsedDashIndex {
  if (hasEncryption(header)) throw new Error('音频流已加密，已跳过 DASH 转写。');
  let index: SidxIndex | undefined;
  let initialization: BoxLocation[] = [];
  try {
    const file = createFile();
    const captureIndex = (value: Omit<SidxIndex, 'start'> & { start?: number }) => {
      if (value.start !== undefined) index = { ...value, start: value.start };
    };
    file.onSidx = captureIndex;
    const input = header.slice(0) as ArrayBuffer & { fileStart: number };
    input.fileStart = 0;
    file.appendBuffer(input);
    file.flush();
    if (!index && file.sidx) captureIndex(file.sidx);
    initialization = [file.ftyp, file.moov].flatMap(box => box?.start === undefined ? [] : [{
      type: box.type, start: box.start, size: box.size, headerSize: 8,
    }]);
  } catch {
    // Incomplete trailing media boxes must not hide a complete sidx in this header.
  }
  if (!index?.references?.length) index = parseSidxFallback(header) ?? undefined;
  if (!index) throw new Error('音频流没有可用 sidx 索引，已跳过 DASH 转写。');
  const explicit = /^0-(\d+)$/.exec(initRange ?? '');
  let initBytes: ArrayBuffer;
  if (explicit) {
    const end = Number(explicit[1]) + 1;
    if (!Number.isSafeInteger(end) || end > header.byteLength) throw new Error('音频初始化头不完整。');
    initBytes = header.slice(0, end);
  } else {
    if (initialization.length !== 2) initialization = boxesIn(header).filter(box => ['ftyp', 'moov'].includes(box.type));
    if (initialization.length !== 2) throw new Error('音频流缺少 ftyp 或 moov 初始化头。');
    const chunks = initialization.sort((a, b) => a.start - b.start).map(box => header.slice(box.start, box.start + box.size));
    const bytes = new Uint8Array(chunks.reduce((size, chunk) => size + chunk.byteLength, 0));
    let offset = 0;
    for (const chunk of chunks) { bytes.set(new Uint8Array(chunk), offset); offset += chunk.byteLength; }
    initBytes = bytes.buffer;
  }
  return { initBytes, index, segments: indexSegments(index) };
}

export function selectMediaRange(segments: MediaSegment[], targetSeconds: number, initSize = 0): MediaRange {
  if (!Number.isFinite(targetSeconds) || targetSeconds < 0) throw new Error('当前播放时间不可用。');
  const intersect = (before: number, after: number) => segments.filter(segment =>
    segment.endSeconds > Math.max(0, targetSeconds - before) && segment.startSeconds < targetSeconds + after);
  const size = (selected: MediaSegment[]) => selected.length ? selected.at(-1)!.byteEnd - selected[0]!.byteStart + 1 : 0;
  const limit = Math.min(MAX_MEDIA_BYTES, MAX_AUDIO_BYTES - initSize - 1);
  let selected = intersect(60, 15);
  let narrowed = false;
  if (size(selected) > limit) { selected = intersect(30, 10); narrowed = true; }
  // Large bitrates can still exceed the budget after narrowing. Keep complete adjacent subsegments.
  while (selected.length > 1 && size(selected) > limit) {
    const before = targetSeconds - selected[0]!.startSeconds;
    const after = selected.at(-1)!.endSeconds - targetSeconds;
    if (before >= after) selected.shift();
    else selected.pop();
  }
  if (!selected.length || size(selected) > limit) throw new Error('当前音频子段超过短音频上传大小，已跳过转写。');
  return {
    rangeStart: selected[0]!.byteStart, rangeEnd: selected.at(-1)!.byteEnd,
    clipStartSeconds: selected[0]!.startSeconds, clipEndSeconds: selected.at(-1)!.endSeconds, narrowed,
  };
}

export function concatenateSnippet(initBytes: ArrayBuffer, mediaBytes: ArrayBuffer): Blob {
  const blob = new Blob([initBytes, mediaBytes], { type: 'audio/mp4' });
  if (blob.size >= MAX_AUDIO_BYTES) throw new Error('音频切片超过上传大小，已跳过转写。');
  return blob;
}

function failure(reason: unknown, clipStartSeconds?: number): AudioSnippetResult {
  return { available: false, segments: [], warnings: [reason instanceof Error ? reason.message : '短音频转写暂时不可用。'], clipStartSeconds };
}

async function withTimeout<T>(run: (signal: AbortSignal) => Promise<T>, milliseconds: number): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), milliseconds);
  try { return await run(controller.signal); }
  finally { clearTimeout(timer); }
}

export async function uploadAudioSnippet(options: UploadAudioSnippetOptions): Promise<AudioSnippetResult> {
  try {
    if (!options.token) return failure('登录后可获取音频转写。');
    if (!options.audio.size || options.audio.size >= MAX_AUDIO_BYTES) return failure('短音频为空或超过上传大小。');
    const form = new FormData();
    const extension = options.audio.type.includes('wav') ? 'wav'
      : options.audio.type.includes('webm') ? 'webm'
        : options.audio.type.includes('ogg') ? 'ogg' : 'm4a';
    form.append('audio', options.audio, options.filename ?? `snippet.${extension}`);
    form.append('platform', options.descriptor.platform);
    form.append('external_id', options.descriptor.external_id);
    form.append('part', String(options.descriptor.part));
    form.append('clip_start_seconds', String(options.clipStartSeconds));
    return await withTimeout(async signal => {
      const response = await (options.fetcher ?? fetch)(apiUrl(options.serverOrigin, '/api/ai/external-audio-snippet/'), {
        method: 'POST', credentials: 'omit', headers: { Authorization: `Token ${options.token}` }, body: form, signal,
      });
      if (!response.ok) return failure(`短音频转写暂不可用（HTTP ${response.status}）。`);
      const result = await response.json() as { available?: boolean; segments?: TranscriptSegmentItem[] };
      if (result.available === false) return failure('服务端暂未提供音频转写，已保留标题与画面。');
      const segments = Array.isArray(result.segments) ? result.segments.filter(segment =>
        Number.isFinite(segment.start_time) && Number.isFinite(segment.end_time) && typeof segment.text === 'string') : [];
      return { available: true, segments, warnings: [], clipStartSeconds: options.clipStartSeconds };
    }, 30_000);
  } catch (error) { return failure(error, options.clipStartSeconds); }
}

interface CachedHeader extends ParsedDashIndex { url: string }
interface CachedTranscript { result: AudioSnippetResult; rangeStart: number; rangeEnd: number }
const headers = new Map<string, CachedHeader>();
const transcripts = new Map<string, CachedTranscript>();
const pending = new Map<string, Promise<AudioSnippetResult>>();
const pendingClips = new Map<string, Promise<AudioSnippetResult>>();
let cacheAuth = '';

export function clearDashCaches(): void { headers.clear(); transcripts.clear(); pending.clear(); pendingClips.clear(); cacheAuth = ''; }

function remember<T>(cache: Map<string, T>, key: string, value: T, limit: number): void {
  cache.delete(key);
  cache.set(key, value);
  if (cache.size > limit) cache.delete(cache.keys().next().value!);
}

async function boundedBytes(response: Response, maximum: number): Promise<ArrayBuffer> {
  if (!response.body) return response.arrayBuffer();
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > maximum) throw new Error('音频 CDN 未遵守 Range 字节范围。');
      chunks.push(value);
    }
  } catch (error) { await reader.cancel().catch(() => undefined); throw error; }
  finally { reader.releaseLock(); }
  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  return bytes.buffer;
}

async function fetchRange(urls: string[], start: number, end: number, fetcher: typeof fetch): Promise<{ bytes: ArrayBuffer; url: string }> {
  let lastError: unknown = new Error('音频 CDN 暂时不可用。');
  for (const url of [...new Set(urls)]) {
    try {
      return await withTimeout(async signal => {
        const response = await fetcher(url, { headers: { Range: `bytes=${start}-${end}` }, credentials: 'omit', signal });
        if (!response.ok) throw new Error(`音频 CDN 请求失败（HTTP ${response.status}）。`);
        const contentRange = response.headers.get('Content-Range');
        if (response.status === 206 && contentRange && !contentRange.startsWith(`bytes ${start}-`)) {
          throw new Error('音频 CDN 返回了不匹配的字节范围。');
        }
        const maximum = response.status === 200 ? Math.min(Math.max(end + 1, 65536), MAX_AUDIO_BYTES) : end - start + 1;
        let bytes = await boundedBytes(response, maximum);
        if (response.status === 200 && start > 0) bytes = bytes.slice(start, end + 1);
        if (!bytes.byteLength || (start > 0 && bytes.byteLength !== end - start + 1)) throw new Error('音频 CDN 返回的子段不完整。');
        return { bytes, url };
      }, 8_000);
    } catch (error) { lastError = error; }
  }
  throw lastError;
}

export async function transcribeDashAudio(options: TranscribeDashOptions): Promise<AudioSnippetResult> {
  const auth = `${options.serverOrigin}:${options.token}`;
  if (auth !== cacheAuth) { clearDashCaches(); cacheAuth = auth; }
  const headerKey = `${options.descriptor.video_key}:${options.track.url}`;
  const requestKey = `${headerKey}:${options.targetSeconds}`;
  const existing = pending.get(requestKey);
  if (existing) return existing;
  const run = async (): Promise<AudioSnippetResult> => {
    try {
      const fetcher = options.fetcher ?? fetch;
      const urls = [options.track.url, ...(options.track.backupUrls ?? [])];
      let header = headers.get(headerKey);
      if (!header) {
        const indexRange = /^\d+-(\d+)$/.exec(options.track.indexRange ?? '');
        const headerEnd = indexRange ? Math.max(Number(indexRange[1]), 8191) : 65535;
        const response = await fetchRange(urls, 0, headerEnd, fetcher);
        header = { ...parseDashIndex(response.bytes, options.track.initRange), url: response.url };
        if (cacheAuth === auth) remember(headers, headerKey, header, 32);
      }
      const range = selectMediaRange(header.segments, options.targetSeconds, header.initBytes.byteLength);
      const cacheKey = `${options.descriptor.video_key}:${Math.floor(range.clipStartSeconds / 15)}`;
      const cached = cacheAuth === auth ? transcripts.get(cacheKey) : undefined;
      if (cached && cached.rangeStart <= range.rangeStart && cached.rangeEnd >= range.rangeEnd) return cached.result;
      const clipKey = `${auth}:${headerKey}:${range.rangeStart}-${range.rangeEnd}`;
      const activeClip = pendingClips.get(clipKey);
      if (activeClip) return activeClip;
      const transcribe = async () => {
        const media = await fetchRange([header.url, ...urls], range.rangeStart, range.rangeEnd, fetcher);
        const result = await uploadAudioSnippet({ ...options, audio: concatenateSnippet(header.initBytes, media.bytes), clipStartSeconds: range.clipStartSeconds });
        if (result.available && cacheAuth === auth) remember(transcripts, cacheKey, { result, ...range }, 128);
        return result;
      };
      const clip = transcribe();
      pendingClips.set(clipKey, clip);
      try { return await clip; }
      finally { if (pendingClips.get(clipKey) === clip) pendingClips.delete(clipKey); }
    } catch (error) { return failure(error); }
  };
  const result = run();
  pending.set(requestKey, result);
  try { return await result; }
  finally { if (pending.get(requestKey) === result) pending.delete(requestKey); }
}
