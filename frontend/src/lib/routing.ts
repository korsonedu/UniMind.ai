export const HOME_PATH = '/xiaoyu';

export function getReturnTo(value: string | null): string {
  if (!value?.startsWith('/') || value.includes('\\') || /\p{Cc}/u.test(value)) return HOME_PATH;
  try {
    const url = new URL(value, 'https://unimind.invalid');
    const pathname = decodeURIComponent(url.pathname);
    if (url.origin !== 'https://unimind.invalid'
      || /^\/(login|register|verify-code|account-callback|api|admin|accounts|account-api|static|media)(\/|$)/i.test(pathname)) return HOME_PATH;
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return HOME_PATH;
  }
}

export function getLoginPath(returnTo: string): string {
  return `/login?${new URLSearchParams({ next: getReturnTo(returnTo) })}`;
}
