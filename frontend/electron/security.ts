export function validSource(value: string, development: boolean): boolean {
  try {
    const url = new URL(value);
    if (url.username || url.password) return false;
    if (url.protocol === 'https:') return true;
    return development && url.protocol === 'http:'
      && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
  } catch {
    return false;
  }
}

export function sameOrigin(source: string, target: string): boolean {
  try {
    const origin = new URL(source);
    const next = new URL(target);
    return !next.username && !next.password && origin.origin === next.origin;
  } catch {
    return false;
  }
}

export function validResource(source: string, target: string, development: boolean): boolean {
  if (!validSource(target, development)) return false;
  try {
    return new URL(target).protocol === 'https:' || sameOrigin(source, target);
  } catch {
    return false;
  }
}
