import { useEffect, useState } from 'react';
import axios from 'axios';
import { queryClient } from '@/lib/queryClient';
import { useAuthStore } from '@/store/useAuthStore';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import { getReturnTo } from '@/lib/routing';

export function AccountCallback() {
  const [error, setError] = useState(false);
  const accountCenter = import.meta.env.VITE_ACCOUNT_CENTER_ORIGIN || (import.meta.env.DEV ? 'http://localhost:8000' : window.location.origin);
  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    const load = async () => {
      try {
        // Discard previous-account caches before the authoritative identity request.
        await queryClient.cancelQueries();
        queryClient.clear();
        useAuthStore.getState().logout({ preserveDesktop: true });
        const { data: user } = await axios.get(`${import.meta.env.VITE_API_URL || '/api'}/users/me/`, {
          withCredentials: true, timeout: 30000, signal: controller.signal,
        });
        if (cancelled) return;
        useAuthStore.getState().setAuth(user, null);
        await useInstitutionStore.getState().fetchFeatures();
        if (!cancelled) window.location.replace(getReturnTo(new URLSearchParams(window.location.search).get('next')));
      } catch {
        if (!cancelled) setError(true);
      }
    };
    void load();
    return () => { cancelled = true; controller.abort(); };
  }, []);
  return <main className="min-h-dvh flex flex-col items-center justify-center gap-4 px-6 bg-background text-foreground">
    <h1 className="text-xl font-semibold">{error ? '暂时无法进入 UniMind' : '正在确认你的账号'}</h1>
    <p className="text-sm text-muted-foreground">{error ? '请重试，或重新登录科晟账号。' : '确认后将进入 UniMind。'}</p>
    {error && <><button onClick={() => window.location.reload()} className="underline">重试</button><a href={`${accountCenter}/accounts/login/?next=%2Faccounts%2Funimind%2F`} className="underline">重新登录</a></>}
  </main>;
}
