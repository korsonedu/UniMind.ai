import type { ImgHTMLAttributes } from 'react';
import { useProtectedMedia } from '@/hooks/useProtectedMedia';

export function ProtectedImage({ src, ...props }: ImgHTMLAttributes<HTMLImageElement>) {
  const media = useProtectedMedia(src);
  return <img {...props} src={media.src || undefined} crossOrigin={media.crossOrigin} />;
}
