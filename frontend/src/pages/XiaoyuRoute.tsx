import { Suspense, lazy, useEffect, useState } from 'react';
import api from '@/lib/api';

const LegacyXiaoYu = lazy(() => import('./XiaoYu').then(module => ({ default: module.XiaoYu })));
const DshXiaoYu = lazy(() => import('./DshM0'));

const enabled = import.meta.env.VITE_DSH_XIAOYU_ENABLED === 'true';

function LoadingScreen() {
  return <div className="flex min-h-screen items-center justify-center text-sm text-black/45">正在进入小宇…</div>;
}

/**
 * Official XiaoYu entry. The harness path is opt-in at build time and only
 * activates when the server reports a usable DSH model; any failure falls back
 * to the legacy page.
 */
export function XiaoyuRoute() {
  const [useDsh, setUseDsh] = useState<boolean | null>(enabled ? null : false);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    api.get<{ mode?: string }>('/ai/dsh/status/', { timeout: 3000 })
      .then(({ data }) => { if (!cancelled) setUseDsh(data.mode !== 'unavailable'); })
      .catch(() => { if (!cancelled) setUseDsh(false); });
    return () => { cancelled = true; };
  }, []);

  if (useDsh === null) return <LoadingScreen />;
  return <Suspense fallback={<LoadingScreen />}>
    {useDsh ? <DshXiaoYu production /> : <LegacyXiaoYu />}
  </Suspense>;
}
