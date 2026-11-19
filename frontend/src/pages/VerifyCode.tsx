import { queryClient } from '@/lib/queryClient';
import { queryKeys } from '@/lib/queryKeys';
import { t, useLocale } from '@/i18n';
import { formatApiErrorToast } from '@/lib/apiError';
import React, { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { InputOTP } from '@/components/ui/input-otp';
import { AuthLayout } from '@/components/AuthLayout';
import { useAuthStore, flushNativeToken } from '@/store/useAuthStore';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import { ArrowLeft, Check, X } from '@phosphor-icons/react';
import { REGEXP_ONLY_DIGITS } from 'input-otp';

import api from '@/lib/api';
import { getReturnTo, getLoginPath } from '@/lib/routing';
import '@/styles/verify-code.css';

const CODE_LENGTH = 6;
const sparks = [[-87, -23], [-75, -39], [-56, -36], [-91, -5], [-71, 20],
  [56, -34], [76, -40], [92, -21], [94, 2], [74, 22]];
const pause = (ms: number) => new Promise<void>(resolve => window.setTimeout(resolve, ms));

type Phase = 'entry' | 'complete' | 'verifying' | 'verified' | 'rejected' | 'retry';

export const VerifyCode: React.FC = () => {
  useLocale();
  const [searchParams] = useSearchParams();
  const email = searchParams.get('email') || '';
  const returnTo = getReturnTo(searchParams.get('next'));
  const loginParams = new URLSearchParams({ next: returnTo });
  for (const key of ['institution', 'role']) {
    const value = searchParams.get(key);
    if (value) loginParams.set(key, value);
  }

  const [code, setCode] = useState('');
  const [phase, setPhase] = useState<Phase>('entry');
  const [error, setError] = useState('');
  const [countdown, setCountdown] = useState(60);
  const [resending, setResending] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const verification = useRef<AbortController | null>(null);
  const editable = phase === 'entry' || phase === 'retry';
  const open = editable || phase === 'complete';

  const setAuth = useAuthStore(s => s.setAuth);
  const { fetchFeatures } = useInstitutionStore();
  const navigate = useNavigate();

  useEffect(() => {
    if (countdown <= 0) return;
    const timer = window.setTimeout(() => setCountdown(prev => prev - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [countdown]);

  useEffect(() => {
    if (!email) navigate(getLoginPath(returnTo), { replace: true });
  }, [email, navigate, returnTo]);

  useEffect(() => {
    if (editable && !resending) input.current?.focus({ preventScroll: true });
  }, [editable, resending]);

  useEffect(() => () => verification.current?.abort(), []);

  const handleLogin = async (otp: string) => {
    if (verification.current || resending) return;
    const controller = new AbortController();
    verification.current = controller;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (!reducedMotion) {
      setPhase('complete');
      await pause(125);
      if (controller.signal.aborted) return;
    }
    setPhase('verifying');
    const [result] = await Promise.allSettled([
      api.post('/users/login-by-code/', { email, code: otp }, { signal: controller.signal }),
      pause(reducedMotion ? 0 : 800),
    ]);
    if (controller.signal.aborted) return;

    const retry = async (err: unknown, fallback: string) => {
      setPhase('rejected');
      await pause(reducedMotion ? 0 : 420);
      if (controller.signal.aborted) return;
      verification.current = null;
      setCode('');
      setError(formatApiErrorToast(err, fallback));
      setPhase('retry');
    };

    if (result.status === 'rejected') {
      await retry(result.reason, t('验证码错误，请重试'));
      return;
    }

    const { user, token } = result.value.data;
    await queryClient.cancelQueries({ queryKey: queryKeys.user.me });
    if (controller.signal.aborted) return;
    queryClient.setQueryData(queryKeys.user.me, user);
    setAuth(user, token);
    try {
      await flushNativeToken();
    } catch (err) {
      if (!controller.signal.aborted) await retry(err, t('登录失败'));
      return;
    }
    if (controller.signal.aborted) return;
    setPhase('verified');
    await Promise.all([fetchFeatures(), pause(reducedMotion ? 350 : 950)]);
    if (!controller.signal.aborted) navigate(returnTo, { replace: true });
  };

  const handleCodeChange = (value: string) => {
    if (verification.current) return;
    setCode(value);
    setError('');
    setPhase('entry');
    if (value.length === CODE_LENGTH) void handleLogin(value);
  };

  const handleResend = async () => {
    if (!editable || resending || countdown > 0) return;
    setResending(true);
    setError('');
    try {
      await api.post('/users/send-verification-code/', { email, purpose: 'login_by_code' });
      setCode('');
      setPhase('entry');
      setCountdown(60);
    } catch (err: unknown) {
      setError(formatApiErrorToast(err, t('重发失败')));
    } finally {
      setResending(false);
    }
  };

  if (!email) return null;

  return (
    <AuthLayout
      className="um-auth-login"
      title={t('验证邮箱')}
      subtitle={<>{t('验证码已发送至')}{' '}<span className="um-code-address">{email}</span></>}
    >
      <Link
        to={`/login?${loginParams}`}
        replace
        state={{ email }}
        className="um-code-back"
      >
        <ArrowLeft size={16} aria-hidden="true" />
        {t('返回修改邮箱')}
      </Link>

      <div className="um-code-stage" data-open={open} data-phase={phase}>
        <div className="um-code-capsule">
          <div className="um-code-status" aria-hidden="true" lang="en">
            <span data-status="verifying"><span className="um-code-spinner" />Verifying</span>
            <span data-status="verified"><Check weight="bold" />Verified</span>
            <span data-status="rejected"><X weight="bold" />Try again</span>
          </div>
          <div className="um-code-input">
            <InputOTP
              ref={input}
              aria-label={t('输入 6 位验证码')}
              aria-invalid={phase === 'retry' && !!error}
              aria-describedby={error ? 'otp-error' : undefined}
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern={REGEXP_ONLY_DIGITS}
              pasteTransformer={value => value.replace(/[\s-]/g, '')}
              maxLength={CODE_LENGTH}
              value={code}
              onChange={handleCodeChange}
              readOnly={phase === 'complete'}
              disabled={!open || resending}
              render={({ slots }) => (
                <div className="um-code-slots" aria-hidden="true" style={{
                  '--code-active': Math.max(0, slots.findIndex(slot => slot.isActive)),
                } as React.CSSProperties}>
                  {slots.map(({ char, hasFakeCaret }, index) => (
                    <span className="um-code-slot" key={index} data-filled={!!char}>
                      {char}
                      {hasFakeCaret && <span className="um-code-caret" />}
                    </span>
                  ))}
                  <span className="um-code-focus" />
                </div>
              )}
            />
          </div>
        </div>
        {phase === 'verified' && <span className="um-code-sparks" aria-hidden="true">
          {sparks.map(([x, y]) => <i key={x} style={{ '--spark-x': `${x}px`, '--spark-y': `${y}px` } as React.CSSProperties} />)}
        </span>}
      </div>

      <p role="status" className="sr-only">
        {phase === 'verifying' ? t('验证中...') : phase === 'verified' ? t('验证成功') : ''}
      </p>
      <div className="um-code-feedback">
        {error && <p id="otp-error" className="um-code-error" role="alert">{error}</p>}
      </div>

      <div className="um-code-resend">
        <Button variant="link" size="sm" disabled={!editable || countdown > 0 || resending} onClick={handleResend}>
          {resending ? t('正在发送…') : countdown > 0
            ? <span className="um-code-countdown">{t('{0} 秒后可重发', { 0: countdown })}</span>
            : t('重新发送验证码')}
        </Button>
      </div>
    </AuthLayout>
  );
};
