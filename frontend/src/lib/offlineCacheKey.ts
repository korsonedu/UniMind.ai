export function nativeCacheKey(userId: number, origin: string): string {
  if (!Number.isSafeInteger(userId) || userId === 0) throw new Error('无效离线账号');
  return `unimind:offline:v1:${userId}:${encodeURIComponent(origin)}`;
}
