import { Capacitor } from '@capacitor/core';
export const SERVER_ORIGIN_STORAGE_KEY = 'unimind:server-origin';
export const SERVER_ORIGIN_CHANGED_EVENT = 'unimind:server-origin-changed';

const DEFAULT_FALLBACK_ORIGIN = 'http://10.0.2.2:8000';

export const SERVER_ORIGIN_PRESETS = [
  { label: 'USB 调试 (adb reverse)', origin: 'http://127.0.0.1:8000' },
  { label: 'Android 模拟器', origin: 'http://10.0.2.2:8000' },
  { label: '线上生产环境', origin: 'https://unimind-ai.com' },
] as const;

let _authTokenAccessor: (() => string | null) | null = null;

/**
 * Registers a live auth token reader without creating module import cycles.
 */
export function registerAuthTokenAccessor(accessor: () => string | null): void {
  _authTokenAccessor = accessor;
}

export function getRegisteredAuthToken(): string | null {
  return _authTokenAccessor ? _authTokenAccessor() : null;
}

/**
 * Returns true when running inside a native Capacitor WebView shell (Android/iOS).
 */
export function isNativePlatform(): boolean {
  return Capacitor.isNativePlatform();
}

/**
 * Normalizes and validates a backend origin URL (http:// or https://, no trailing slash).
 * Returns null if invalid. When `defaultScheme` is supplied and the input omits a scheme,
 * that scheme is prepended before parsing.
 */
export function normalizeServerOrigin(
  input: string,
  options?: { defaultScheme?: 'http' | 'https' },
): string | null {
  const trimmed = input.trim();
  if (!trimmed) return null;

  let candidate = trimmed;
  if (!/^[a-zA-Z][a-zA-Z\d+\-.]*:\/\//.test(candidate)) {
    if (!options?.defaultScheme || candidate.includes('://')) return null;
    candidate = `${options.defaultScheme}://${candidate.replace(/^\/+/, '')}`;
  }

  try {
    const parsed = new URL(candidate);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return null;
    if (!parsed.hostname || parsed.username || parsed.password) return null;
    return parsed.origin;
  } catch {
    return null;
  }
}

export function getDefaultNativeOrigin(): string {
  const envOrigin = typeof import.meta !== 'undefined' ? import.meta.env?.VITE_API_ORIGIN : undefined;
  return normalizeServerOrigin(envOrigin || '') ?? DEFAULT_FALLBACK_ORIGIN;
}

export function getStoredServerOrigin(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const stored = window.localStorage.getItem(SERVER_ORIGIN_STORAGE_KEY);
    return stored ? normalizeServerOrigin(stored) : null;
  } catch {
    return null;
  }
}

/**
 * Resolves the active backend origin (scheme + host + optional port, no trailing slash).
 */
export function getServerOrigin(): string {
  if (isNativePlatform()) {
    return getStoredServerOrigin() ?? getDefaultNativeOrigin();
  }
  const envOrigin = typeof import.meta !== 'undefined' ? import.meta.env?.VITE_API_ORIGIN : undefined;
  const normalizedEnvOrigin = normalizeServerOrigin(envOrigin || '');
  if (normalizedEnvOrigin) return normalizedEnvOrigin;

  const envApiUrl = typeof import.meta !== 'undefined' ? import.meta.env?.VITE_API_URL : undefined;
  const normalizedFromApi = envApiUrl ? normalizeServerOrigin(envApiUrl) : null;
  if (normalizedFromApi) return normalizedFromApi;

  return typeof window !== 'undefined' ? window.location.origin : '';
}

export function setServerOrigin(origin: string): string {
  const normalized = normalizeServerOrigin(origin);
  if (!normalized) {
    throw new Error('请输入以 http:// 或 https:// 开头的有效服务器地址');
  }
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(SERVER_ORIGIN_STORAGE_KEY, normalized);
    window.dispatchEvent(new CustomEvent(SERVER_ORIGIN_CHANGED_EVENT, { detail: normalized }));
  }
  return normalized;
}

export function clearServerOrigin(): void {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(SERVER_ORIGIN_STORAGE_KEY);
  window.dispatchEvent(new CustomEvent(SERVER_ORIGIN_CHANGED_EVENT, { detail: null }));
}

/**
 * Resolves the active API base URL.
 * Web and Desktop keep relative `/api` (or `VITE_API_URL`) untouched.
 */
export function getApiBaseUrl(): string {
  if (isNativePlatform()) {
    return `${getServerOrigin()}/api`;
  }
  return (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_URL) || '/api';
}

/**
 * Resolves the active WebSocket base URL (ws:// or wss:// + host).
 */
export function getWsBaseUrl(): string {
  if (isNativePlatform()) {
    return getServerOrigin().replace(/^http/i, 'ws');
  }
  const envWs = typeof import.meta !== 'undefined' ? import.meta.env?.VITE_WS_URL : undefined;
  if (envWs) return envWs;
  if (typeof window === 'undefined') return '';
  return (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + window.location.host;
}

/**
 * Resolves backend-hosted relative paths (such as `/media/...` or `/api/...`)
 * against the configured server origin when running in Capacitor native builds.
 * Bundled static assets under `/assets/` or `/unimind_logo_small.png` remain local.
 */
export function resolveAssetUrl(path: string | null | undefined): string {
  if (!path) return '';
  if (/^(https?:|data:|blob:|capacitor:|file:)/i.test(path)) return path;
  if (!isNativePlatform()) return path;
  if (path.startsWith('/media/') || path.startsWith('/api/')) {
    return `${getServerOrigin()}${path}`;
  }
  return path;
}
