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

/**
 * 从 DRF 响应 payload 中提取人类可读的错误信息。
 * DRF 可能把 error/detail 序列化为字符串、数组、或嵌套对象。
 */
function extractDRFMessage(payload: Record<string, unknown> | undefined): string | null {
  if (!payload) return null;

  // 优先从 error / detail / message 字段提取（可能为 string 或 string[]）
  for (const key of ['error', 'detail', 'message']) {
    const val = payload[key];
    if (typeof val === 'string' && val.trim()) return val.trim();
    if (Array.isArray(val)) {
      const first = val.find((v: unknown) => typeof v === 'string' && v.trim());
      if (first) return first as string;
    }
  }

  // 回退：从序列化器字段错误中提取第一条
  for (const [field, msgs] of Object.entries(payload)) {
    if (field === 'code' || field === 'request_id') continue;
    if (Array.isArray(msgs)) {
      const first = msgs.find((m: unknown) => typeof m === 'string' && m.trim());
      if (first) return `${field}: ${first}`;
    }
  }

  return null;
}

export function normalizeApiError(error: unknown, fallbackMessage = '请求失败，请检查网络后重试'): NormalizedApiError {
  if (!axios.isAxiosError(error)) {
    // 原生 fetch 错误、OSS 分片上传错误等：保留 error.message
    const nativeMessage = error instanceof Error ? error.message : null;
    return {
      message: nativeMessage || fallbackMessage,
      code: 'unknown_error',
      isNetworkError: true,
    };
  }

  const status = error.response?.status;
  const payload = error.response?.data as Record<string, unknown> | undefined;
  const requestId = getHeaderValue(error.response?.headers, 'x-request-id')
    || (typeof payload?.request_id === 'string' ? payload.request_id : undefined);

  const drfMessage = extractDRFMessage(payload);
  const message = drfMessage || error.message || fallbackMessage;

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
  if (normalized.requestId) return `${normalized.message} (RID: ${normalized.requestId})`;
  return normalized.message;
}
