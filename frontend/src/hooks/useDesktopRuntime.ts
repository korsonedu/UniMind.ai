import { useEffect, useLayoutEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDesktopStore } from '@/lib/desktop';

export function useDesktopRuntime(userId?: number) {
  const navigate = useNavigate();
  const navigateRef = useRef(navigate);
  useLayoutEffect(() => { navigateRef.current = navigate; }, [navigate]);
  useEffect(() => {
    const desktop = window.unimindDesktop;
    if (!desktop) return;
    let active = true;
    const unsubscribeState = desktop.onStateChanged(state => { if (active) useDesktopStore.setState({ state, error: null }); });
    const unsubscribeNavigation = desktop.onNavigate(route => {
      if (/^\/(?:settings|xiaoyu|courses|notes)(?:[/?#]|$)/.test(route)) navigateRef.current(route);
    });
    const sync = async () => {
      try {
        const state = userId ? await desktop.syncIdentity() : await desktop.getState();
        if (active) useDesktopStore.setState({ state, error: null });
      } catch (error) {
        if (active) useDesktopStore.setState({ error: String(error instanceof Error ? error.message : error) });
      }
    };
    useDesktopStore.setState({ state: null, error: null });
    void sync();
    window.addEventListener('online', sync);
    const unsubscribeResume = desktop.onResume?.(() => { void sync(); });
    return () => { active = false; unsubscribeState(); unsubscribeNavigation(); unsubscribeResume?.(); window.removeEventListener('online', sync); };
  }, [userId]);
}
