import { t, useLocale } from '@/i18n';
import React, { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ArrowCounterClockwise, CheckCircle, Globe, PlugsConnected, Spinner, Warning } from '@phosphor-icons/react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { queryClient } from '@/lib/queryClient';
import {
  SERVER_ORIGIN_CHANGED_EVENT,
  SERVER_ORIGIN_PRESETS,
  clearServerOrigin,
  getDefaultNativeOrigin,
  getServerOrigin,
  getStoredServerOrigin,
  normalizeServerOrigin,
  setServerOrigin,
} from '@/lib/serverConfig';
import { flushNativeToken, useAuthStore } from '@/store/useAuthStore';

type ConnectionTestState =
  | { status: 'idle' }
  | { status: 'testing'; origin: string }
  | { status: 'ok'; origin: string }
  | { status: 'error'; origin: string; message: string };

interface ServerConfigControlProps {
  variant?: 'pill' | 'button' | 'outline';
  label?: string;
  className?: string;
  onOriginChanged?: (origin: string) => void;
}

const AUTH_ROUTES = ['/login', '/register', '/verify-code', '/account-callback'];

export const ServerConfigControl: React.FC<ServerConfigControlProps> = ({
  variant = 'pill',
  label,
  className,
  onOriginChanged,
}) => {
  useLocale();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [activeOrigin, setActiveOrigin] = useState(() => getServerOrigin());
  const [hasCustom, setHasCustom] = useState(() => !!getStoredServerOrigin());
  const [draft, setDraft] = useState(() => getServerOrigin());
  const [testState, setTestState] = useState<ConnectionTestState>({ status: 'idle' });
  const [saving, setSaving] = useState(false);
  const testAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const sync = () => {
      const next = getServerOrigin();
      setActiveOrigin(next);
      setHasCustom(!!getStoredServerOrigin());
    };
    window.addEventListener(SERVER_ORIGIN_CHANGED_EVENT, sync);
    return () => window.removeEventListener(SERVER_ORIGIN_CHANGED_EVENT, sync);
  }, []);

  useEffect(() => () => {
    testAbortRef.current?.abort();
  }, []);

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen);
    if (nextOpen) {
      const current = getServerOrigin();
      setActiveOrigin(current);
      setHasCustom(!!getStoredServerOrigin());
      setDraft(current);
      setTestState({ status: 'idle' });
    } else {
      testAbortRef.current?.abort();
    }
  };

  const resolveCandidate = (): string | null => normalizeServerOrigin(draft, { defaultScheme: 'http' });

  const handleTestConnection = async () => {
    const candidate = resolveCandidate();
    if (!candidate) {
      setTestState({
        status: 'error',
        origin: draft.trim(),
        message: t('请输入以 http:// 或 https:// 开头的有效地址（例如 http://192.168.1.10:8000）'),
      });
      return;
    }
    setDraft(candidate);
    testAbortRef.current?.abort();
    const controller = new AbortController();
    testAbortRef.current = controller;
    const timeoutId = window.setTimeout(() => controller.abort(), 6000);
    setTestState({ status: 'testing', origin: candidate });
    try {
      const response = await fetch(`${candidate}/health/`, {
        method: 'GET',
        credentials: 'omit',
        cache: 'no-store',
        signal: controller.signal,
      });
      if (!response.ok) {
        setTestState({
          status: 'error',
          origin: candidate,
          message: t('服务端返回 HTTP {status}，请确认地址和端口是否正确。', { status: response.status }),
        });
        return;
      }
      const data = (await response.json().catch(() => null)) as { status?: unknown; database?: unknown; cache?: unknown } | null;
      if (!data || data.status !== 'ok' || typeof data.database !== 'boolean' || typeof data.cache !== 'boolean') {
        setTestState({
          status: 'error',
          origin: candidate,
          message: t('目标响应不是 UniMind 后端服务（缺少健康检查字段）。'),
        });
        return;
      }
      setTestState({ status: 'ok', origin: candidate });
    } catch (err: unknown) {
      if (controller.signal.aborted) {
        setTestState({
          status: 'error',
          origin: candidate,
          message: t('连接超时，请检查局域网 IP、电脑防火墙或 adb reverse tcp:8000 tcp:8000。'),
        });
      } else {
        const msg = err instanceof Error ? t(err.message) : t('网络不可达');
        setTestState({
          status: 'error',
          origin: candidate,
          message: t('连接失败（{message}）。请检查协议、IP、端口或后端 CORS 设置。', { message: msg }),
        });
      }
    } finally {
      window.clearTimeout(timeoutId);
    }
  };

  const applyServerOriginChange = async (nextOrigin: string, previousOrigin: string) => {
    setActiveOrigin(nextOrigin);
    setHasCustom(!!getStoredServerOrigin());
    if (nextOrigin !== previousOrigin) {
      await queryClient.cancelQueries();
      queryClient.clear();
      if (useAuthStore.getState().demoActive) await useAuthStore.getState().exitDemo();
      useAuthStore.getState().logout({ preserveDesktop: true });
      await flushNativeToken();
      toast.success(t('已切换服务器：{origin}', { origin: nextOrigin }));
      onOriginChanged?.(nextOrigin);
      if (!AUTH_ROUTES.includes(location.pathname)) {
        navigate('/login', { replace: true });
      }
    } else {
      toast.success(t('服务器地址已确认'));
    }
    setOpen(false);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (saving) return;
    const candidate = resolveCandidate();
    if (!candidate) {
      setTestState({
        status: 'error',
        origin: draft.trim(),
        message: t('请输入以 http:// 或 https:// 开头的有效服务器地址'),
      });
      return;
    }
    setSaving(true);
    try {
      const previous = getServerOrigin();
      await applyServerOriginChange(candidate, previous);
      setServerOrigin(candidate);
      if (candidate !== previous) window.location.replace('/login');
    } catch (err: unknown) {
      setTestState({
        status: 'error',
        origin: candidate,
        message: err instanceof Error ? t(err.message) : t('保存失败'),
      });
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (saving) return;
    setSaving(true);
    try {
      const previous = getServerOrigin();
      const fallback = getDefaultNativeOrigin();
      setDraft(fallback);
      setTestState({ status: 'idle' });
      await applyServerOriginChange(fallback, previous);
      clearServerOrigin();
      if (fallback !== previous) window.location.replace('/login');
    } catch (error: unknown) {
      setTestState({ status: 'error', origin: draft.trim(), message: error instanceof Error ? t(error.message) : t('恢复默认地址失败，请重试') });
    } finally {
      setSaving(false);
    }
  };

  const defaultOrigin = getDefaultNativeOrigin();

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        {variant === 'pill' ? (
          <button
            type="button"
            className={`inline-flex w-full items-center justify-between gap-2 rounded-xl border border-border/80 bg-muted/40 px-3.5 py-2.5 text-left text-xs text-foreground transition-colors hover:bg-muted/70 min-h-[44px] ${className || ''}`}
          >
            <span className="flex min-w-0 items-center gap-2">
              <Globe className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
              <span className="truncate font-mono text-[12px]">{activeOrigin}</span>
            </span>
            <span className="shrink-0 font-medium text-primary">{label || t('服务器地址')}</span>
          </button>
        ) : (
          <Button
            type="button"
            variant={variant === 'outline' ? 'outline' : 'default'}
            className={`min-h-[44px] gap-2 ${className || ''}`}
          >
            <PlugsConnected className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{label || t('配置服务器地址')}</span>
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader className="text-left">
          <DialogTitle className="text-lg">{t('服务器地址')}</DialogTitle>
          <DialogDescription className="text-xs leading-relaxed">
            {t('支持局域网开发机、真机 USB 转发或线上 HTTPS 地址。切换服务器后将清空本地缓存并重新登录。')}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={e => void handleSave(e)} className="space-y-4">
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <label htmlFor="um-server-origin-input" className="font-medium text-foreground">
                {t('服务端地址（Origin）')}
              </label>
              <span>{hasCustom ? t('已自定义') : t('默认配置')}</span>
            </div>
            <Input
              id="um-server-origin-input"
              type="url"
              inputMode="url"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              placeholder="http://192.168.1.100:8000"
              value={draft}
              onChange={e => {
                setDraft(e.target.value);
                if (testState.status !== 'idle') setTestState({ status: 'idle' });
              }}
              className="h-11 font-mono text-base sm:text-sm"
            />
          </div>

          <div className="space-y-1.5">
            <span className="block text-xs font-medium text-muted-foreground">{t('快捷选择')}</span>
            <div className="flex flex-wrap gap-2">
              {SERVER_ORIGIN_PRESETS.map(preset => (
                <button
                  key={preset.origin}
                  type="button"
                  onClick={() => {
                    setDraft(preset.origin);
                    setTestState({ status: 'idle' });
                  }}
                  className="inline-flex min-h-[44px] items-center rounded-lg border border-border bg-muted/40 px-2.5 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-muted"
                >
                  {t(preset.label)}
                </button>
              ))}
            </div>
          </div>

          {testState.status === 'ok' && (
            <div className="flex items-start gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2.5 text-xs text-emerald-700 dark:border-emerald-800/50 dark:bg-emerald-950/30 dark:text-emerald-300">
              <CheckCircle className="mt-0.5 h-4 w-4 shrink-0" weight="fill" aria-hidden="true" />
              <span>{t('连接成功：{origin} 已响应 UniMind 服务。', { origin: testState.origin })}</span>
            </div>
          )}

          {testState.status === 'error' && (
            <div className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2.5 text-xs text-red-700 dark:border-red-800/40 dark:bg-red-950/30 dark:text-red-400">
              <Warning className="mt-0.5 h-4 w-4 shrink-0" weight="fill" aria-hidden="true" />
              <span>{testState.message}</span>
            </div>
          )}

          <DialogFooter className="gap-2 sm:gap-2">
            {(hasCustom || draft.trim() !== defaultOrigin) && (
              <Button
                type="button"
                variant="ghost"
                disabled={saving}
                onClick={() => void handleReset()}
                className="min-h-[44px] gap-1.5 sm:mr-auto"
              >
                <ArrowCounterClockwise className="h-4 w-4" aria-hidden="true" />
                {t('恢复默认')}
              </Button>
            )}
            <Button
              type="button"
              variant="outline"
              disabled={saving || testState.status === 'testing'}
              onClick={() => void handleTestConnection()}
              className="min-h-[44px] gap-1.5"
            >
              {testState.status === 'testing' ? (
                <Spinner className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <PlugsConnected className="h-4 w-4" aria-hidden="true" />
              )}
              {t('测试连接')}
            </Button>
            <Button type="submit" disabled={saving} className="min-h-[44px]">
              {saving ? t('应用中...') : t('保存并应用')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};
