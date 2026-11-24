import { normalizeServerOrigin, type ExtensionSession } from './storage';

export class ApiError extends Error {
  constructor(public readonly status: number, message: string, public readonly data?: unknown) {
    super(message);
    this.name = 'ApiError';
  }
}

export interface ApiRequestOptions {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
}

export interface ApiClient {
  readonly serverOrigin: string;
  readonly token: string | null;
  request<T>(path: string, options?: ApiRequestOptions): Promise<T>;
  fetch(path: string, options?: RequestInit): Promise<Response>;
}

export function apiUrl(serverOrigin: string, path: string): string {
  const origin = normalizeServerOrigin(serverOrigin);
  const relative = path.startsWith('/') ? path : `/${path}`;
  if (/^https?:\/\//i.test(path)) {
    const url = new URL(path);
    if (url.origin !== origin) throw new Error('请求地址与当前服务地址不一致。');
    return url.href;
  }
  return `${origin}${relative === '/api' || relative.startsWith('/api/') ? relative : `/api${relative}`}`;
}

function errorMessage(data: unknown, status: number): string {
  if (typeof data === 'string' && data.trim()) return data;
  if (data && typeof data === 'object') {
    const record = data as Record<string, unknown>;
    for (const field of ['detail', 'error', 'message', 'non_field_errors']) {
      const value = record[field];
      if (typeof value === 'string' && value) return value;
      if (Array.isArray(value)) return value.map(String).join('，');
      if (value && typeof value === 'object' && typeof (value as Record<string, unknown>).message === 'string') {
        return String((value as Record<string, unknown>).message);
      }
    }
    const first = Object.values(record).find(value => Array.isArray(value) && value.length);
    if (Array.isArray(first)) return first.map(String).join('，');
  }
  return `请求失败（${status}），请稍后重试。`;
}

export async function throwApiError(response: Response): Promise<never> {
  const text = await response.text();
  let data: unknown;
  try { data = JSON.parse(text); } catch { data = undefined; }
  throw new ApiError(response.status, errorMessage(data, response.status), data);
}

export function createApiClient(session: Pick<ExtensionSession, 'serverOrigin' | 'token'> & Partial<ExtensionSession>): ApiClient {
  const serverOrigin = normalizeServerOrigin(session.serverOrigin);
  const token = session.token;
  const fetchApi = async (path: string, options: RequestInit = {}): Promise<Response> => {
    const headers = new Headers(options.headers);
    headers.set('Accept-Language', 'zh-CN');
    if (token) headers.set('Authorization', `Token ${token}`);
    else headers.delete('Authorization');
    return fetch(apiUrl(serverOrigin, path), {
      ...options,
      credentials: 'omit',
      headers,
    });
  };
  return {
    serverOrigin,
    token,
    fetch: fetchApi,
    async request<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
      const response = await fetchApi(path, {
        method: options.method ?? 'GET',
        headers: { Accept: 'application/json', ...(options.body === undefined ? {} : { 'Content-Type': 'application/json' }) },
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: options.signal,
      });
      if (!response.ok) return throwApiError(response);
      if (response.status === 204) return undefined as T;
      const text = await response.text();
      return (text ? JSON.parse(text) : undefined) as T;
    },
  };
}
