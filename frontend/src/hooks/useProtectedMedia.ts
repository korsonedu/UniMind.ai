import { useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import api from '@/lib/api';
import { getServerOrigin, isNativePlatform, resolveAssetUrl } from '@/lib/serverConfig';
import { useAuthStore } from '@/store/useAuthStore';

/** Only backend /media paths receive tickets; external images never receive credentials. */
export function getProtectedMediaPath(source?: string | null): string | null {
  if (!source || !isNativePlatform()) return null;
  try {
    const url = new URL(source, `${getServerOrigin()}/`);
    return url.origin === getServerOrigin() && url.pathname.startsWith('/media/') ? url.pathname : null;
  } catch { return null; }
}

export function useProtectedMedia(source?: string | null, beforeRenew?: () => void) {
  const issuedPath = useRef<string | null>(null);
  const path = getProtectedMediaPath(source);
  const token = useAuthStore(state => state.token);
  const userId = useAuthStore(state => state.user?.id);
  const query = useQuery({
    queryKey: ['native-media', getServerOrigin(), userId, path],
    enabled: !!path && !!token,
    queryFn: async ({ signal }) => {
      const { data } = await api.post<{ ticket: string; path: string; expires_in: number }>('/media-ticket/', { path }, { signal });
      if (issuedPath.current === path) beforeRenew?.();
      issuedPath.current = path;
      return `${getServerOrigin()}${data.path}?media_token=${encodeURIComponent(data.ticket)}`;
    },
    staleTime: 240_000,
    gcTime: 300_000,
    refetchInterval: path && token ? 240_000 : false,
    refetchOnWindowFocus: true,
    retry: false,
  });
  return { crossOrigin: path ? 'anonymous' as const : undefined, src: path ? query.data : resolveAssetUrl(source), refresh: query.refetch, error: query.isError };
}
