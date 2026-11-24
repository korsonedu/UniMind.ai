import type { ActiveVideoDescriptor, CaptureContextResult, PageCollectSnapshot, VideoPlatform } from './types';

export const UNIMIND_VIDEO_STATE_CHANGED = 'UNIMIND_VIDEO_STATE_CHANGED';
export const UNIMIND_OPEN_SIDEPANEL = 'UNIMIND_OPEN_SIDEPANEL';
export const UNIMIND_GET_ACTIVE_VIDEO = 'UNIMIND_GET_ACTIVE_VIDEO';
export const UNIMIND_COLLECT_PAGE_SNAPSHOT = 'UNIMIND_COLLECT_PAGE_SNAPSHOT';
export const UNIMIND_SEEK_VIDEO = 'UNIMIND_SEEK_VIDEO';
export const UNIMIND_CAPTURE_CONTEXT_FOR_ASK = 'UNIMIND_CAPTURE_CONTEXT_FOR_ASK';
export const UNIMIND_AUTH_SYNC = 'UNIMIND_AUTH_SYNC';
export const UNIMIND_TOGGLE_TAB_AUDIO = 'UNIMIND_TOGGLE_TAB_AUDIO';

interface MessagePayloads {
  [UNIMIND_VIDEO_STATE_CHANGED]: ActiveVideoDescriptor | null;
  [UNIMIND_OPEN_SIDEPANEL]: undefined;
  [UNIMIND_GET_ACTIVE_VIDEO]: undefined;
  [UNIMIND_COLLECT_PAGE_SNAPSHOT]: { windowBeforeSec?: number; windowAfterSec?: number } | undefined;
  [UNIMIND_SEEK_VIDEO]: { seconds: number };
  [UNIMIND_CAPTURE_CONTEXT_FOR_ASK]: { tabId?: number } | undefined;
  [UNIMIND_AUTH_SYNC]: { serverOrigin?: string } | undefined;
  [UNIMIND_TOGGLE_TAB_AUDIO]: { tabId?: number; enabled: boolean };
}

export interface MessageResponses {
  [UNIMIND_VIDEO_STATE_CHANGED]: void;
  [UNIMIND_OPEN_SIDEPANEL]: { ok: boolean };
  [UNIMIND_GET_ACTIVE_VIDEO]: ActiveVideoDescriptor | null;
  [UNIMIND_COLLECT_PAGE_SNAPSHOT]: PageCollectSnapshot | null;
  [UNIMIND_SEEK_VIDEO]: { ok: boolean; currentTime?: number };
  [UNIMIND_CAPTURE_CONTEXT_FOR_ASK]: CaptureContextResult;
  [UNIMIND_AUTH_SYNC]: { token: string | null };
  [UNIMIND_TOGGLE_TAB_AUDIO]: { enabled: boolean; error?: string };
}

export type MessageType = keyof MessagePayloads;
export type BridgeMessage = {
  [Type in MessageType]: { type: Type; payload?: MessagePayloads[Type] } &
    (undefined extends MessagePayloads[Type] ? unknown : { payload: MessagePayloads[Type] });
}[MessageType];

type TabMessageType =
  | typeof UNIMIND_GET_ACTIVE_VIDEO
  | typeof UNIMIND_COLLECT_PAGE_SNAPSHOT
  | typeof UNIMIND_SEEK_VIDEO;
type RuntimeMessageType = Exclude<MessageType, TabMessageType>;
type MessageArgs<Type extends MessageType> = undefined extends MessagePayloads[Type]
  ? [payload?: MessagePayloads[Type]]
  : [payload: MessagePayloads[Type]];

export function sendTabMessage<Type extends TabMessageType>(
  tabId: number, type: Type, ...[payload]: MessageArgs<Type>
): Promise<MessageResponses[Type]> {
  return chrome.tabs.sendMessage(tabId, payload === undefined ? { type } : { type, payload });
}

export function sendRuntimeMessage<Type extends RuntimeMessageType>(
  type: Type, ...[payload]: MessageArgs<Type>
): Promise<MessageResponses[Type]> {
  return chrome.runtime.sendMessage(payload === undefined ? { type } : { type, payload });
}

export function formatVideoKey(platform: VideoPlatform, external_id: string, part: number): string {
  if (platform === 'bilibili') return `bilibili:${external_id}:p${part || 1}`;
  return part > 1 ? `${platform}:${external_id}:p${part}` : `${platform}:${external_id}`;
}

export function parseSeekSeconds(hrefOrText: string): number | null {
  const text = hrefOrText.trim();
  const seek = /^#seek:(\d+(?:\.\d+)?)$/.exec(text);
  if (seek?.[1]) {
    const seconds = Number(seek[1]);
    return Number.isFinite(seconds) ? seconds : null;
  }
  const timestamp = /^(?:\[(?:(\d+):)?(\d+):(\d{2})\]|(?:(\d+):)?(\d+):(\d{2}))$/.exec(text);
  if (!timestamp) return null;
  const hours = timestamp[1] ?? timestamp[4];
  const minutes = Number(timestamp[2] ?? timestamp[5]);
  const seconds = Number(timestamp[3] ?? timestamp[6]);
  const total = Number(hours ?? 0) * 3600 + minutes * 60 + seconds;
  return seconds < 60 && (!hours || minutes < 60) && Number.isFinite(total) ? total : null;
}
