import { ref } from 'vue';

export function message(error: unknown): string {
  if (error instanceof Error) return error.message;
  return '操作失败，请重试。';
}

export function detail(data: any): string {
  if (typeof data === 'string') return data;
  if (Array.isArray(data)) return data.map(detail).join('；');
  if (data && typeof data === 'object') return Object.entries(data).map(([key, value]) =>
    ['error', 'detail', 'non_field_errors'].includes(key) ? detail(value) : `${key}：${detail(value)}`).join('；');
  return '操作失败，请重试。';
}

export function useTask() {
  const busy = ref(false);
  const error = ref('');
  async function run(action: () => Promise<void>) {
    if (busy.value) return;
    busy.value = true;
    error.value = '';
    try { await action(); } catch (e) { error.value = message(e); }
    finally { busy.value = false; }
  }
  return { busy, error, run };
}

export function localDate(value: string) {
  return new Date(value).toLocaleString('zh-CN', { hour12: false });
}
