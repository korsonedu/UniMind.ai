import axios from 'axios';

export type NormalizedApiError = {
  message: string;
  code: string;
  status?: number;
  requestId?: string;
  isNetworkError: boolean;
};

function getHeaderValue(headers: unknown, key: string): string | undefined {
  if (!headers || typeof headers !== 'object') return undefined;
  const map = headers as Record<string, unknown>;
  const exact = map[key];
  if (typeof exact === 'string' && exact.trim()) return exact.trim();
  const lower = map[key.toLowerCase()];
  if (typeof lower === 'string' && lower.trim()) return lower.trim();
  return undefined;
}

export function normalizeApiError(error: unknown, fallbackMessage = '请求失败'): NormalizedApiError {
  if (!axios.isAxiosError(error)) {
    return {
      message: fallbackMessage,
      code: 'unknown_error',
      isNetworkError: false,
    };
  }

  const status = error.response?.status;
  const payload = error.response?.data as Record<string, unknown> | undefined;
  const requestId = getHeaderValue(error.response?.headers, 'x-request-id')
    || (typeof payload?.request_id === 'string' ? payload.request_id : undefined);

  const message =
    (typeof payload?.error === 'string' && payload.error)
    || (typeof payload?.detail === 'string' && payload.detail)
    || (typeof payload?.message === 'string' && payload.message)
    || error.message
    || fallbackMessage;

  const code =
    (typeof payload?.code === 'string' && payload.code)
    || `http_${status || 'error'}`;

  return {
    message,
    code,
    status,
    requestId,
    isNetworkError: !error.response,
  };
}

export function formatApiErrorToast(error: unknown, fallbackMessage = '请求失败'): string {
  const normalized = normalizeApiError(error, fallbackMessage);
  if (normalized.requestId) return `${normalized.message} (RID: ${normalized.requestId})`;
  return normalized.message;
}
