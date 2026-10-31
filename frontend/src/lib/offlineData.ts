import axios from 'axios';
import api from './api';
import type { Note, NoteDraft, Notebook } from './notes';

export interface OfflineOutboxEntry {
  id: string;
  noteId: number;
  baseVersion: number;
  draft: NoteDraft;
  queuedAt: string;
}

export interface OfflinePractice {
  sessionId: string;
  questions: unknown[];
  result: unknown | null;
  cachedAt: string;
}

export interface OfflineCache {
  version: 1;
  userId: number;
  notes: Note[];
  notebooks: Notebook[];
  tags: { id: number; name: string }[];
  practice: Record<string, OfflinePractice>;
  outbox: OfflineOutboxEntry[];
  updatedAt: string;
}

const MAX_NOTES = 200;
const MAX_PRACTICE = 20;
const bridge = () => (
  window.unimindDesktop?.readOfflineData && window.unimindDesktop?.writeOfflineData
    ? window.unimindDesktop
    : null
);
export const offlineCacheSupported = () => !!bridge();

let cache: OfflineCache | null = null;
let cacheUserId: number | null = null;
let loadFlight: Promise<OfflineCache | null> | null = null;
let writeTimer: ReturnType<typeof setTimeout> | null = null;
let writeChain: Promise<void> = Promise.resolve();

const now = () => new Date().toISOString();

function isValid(value: unknown): value is OfflineCache {
  if (!value || typeof value !== 'object') return false;
  const data = value as Partial<OfflineCache>;
  return data.version === 1 && Number.isSafeInteger(data.userId)
    && Array.isArray(data.notes) && Array.isArray(data.notebooks) && Array.isArray(data.tags)
    && !!data.practice && typeof data.practice === 'object' && Array.isArray(data.outbox)
    && typeof data.updatedAt === 'string';
}

export function resetOfflineCache() {
  if (writeTimer) { clearTimeout(writeTimer); writeTimer = null; }
  cache = null; cacheUserId = null; loadFlight = null;
}

export async function loadOfflineCache(userId?: number): Promise<OfflineCache | null> {
  const desktop = bridge();
  if (!desktop || !userId) return null;
  if (cache && cacheUserId === userId) return cache;
  if (loadFlight) {
    const pending = await loadFlight;
    if (pending?.userId === userId) return pending;
  }
  cache = null; cacheUserId = null;
  loadFlight = desktop.readOfflineData!().then(value => {
    if (!isValid(value) || value.userId !== userId) {
      const empty: OfflineCache = {
        version: 1, userId, notes: [], notebooks: [], tags: [], practice: {}, outbox: [], updatedAt: now(),
      };
      cache = empty; cacheUserId = userId;
      return empty;
    }
    cache = value; cacheUserId = userId;
    return value;
  }).catch(() => null).finally(() => { loadFlight = null; });
  return loadFlight;
}

function scheduleWrite(immediate = false): Promise<void> {
  const value = cache;
  if (!value || !bridge()) return Promise.resolve();
  if (writeTimer) { clearTimeout(writeTimer); writeTimer = null; }
  const commit = () => {
    writeChain = writeChain.catch(() => {}).then(() => bridge()?.writeOfflineData?.(value)).then(() => {}).catch(() => {});
    return writeChain;
  };
  if (immediate) return commit();
  return new Promise(resolve => {
    writeTimer = setTimeout(() => { writeTimer = null; void commit(); resolve(); }, 400);
  });
}

async function mutate(userId: number, update: (value: OfflineCache) => void): Promise<OfflineCache | null> {
  const value = await loadOfflineCache(userId);
  if (!value) return null;
  update(value);
  value.updatedAt = now();
  await scheduleWrite();
  return value;
}

export async function cacheNotes(userId: number, notes: Note[], replace = false) {
  await mutate(userId, value => {
    if (replace) value.notes = notes.slice(0, MAX_NOTES);
    else {
      const merged = new Map(value.notes.map(note => [note.id, note]));
      for (const note of notes) merged.set(note.id, note);
      value.notes = [...merged.values()].sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, MAX_NOTES);
    }
  });
}

export async function cacheNote(userId: number, note: Note) {
  await mutate(userId, value => {
    value.notes = [note, ...value.notes.filter(item => item.id !== note.id)]
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at)).slice(0, MAX_NOTES);
  });
}

export async function cacheNotebooks(userId: number, notebooks: Notebook[]) {
  await mutate(userId, value => { value.notebooks = notebooks; });
}

export async function cacheTags(userId: number, tags: { id: number; name: string }[]) {
  await mutate(userId, value => { value.tags = tags; });
}

export async function cachePractice(userId: number, sessionId: string, questions: unknown[], result: unknown | null) {
  await mutate(userId, value => {
    value.practice[sessionId] = { sessionId, questions, result, cachedAt: now() };
    value.practice = Object.fromEntries(
      Object.entries(value.practice).sort(([, a], [, b]) => b.cachedAt.localeCompare(a.cachedAt)).slice(0, MAX_PRACTICE),
    );
  });
}

export async function getCachedNote(userId: number, noteId: number): Promise<Note | null> {
  const value = await loadOfflineCache(userId);
  return value?.notes.find(note => note.id === noteId) ?? null;
}

export async function getCachedPractice(userId: number, sessionId: string): Promise<OfflinePractice | null> {
  const value = await loadOfflineCache(userId);
  return value?.practice[sessionId] ?? null;
}

export async function queueNoteSave(userId: number, noteId: number, baseVersion: number, draft: NoteDraft) {
  const value = await loadOfflineCache(userId);
  if (!value) return false;
  const index = value.notes.findIndex(note => note.id === noteId);
  if (index >= 0) value.notes[index] = { ...value.notes[index], ...draft, updated_at: now() };
  const existing = value.outbox.find(entry => entry.noteId === noteId);
  if (existing) {
    existing.baseVersion = baseVersion;
    existing.draft = draft;
    existing.queuedAt = now();
  } else {
    value.outbox.push({ id: crypto.randomUUID(), noteId, baseVersion, draft, queuedAt: now() });
  }
  value.updatedAt = now();
  await scheduleWrite(true);
  return true;
}

export async function removeQueuedNote(userId: number, noteId: number) {
  const value = await loadOfflineCache(userId);
  if (!value || !value.outbox.some(entry => entry.noteId === noteId)) return;
  value.outbox = value.outbox.filter(entry => entry.noteId !== noteId);
  value.updatedAt = now();
  await scheduleWrite(true);
}

export async function flushOfflineOutbox(userId: number): Promise<{ synced: number; conflicts: number }> {
  const value = await loadOfflineCache(userId);
  if (!value || !navigator.onLine || !value.outbox.length) return { synced: 0, conflicts: 0 };
  let synced = 0;
  let conflicts = 0;
  for (const entry of [...value.outbox]) {
    try {
      const { data } = await api.patch<Note>(
        `/notes/items/${entry.noteId}/`,
        { ...entry.draft, version: entry.baseVersion },
        { timeout: 30000 },
      );
      const index = value.notes.findIndex(note => note.id === entry.noteId);
      if (index >= 0) value.notes[index] = data;
      value.outbox = value.outbox.filter(item => item.id !== entry.id);
      synced += 1;
    } catch (error) {
      const status = axios.isAxiosError(error) ? error.response?.status : undefined;
      if (status !== 409 && status !== 404) break;
      try {
        const { data } = await api.post<Note>('/notes/items/', {
          title: `${entry.draft.title || '未命名笔记'}（本地副本）`,
          content: entry.draft.content,
          notebook: entry.draft.notebook,
          tags: entry.draft.tags,
          is_favorite: entry.draft.is_favorite,
        }, { timeout: 30000 });
        value.notes = [data, ...value.notes].slice(0, MAX_NOTES);
        value.outbox = value.outbox.filter(item => item.id !== entry.id);
        conflicts += 1;
      } catch {
        break;
      }
    }
  }
  value.updatedAt = now();
  await scheduleWrite(true);
  if (synced || conflicts) {
    window.dispatchEvent(new CustomEvent('unimind:offline-sync', { detail: { synced, conflicts } }));
  }
  return { synced, conflicts };
}
