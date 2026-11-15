import { t } from '@/i18n';
export function dateOffset(date: string, offset: number): string {
  const value = new Date(`${date}T12:00:00Z`);
  value.setUTCDate(value.getUTCDate() + offset);
  return value.toISOString().slice(0, 10);
}

export function learningDuration(seconds: number): string {
  if (seconds <= 0) return t('0 分钟');
  if (seconds < 60) return t('{0} 秒', { 0: Math.max(1, Math.round(seconds)) });
  const minutes = Math.floor(seconds / 60);
  return minutes >= 60 ? t('{0} 小时 {1} 分钟', { 0: Math.floor(minutes / 60), 1: minutes % 60 }) : t('{0} 分钟', { 0: minutes });
}
