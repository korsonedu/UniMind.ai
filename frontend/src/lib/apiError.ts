import { t } from '@/i18n';
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
  const value = Object.entries(headers).find(([name]) => name.toLowerCase() === key)?.[1];
  return typeof value === 'string' ? value.trim() || undefined : undefined;
}

/**
 * 从 DRF 响应 payload 中提取人类可读的错误信息。
 * DRF 可能把 error/detail 序列化为字符串、数组、或嵌套对象。
 */
function extractDRFMessage(payload: unknown): string | null {
  if (typeof payload === 'string') {
    const message = payload.trim();
    return message && !/^<!doctype\b|<(?:html|head|body)(?=[\s/>])/i.test(message) ? t(message) : null;
  }
  if (Array.isArray(payload)) {
    for (const item of payload) {
      const message = extractDRFMessage(item);
      if (message) return message;
    }
    return null;
  }
  if (!payload || typeof payload !== 'object') return null;
  const fields = payload as Record<string, unknown>;
  for (const key of ['error', 'detail', 'message']) {
    const message = extractDRFMessage(fields[key]);
    if (message) return message;
  }
  for (const [field, value] of Object.entries(fields)) {
    if (field === 'code' || field === 'request_id' || !Array.isArray(value)) continue;
    const message = extractDRFMessage(value);
    if (message) return message;
  }
  return null;
}

export function normalizeApiError(error: unknown, fallbackMessage = '请求失败，请检查网络后重试'): NormalizedApiError {
  if (!axios.isAxiosError(error)) {
    // 原生 fetch 错误、OSS 分片上传错误等：保留 error.message
    const nativeMessage = error instanceof Error ? error.message : null;
    return {
      message: t(nativeMessage || fallbackMessage),
      code: 'unknown_error',
      isNetworkError: true,
    };
  }

  const status = error.response?.status;
  const payload = error.response?.data as Record<string, unknown> | undefined;
  const requestId = getHeaderValue(error.response?.headers, 'x-request-id')
    || (typeof payload?.request_id === 'string' ? payload.request_id : undefined);

  const contentType = getHeaderValue(error.response?.headers, 'content-type') || '';
  const isHtml = /^(?:text\/html|application\/xhtml\+xml)\s*(?:;|$)/i.test(contentType);
  const drfMessage = isHtml ? null : extractDRFMessage(payload);
  const message = drfMessage || t(fallbackMessage);

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

export function formatApiErrorToast(error: unknown, fallbackMessage = '请求失败，请检查网络后重试'): string {
  const normalized = normalizeApiError(error, fallbackMessage);
  return t(normalized.message);
}
