import { OFFSCREEN_AUDIO_TARGET, OFFSCREEN_CLOCK_TARGET, OFFSCREEN_STATE_TARGET, type AudioDocumentMessage, type PlaybackClock } from './protocol';

interface AudioChunk {
  buffer: AudioBuffer;
  startSeconds: number;
}

interface Recording {
  tabId: number;
  stream: MediaStream;
  context: AudioContext;
  source: MediaStreamAudioSourceNode;
  chunks: AudioChunk[];
  recorder?: MediaRecorder;
  timer?: ReturnType<typeof setTimeout>;
  clockTimer?: ReturnType<typeof setInterval>;
  clock?: { snapshot: PlaybackClock; at: number };
  polling: boolean;
  generation: number;
  stopped: boolean;
  pending: Promise<void>;
  flush?: () => Promise<void>;
}

const recordings = new Map<number, Recording>();
let operations: Promise<unknown> = Promise.resolve();

function updateClock(recording: Recording, snapshot: PlaybackClock): void {
  const now = performance.now();
  const previous = recording.clock;
  if (previous) {
    const elapsed = previous.snapshot.paused ? 0 : (now - previous.at) / 1000;
    const expected = previous.snapshot.video_seconds + elapsed;
    if (snapshot.video_key !== previous.snapshot.video_key ||
        Math.abs(snapshot.video_seconds - expected) > 2) {
      recording.generation++;
      recording.chunks = [];
    }
  }
  recording.clock = { snapshot, at: now };
}

async function pollClock(recording: Recording): Promise<void> {
  if (recording.polling) return;
  recording.polling = true;
  const previousClock = recording.clock;
  try {
    const snapshot = await chrome.runtime.sendMessage({ target: OFFSCREEN_CLOCK_TARGET, tabId: recording.tabId }) as PlaybackClock | null;
    if (snapshot && !recording.stopped && recording.clock === previousClock) updateClock(recording, snapshot);
  } catch {
    // The next tick reconnects after a service worker restart.
  } finally {
    recording.polling = false;
  }
}

function startChunk(recording: Recording): void {
  if (recording.stopped) return;
  const mimeType = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus']
    .find(type => MediaRecorder.isTypeSupported(type));
  const recorder = new MediaRecorder(recording.stream, { ...(mimeType ? { mimeType } : {}), audioBitsPerSecond: 64000 });
  recording.recorder = recorder;
  const parts: Blob[] = [];
  const generation = recording.generation;
  const initialClock = recording.clock;
  const start = performance.now();
  let finish!: () => void;
  const completed = new Promise<void>(resolve => { finish = resolve; });
  recorder.ondataavailable = event => { if (event.data.size) parts.push(event.data); };
  recorder.onstop = () => {
    // Each stopped recorder produces a complete WebM. Decode before evicting
    // older chunks, then export one WAV so every rolling window remains valid.
    startChunk(recording);
    const decode = async () => {
      const clock = initialClock ?? recording.clock;
      if (!parts.length || !clock || clock.snapshot.paused) return;
      const bytes = await new Blob(parts, { type: recorder.mimeType }).arrayBuffer();
      const buffer = await recording.context.decodeAudioData(bytes);
      if (recording.stopped || generation !== recording.generation) return;
      recording.chunks.push({
        buffer,
        startSeconds: clock.snapshot.video_seconds + (start - clock.at) / 1000,
      });
      let duration = recording.chunks.reduce((total, chunk) => total + chunk.buffer.duration, 0);
      while (recording.chunks.length > 1 && duration - recording.chunks[0]!.buffer.duration >= 60) {
        duration -= recording.chunks.shift()!.buffer.duration;
      }
    };
    recording.pending = recording.pending.then(decode).catch(() => undefined).finally(finish);
  };
  recorder.onerror = () => { if (recorder.state !== 'inactive') recorder.stop(); };
  recorder.start();
  recording.timer = setTimeout(() => { if (recorder.state !== 'inactive') recorder.stop(); }, 1000);
  recording.flush = async () => {
    clearTimeout(recording.timer);
    if (recorder.state !== 'inactive') recorder.stop();
    await completed;
  };
}

async function stopRecording(tabId: number): Promise<void> {
  const recording = recordings.get(tabId);
  if (!recording) return;
  recordings.delete(tabId);
  recording.stopped = true;
  clearTimeout(recording.timer);
  clearInterval(recording.clockTimer);
  if (recording.recorder?.state !== 'inactive') recording.recorder?.stop();
  recording.stream.getTracks().forEach(track => track.stop());
  recording.source.disconnect();
  await recording.context.close();
  void chrome.runtime.sendMessage({ target: OFFSCREEN_STATE_TARGET, tabId, enabled: false }).catch(() => undefined);
}

async function startRecording(tabId: number, streamId: string): Promise<void> {
  await stopRecording(tabId);
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { mandatory: { chromeMediaSource: 'tab', chromeMediaSourceId: streamId } } as MediaTrackConstraints,
    video: false,
  });
  const context = new AudioContext();
  const source = context.createMediaStreamSource(stream);
  // tabCapture suppresses the page's direct output until explicitly played here.
  source.connect(context.destination);
  try {
    await context.resume();
    const recording: Recording = { tabId, stream, context, source, chunks: [], generation: 0, stopped: false, polling: false, pending: Promise.resolve() };
    recordings.set(tabId, recording);
    stream.getAudioTracks().forEach(track => track.addEventListener('ended', () => {
      if (recordings.get(tabId) === recording) void stopRecording(tabId);
    }, { once: true }));
    startChunk(recording);
    void pollClock(recording);
    recording.clockTimer = setInterval(() => { void pollClock(recording); }, 2000);
  } catch (error) {
    if (recordings.has(tabId)) {
      await stopRecording(tabId);
    } else {
      stream.getTracks().forEach(track => track.stop());
      source.disconnect();
      await context.close();
    }
    throw error;
  }
}

async function exportRecording(recording: Recording, snapshot: PlaybackClock) {
  updateClock(recording, snapshot);
  await recording.flush?.();
  if (!recording.chunks.length) return { enabled: true };
  const chunks = recording.chunks.slice();
  const sampleRate = recording.context.sampleRate;
  const totalFrames = chunks.reduce((total, chunk) => total + chunk.buffer.length, 0);
  const trim = Math.max(0, totalFrames - Math.floor(sampleRate * 60));
  const mono = new AudioBuffer({ numberOfChannels: 1, length: totalFrames - trim, sampleRate });
  const samples = mono.getChannelData(0);
  let position = -trim;
  for (const { buffer } of chunks) {
    for (let channel = 0; channel < buffer.numberOfChannels; channel++) {
      const values = buffer.getChannelData(channel);
      for (let frame = Math.max(0, -position); frame < values.length; frame++) {
        samples[position + frame] = samples[position + frame]! + values[frame]! / buffer.numberOfChannels;
      }
    }
    position += buffer.length;
  }
  const offline = new OfflineAudioContext(1, Math.ceil(mono.duration * 16000), 16000);
  const source = offline.createBufferSource();
  source.buffer = mono;
  source.connect(offline.destination);
  source.start();
  const rendered = await offline.startRendering();
  const pcm = rendered.getChannelData(0);
  const wav = new ArrayBuffer(44 + pcm.length * 2);
  const view = new DataView(wav);
  const label = (offset: number, text: string) => [...text].forEach((character, index) => view.setUint8(offset + index, character.charCodeAt(0)));
  label(0, 'RIFF');
  view.setUint32(4, wav.byteLength - 8, true);
  label(8, 'WAVE');
  label(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, 16000, true);
  view.setUint32(28, 32000, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  label(36, 'data');
  view.setUint32(40, pcm.length * 2, true);
  for (let index = 0; index < pcm.length; index++) {
    view.setInt16(44 + index * 2, Math.max(-1, Math.min(1, pcm[index]!)) * 32767, true);
  }
  const bytes = new Uint8Array(wav);
  let binary = '';
  for (let index = 0; index < bytes.length; index += 8192) binary += String.fromCharCode(...bytes.subarray(index, index + 8192));
  return { enabled: true, audioBase64: btoa(binary), clipStartSeconds: Math.max(0, chunks[0]!.startSeconds + trim / sampleRate) };
}

chrome.runtime.onMessage.addListener((message: AudioDocumentMessage, sender, respond) => {
  if (message?.target !== OFFSCREEN_AUDIO_TARGET || sender.id !== chrome.runtime.id || sender.tab ||
      (sender.url && sender.url !== chrome.runtime.getURL('background.js'))) return;
  const run = async () => {
    if (message.action === 'start' && message.streamId) {
      if (recordings.has(message.tabId)) return { enabled: true };
      await startRecording(message.tabId, message.streamId);
      return { enabled: true };
    }
    if (message.action === 'stop') {
      await stopRecording(message.tabId);
      return { enabled: false };
    }
    const recording = recordings.get(message.tabId);
    if (!recording || !message.snapshot) return { enabled: false };
    return exportRecording(recording, message.snapshot);
  };
  const result = operations.then(run, run);
  operations = result.catch(() => undefined);
  void result.then(respond, error => respond({ enabled: recordings.has(message.tabId), error: error instanceof Error ? error.message : '暂时无法导出听课录音。' }));
  return true;
});

window.addEventListener('pagehide', () => { for (const tabId of recordings.keys()) void stopRecording(tabId); });
