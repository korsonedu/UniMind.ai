import type { AnchorHTMLAttributes } from 'react';
import { useProtectedMedia } from '@/hooks/useProtectedMedia';

export function ProtectedMediaLink({ href, ...props }: AnchorHTMLAttributes<HTMLAnchorElement>) {
  const media = useProtectedMedia(href);
  return <a {...props} href={media.src || undefined} aria-disabled={!media.src || undefined} />;
}
