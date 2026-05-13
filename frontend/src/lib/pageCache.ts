type CacheEnvelope<T> = {
  data: T;
  updatedAt: number;
};

function safeStorage(): Storage | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function readPageCache<T>(key: string, ttlMs: number): T | null {
  const storage = safeStorage();
  if (!storage) return null;

  try {
    const raw = storage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CacheEnvelope<T>;
    if (!parsed || typeof parsed !== 'object') return null;
    if (typeof parsed.updatedAt !== 'number') return null;
    if (Date.now() - parsed.updatedAt > ttlMs) {
      storage.removeItem(key);
      return null;
    }
    return parsed.data ?? null;
  } catch {
    return null;
  }
}

export function writePageCache<T>(key: string, data: T): void {
  const storage = safeStorage();
  if (!storage) return;
  try {
    const payload: CacheEnvelope<T> = { data, updatedAt: Date.now() };
    storage.setItem(key, JSON.stringify(payload));
  } catch {
    // Ignore cache write failures (quota/privacy mode)
  }
}
