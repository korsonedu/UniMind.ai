import { UNIMIND_COLLECT_PAGE_SNAPSHOT } from '../../shared/bridge';
import type { PageCollectSnapshot } from '../../shared/types';
import {
  OFFSCREEN_AUDIO_TARGET,
  OFFSCREEN_CLOCK_TARGET,
  OFFSCREEN_STATE_TARGET,
  type AudioDocumentMessage,
  type AudioDocumentResponse,
} from './protocol';

let creatingDocument: Promise<void> | undefined;
let controlQueue: Promise<unknown> = Promise.resolve();
const enabledTabs = new Set<number>();
const enablingTabs = new Map<number, Promise<{ enabled: boolean; error?: string }>>();

function playbackClock(snapshot: PageCollectSnapshot) {
  return { video_key: snapshot.descriptor.video_key, video_seconds: snapshot.video_seconds, paused: snapshot.paused };
}

async function hasAudioDocument(): Promise<boolean> {
  const contexts = await chrome.runtime.getContexts({
    contextTypes: [chrome.runtime.ContextType.OFFSCREEN_DOCUMENT],
    documentUrls: [chrome.runtime.getURL('offscreen.html')],
  });
  return contexts.length > 0;
}

async function ensureAudioDocument(): Promise<void> {
  if (creatingDocument) return creatingDocument;
  creatingDocument = (async () => {
    if (await hasAudioDocument()) return;
    await chrome.offscreen.createDocument({
      url: 'offscreen.html',
      reasons: [chrome.offscreen.Reason.USER_MEDIA],
      justification: 'Record the most recent 60 seconds of user-enabled tab audio for lesson questions.',
    });
  })();
  try {
    await creatingDocument;
  } finally {
    creatingDocument = undefined;
  }
}

function sendAudioMessage(message: Omit<AudioDocumentMessage, 'target'>): Promise<AudioDocumentResponse> {
  return chrome.runtime.sendMessage({ target: OFFSCREEN_AUDIO_TARGET, ...message });
}

export function setTabAudioEnabled(tabId: number, enabled: boolean): Promise<{ enabled: boolean; error?: string }> {
  if (enabled) {
    const pending = enablingTabs.get(tabId);
    if (pending) return pending;
    if (enabledTabs.has(tabId)) return Promise.resolve({ enabled: true });
  } else {
    enabledTabs.delete(tabId);
    enablingTabs.delete(tabId);
  }
  // Obtain the stream ID while the caller's click activation is still available.
  const streamId = enabled ? chrome.tabCapture.getMediaStreamId({ targetTabId: tabId }) : undefined;
  // Attach a rejection handler immediately while a preceding control operation settles.
  const acquired = streamId?.then(value => ({ value }), error => ({ error }));
  const run = async () => {
    try {
      if (!enabled) {
        enabledTabs.delete(tabId);
        if (!(await hasAudioDocument())) return { enabled: false };
        return await sendAudioMessage({ action: 'stop', tabId });
      }
      const result = await acquired!;
      if ('error' in result) throw result.error;
      await ensureAudioDocument();
      const response = await sendAudioMessage({ action: 'start', tabId, streamId: result.value });
      if (response.enabled) enabledTabs.add(tabId);
      return response;
    } catch (error) {
      return { enabled: false, error: error instanceof Error ? error.message : '暂时无法开启实时听课录音。' };
    }
  };
  const operation = controlQueue.then(run, run);
  controlQueue = operation.catch(() => undefined);
  if (enabled) {
    enablingTabs.set(tabId, operation);
    void operation.finally(() => {
      if (enablingTabs.get(tabId) === operation) enablingTabs.delete(tabId);
    });
  }
  return operation;
}

export async function collectTabAudio(
  tabId: number,
  snapshot: PageCollectSnapshot,
): Promise<{ audio: Blob; clipStartSeconds: number } | null> {
  if (!(await hasAudioDocument())) return null;
  const response = await sendAudioMessage({ action: 'export', tabId, snapshot: playbackClock(snapshot) });
  if (!response.enabled) enabledTabs.delete(tabId);
  if (response.error) throw new Error(response.error);
  if (!response.audioBase64 || response.clipStartSeconds === undefined) return null;
  const bytes = Uint8Array.from(atob(response.audioBase64), character => character.charCodeAt(0));
  return { audio: new Blob([bytes], { type: 'audio/wav' }), clipStartSeconds: response.clipStartSeconds };
}

export async function stopTabAudio(tabId: number): Promise<void> {
  await setTabAudioEnabled(tabId, false);
}

export function installOffscreenAudioBridge(): void {
  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (sender.id !== chrome.runtime.id || sender.tab || sender.url !== chrome.runtime.getURL('offscreen.html')) return;
    if (message?.target === OFFSCREEN_STATE_TARGET) {
      if (!message.enabled) enabledTabs.delete(message.tabId);
      return;
    }
    if (message?.target !== OFFSCREEN_CLOCK_TARGET) return;
    if (!Number.isInteger(message.tabId)) return;
    void chrome.tabs.sendMessage(message.tabId, {
      type: UNIMIND_COLLECT_PAGE_SNAPSHOT,
      payload: { windowBeforeSec: 0, windowAfterSec: 0 },
    }).then((snapshot: PageCollectSnapshot | null) => respond(snapshot ? playbackClock(snapshot) : null), () => respond(null));
    return true;
  });
}
