import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  clearDashCaches, concatenateSnippet, installMediaHeaders, MAX_AUDIO_BYTES, MAX_MEDIA_BYTES, parseDashIndex,
  parseSidxFallback, selectMediaRange, transcribeDashAudio,
} from '../src/collectors/dash-range';
import {
  clearVisual, collectVisual, computeCropRect, MAX_FRAME_BYTES, pairFrames,
} from '../src/collectors/visual';
import type { ActiveVideoDescriptor, PageCollectSnapshot, VideoRectInfo } from '../src/shared/types';

function join(...chunks: Uint8Array[]): Uint8Array<ArrayBuffer> {
  const bytes = new Uint8Array(chunks.reduce((length, chunk) => length + chunk.length, 0));
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.length;
  }
  return bytes;
}

function box(type: string, payload: Uint8Array) {
  const header = new Uint8Array(8);
  new DataView(header.buffer).setUint32(0, header.length + payload.length);
  header.set(new TextEncoder().encode(type), 4);
  return join(header, payload);
}

function makeHeader({
  version = 0, startTime = 0, firstOffset = 0, sizes = [256, 256, 256, 256],
}: { version?: 0 | 1; startTime?: number; firstOffset?: number; sizes?: number[] } = {}) {
  const ftyp = box('ftyp', new TextEncoder().encode('iso6\0\0\0\x01iso6mp41'));
  const mvhd = new Uint8Array(100);
  const movie = new DataView(mvhd.buffer);
  movie.setUint32(12, 1_000);
  movie.setUint32(20, 0x00010000);
  movie.setUint16(24, 0x0100);
  movie.setUint32(36, 0x00010000);
  movie.setUint32(52, 0x00010000);
  movie.setUint32(68, 0x40000000);
  movie.setUint32(96, 1);
  const init = join(ftyp, box('moov', box('mvhd', mvhd)));

  const refsOffset = version === 0 ? 24 : 32;
  const fields = new Uint8Array(refsOffset + sizes.length * 12);
  const sidx = new DataView(fields.buffer);
  sidx.setUint8(0, version);
  sidx.setUint32(4, 1); // reference_ID
  sidx.setUint32(8, 1_000); // timescale
  if (version === 0) {
    sidx.setUint32(12, startTime);
    sidx.setUint32(16, firstOffset);
  } else {
    sidx.setBigUint64(12, BigInt(startTime));
    sidx.setBigUint64(20, BigInt(firstOffset));
  }
  sidx.setUint16(refsOffset - 2, sizes.length);
  sizes.forEach((size, i) => {
    const offset = refsOffset + i * 12;
    sidx.setUint32(offset, size);
    sidx.setUint32(offset + 4, 10_000);
    sidx.setUint32(offset + 8, 0x90000000); // starts_with_SAP, SAP_type = 1
  });
  const header = join(init, box('sidx', fields));
  return { init, header, mediaStart: header.length + firstOffset };
}

const descriptor: ActiveVideoDescriptor = {
  platform: 'bilibili', external_id: 'BVDASH', part: 2, video_key: 'bilibili:BVDASH:p2',
  url: 'https://www.bilibili.com/video/BVDASH?p=2', title: 'DASH fixture',
};
const rect: VideoRectInfo = {
  x: -80, y: 450, width: 400, height: 200,
  viewportWidth: 800, viewportHeight: 600, devicePixelRatio: 1.25,
};
const frame = (video_seconds: number, image = 'data:image/jpeg;base64,AQID') => ({ video_seconds, image });

afterEach(() => {
  clearDashCaches();
  clearVisual(4);
  vi.unstubAllGlobals();
});

describe('DASH 初始化头、sidx 与 HTTP Range', () => {
  it('用扩展 ID 限定 CDN 请求头规则，注册失败后可以重试', async () => {
    const updateSessionRules = vi.fn()
      .mockRejectedValueOnce(new Error('注册暂时不可用'))
      .mockResolvedValueOnce(undefined);
    const extensionId = 'abcdefghijklmnopabcdefghijklmnop';
    vi.stubGlobal('chrome', { runtime: { id: extensionId }, declarativeNetRequest: { updateSessionRules } });
    await expect(installMediaHeaders()).rejects.toThrow('注册暂时不可用');
    const retry = installMediaHeaders();
    expect(installMediaHeaders()).toBe(retry);
    await expect(retry).resolves.toBeUndefined();
    expect(updateSessionRules).toHaveBeenCalledTimes(2);
    expect(updateSessionRules).toHaveBeenLastCalledWith({
      removeRuleIds: [1001],
      addRules: [{
        id: 1001, priority: 1,
        action: { type: 'modifyHeaders', requestHeaders: [
          { header: 'Referer', operation: 'set', value: 'https://www.bilibili.com/' },
          { header: 'Origin', operation: 'set', value: 'https://www.bilibili.com' },
        ] },
        condition: {
          requestDomains: ['bilivideo.com', 'hdslb.com', 'akamaized.net'],
          resourceTypes: ['xmlhttprequest', 'other'],
          initiatorDomains: [extensionId],
        },
      }],
    });
  });

  it('以 sidx 末端和 first_offset 为基准，累计 timescale 和段长', () => {
    const { init, header, mediaStart } = makeHeader({ startTime: 2_500, firstOffset: 13, sizes: [256, 512] });
    const parsed = parseDashIndex(header.buffer);
    expect(parsed.index).toMatchObject({ start: init.length, size: header.length - init.length, timescale: 1_000 });
    expect(new Uint8Array(parsed.initBytes)).toEqual(init);
    expect(parsed.segments).toEqual([
      { startSeconds: 2.5, endSeconds: 12.5, byteStart: mediaStart, byteEnd: mediaStart + 255 },
      { startSeconds: 12.5, endSeconds: 22.5, byteStart: mediaStart + 256, byteEnd: mediaStart + 767 },
    ]);
    const explicit = parseDashIndex(header.buffer, `0-${init.length - 1}`);
    expect(explicit.initBytes).toEqual(parsed.initBytes);
    const fallback = parseSidxFallback(header.buffer);
    expect(fallback).not.toBeNull();
    expect(parsed.index).toMatchObject(fallback!);
  });

  it('备选解析器读取 version 1 的 64 位字段', () => {
    const { header, mediaStart } = makeHeader({ version: 1, startTime: 2 ** 32 + 500, firstOffset: 2 ** 32 + 13 });
    expect(parseSidxFallback(header.buffer)).toMatchObject({
      timescale: 1_000, earliest_presentation_time: 2 ** 32 + 500, first_offset: 2 ** 32 + 13,
      references: [{ reference_type: 0, referenced_size: 256, subsegment_duration: 10_000 },
        { reference_type: 0, referenced_size: 256, subsegment_duration: 10_000 },
        { reference_type: 0, referenced_size: 256, subsegment_duration: 10_000 },
        { reference_type: 0, referenced_size: 256, subsegment_duration: 10_000 }],
    });
    expect(parseDashIndex(header.buffer).segments[0]).toMatchObject({
      startSeconds: (2 ** 32 + 500) / 1_000, byteStart: mediaStart,
    });
  });

  it('超出 3.5 MiB 时收窄至 30 秒前和 10 秒后，保留完整媒体子段', () => {
    const { header, init, mediaStart } = makeHeader({ sizes: Array<number>(12).fill(600_000) });
    const { segments } = parseDashIndex(header.buffer);
    const range = selectMediaRange(segments, 80, init.byteLength);
    expect(range).toEqual({
      rangeStart: mediaStart + 3_000_000, rangeEnd: mediaStart + 5_400_000 - 1,
      clipStartSeconds: 50, clipEndSeconds: 90, narrowed: true,
    });
    expect(range.rangeEnd - range.rangeStart + 1).toBeLessThanOrEqual(MAX_MEDIA_BYTES);
    expect(range.rangeEnd - range.rangeStart + 1 + init.byteLength).toBeLessThan(MAX_AUDIO_BYTES);
  });

  it('按顺序拼接初始化与 moof/mdat，遇主 CDN 403 自动切换并复用缓存', async () => {
    const media = join(box('moof', new Uint8Array()), box('mdat', Uint8Array.of(9, 8, 7, 6)));
    const { header, init, mediaStart } = makeHeader({ startTime: 2_500, firstOffset: 13, sizes: [media.length] });
    const snippet = concatenateSnippet(init.buffer, media.buffer);
    expect(snippet.type).toBe('audio/mp4');
    expect(new Uint8Array(await snippet.arrayBuffer())).toEqual(join(init, media));

    const ranges = [`bytes=0-8191`, `bytes=${mediaStart}-${mediaStart + media.length - 1}`];
    const segments = [{ start_time: 2.5, end_time: 4, text: '绝对时间转写' }];
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(null, { status: 403 }))
      .mockResolvedValueOnce(new Response(header, { status: 206 }))
      .mockResolvedValueOnce(new Response(media, {
        status: 206, headers: { 'Content-Range': `bytes ${mediaStart}-${mediaStart + media.length - 1}/1000` },
      }))
      .mockResolvedValueOnce(Response.json({ available: true, segments }));
    const url = 'https://unit.bilivideo.com/audio.m4s';
    const backup = 'https://unit.hdslb.com/audio.m4s';
    const options = {
      descriptor, targetSeconds: 6, serverOrigin: 'https://uni.example', token: 'fixture-token', fetcher,
      track: { url, backupUrls: [backup], initRange: `0-${init.length - 1}`, indexRange: `${init.length}-${header.length - 1}` },
    };
    expect(await transcribeDashAudio(options)).toMatchObject({ available: true, segments, clipStartSeconds: 2.5 });
    expect(fetcher).toHaveBeenNthCalledWith(1, url, expect.objectContaining({ credentials: 'omit', headers: { Range: ranges[0] } }));
    expect(fetcher).toHaveBeenNthCalledWith(2, backup, expect.objectContaining({ credentials: 'omit', headers: { Range: ranges[0] } }));
    expect(fetcher).toHaveBeenNthCalledWith(3, backup, expect.objectContaining({ credentials: 'omit', headers: { Range: ranges[1] } }));
    const upload = fetcher.mock.calls[3];
    expect(upload).toEqual(['https://uni.example/api/ai/external-audio-snippet/', expect.objectContaining({
      method: 'POST', credentials: 'omit', headers: { Authorization: 'Token fixture-token' },
    })]);
    const form = upload?.[1]?.body as FormData;
    expect([...form.entries()].slice(1)).toEqual([
      ['platform', 'bilibili'], ['external_id', 'BVDASH'], ['part', '2'], ['clip_start_seconds', '2.5'],
    ]);
    const file = form.get('audio') as File;
    expect(file.name).toBe('snippet.m4a');
    expect(await file.arrayBuffer()).toEqual(await snippet.arrayBuffer());

    expect(await transcribeDashAudio({ ...options, targetSeconds: 7 })).toMatchObject({ segments });
    expect(fetcher).toHaveBeenCalledTimes(4);
  });

  it('缺失 sidx 时返回告警和空字幕，默认只请求前 64 KiB', async () => {
    const { init } = makeHeader();
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(new Response(init, { status: 206 }));
    const result = await transcribeDashAudio({
      descriptor, targetSeconds: 6, track: { url: 'https://unit.bilivideo.com/missing.m4s' },
      serverOrigin: 'https://uni.example', token: 'fixture-token', fetcher,
    });
    expect(result).toMatchObject({ available: false, segments: [], warnings: [expect.stringContaining('sidx')] });
    expect(fetcher).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ headers: { Range: 'bytes=0-65535' } }));
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});

describe('播放画面裁剪与双帧', () => {
  it('用图像和视口宽度比换算坐标，并裁去视口外部分', () => {
    expect(computeCropRect(rect, 1600, 1200)).toEqual({ sx: 0, sy: 900, sw: 640, sh: 300 });
    expect(computeCropRect({ ...rect, x: 900 }, 1600, 1200)).toBeNull();
    expect(computeCropRect({ ...rect, viewportWidth: 0 }, 1600, 1200)).toEqual({
      sx: 0, sy: 562.5, sw: 400, sh: 250,
    });
  });

  it('只配对满足 15 秒时间窗和字节上限的前帧', () => {
    const current = frame(40);
    expect(pairFrames(current, [frame(24.99), frame(40), frame(42)])).toEqual({ current });
    expect(pairFrames(current, [frame(25)])).toEqual({ current, previous: frame(25) });
    expect(pairFrames(current, [frame(35), frame(36), frame(36.5)])).toEqual({ current, previous: frame(36.5) });
    const oversized = `data:image/jpeg;base64,${btoa('a'.repeat(MAX_FRAME_BYTES + 1))}`;
    expect(pairFrames(current, [frame(39, oversized), frame(35)])).toEqual({ current, previous: frame(35) });
  });

  it('裁剪全视口截图、压缩至目标大小，并按 Tab 与视频键复用最近成功帧', async () => {
    const captureVisibleTab = vi.fn().mockResolvedValue('data:image/jpeg;base64,AQID');
    const close = vi.fn();
    const drawImage = vi.fn();
    const qualities: number[] = [];
    const canvases: [number, number][] = [];
    vi.stubGlobal('chrome', {
      tabs: {
        get: vi.fn().mockResolvedValue({ active: true, windowId: 2 }),
        query: vi.fn().mockResolvedValue([{ id: 4 }]),
        captureVisibleTab,
      },
    });
    vi.stubGlobal('createImageBitmap', vi.fn().mockResolvedValue({ width: 3200, height: 2400, close }));
    vi.stubGlobal('OffscreenCanvas', class {
      constructor(readonly width: number, readonly height: number) { canvases.push([width, height]); }
      getContext() { return { drawImage }; }
      async convertToBlob({ quality }: ImageEncodeOptions) {
        qualities.push(quality!);
        return new Blob([new Uint8Array(quality === 0.75 ? MAX_FRAME_BYTES + 1 : 3)], { type: 'image/jpeg' });
      }
    });
    const snapshot: PageCollectSnapshot = {
      descriptor, video_seconds: 30, paused: false, transcript_source: 'none', segments: [],
      direct_visual: null, cors_fallback_rect: { ...rect, width: 560 },
    };
    const first = await collectVisual(4, snapshot);
    expect(first).toEqual({ warnings: [], visual: { current: frame(30, 'data:image/jpeg;base64,AAAA') } });
    expect(captureVisibleTab).toHaveBeenCalledWith(2, { format: 'jpeg', quality: 85 });
    expect(canvases).toEqual([[1280, 400]]);
    expect(drawImage).toHaveBeenCalledWith(expect.anything(), 0, 1800, 1920, 600, 0, 0, 1280, 400);
    expect(qualities).toEqual([0.75, 0.6]);
    expect(close).toHaveBeenCalledOnce();
    await expect(collectVisual(4, { ...snapshot, video_seconds: 40 })).resolves.toMatchObject({
      visual: { current: frame(40, 'data:image/jpeg;base64,AAAA'), previous: first.visual?.current },
    });
    const switched = await collectVisual(4, {
      ...snapshot, video_seconds: 41, descriptor: { ...descriptor, video_key: 'bilibili:BVDASH:p3' },
    });
    expect(switched.visual?.previous).toBeUndefined();
  });
});
