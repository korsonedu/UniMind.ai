import { t, useLocale } from '@/i18n';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, DownloadSimple } from '@phosphor-icons/react';

type Platform = 'mac' | 'windows';
type Release = { version: string; prerelease: boolean; packages: Partial<Record<Platform, string>> };
const labels = { mac: 'macOS · Apple 芯片', windows: 'Windows · x64' };

function detectPlatform(): Platform | null {
  const agent = navigator.userAgent;
  if (/Android|iPhone|iPad|iPod/i.test(agent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)) return null;
  if (/Windows/i.test(agent)) return 'windows';
  if (/Mac/i.test(agent)) return 'mac';
  return null;
}

export function LandingDownload({ entry }: { entry: string }) {
  useLocale();
  const [platform, setPlatform] = useState(detectPlatform);
  const [release, setRelease] = useState<Release | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${import.meta.env.VITE_API_URL || '/api'}/desktop-release/`, { signal: controller.signal, cache: 'no-store' })
      .then(response => {
        if (!response.ok) throw new Error('Release unavailable');
        return response.json() as Promise<Release>;
      })
      .then(setRelease)
      .catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => controller.abort();
  }, [attempt]);

  const url = platform ? release?.packages[platform] : undefined;

  return <div className="landing-download" id="download">
    <div className="landing-hero-actions">
      <Link to={entry} className="landing-button">{t('开始对话')}<ArrowUpRight size={18} /></Link>
      {url && platform ? <a href={url} className="landing-button landing-button-secondary" download>
        <DownloadSimple size={18} />{t('下载')} {platform === 'mac' ? 'macOS' : 'Windows'} {t('版')}
      </a> : <button className="landing-button landing-button-secondary" disabled>
        <DownloadSimple size={18} />{error ? t('下载暂不可用') : !release ? t('获取最新版本…') : platform ? t('暂无对应安装包') : t('选择电脑系统下载')}
      </button>}
    </div>
    <div className="landing-download-options" aria-label={t('选择下载系统')}>
      {(Object.keys(labels) as Platform[]).map(value => <button key={value} type="button" aria-pressed={platform === value}
        disabled={!release?.packages[value]} onClick={() => setPlatform(value)}>{t(labels[value])}</button>)}
    </div>
    <p className="landing-download-note" aria-live="polite">
      {error ? <>{t('暂时无法获取最新版本，')}<button type="button" onClick={() => { setError(false); setAttempt(value => value + 1); }}>{t('重试')}</button></>
        : release ? <>v{release.version}{release.prerelease && t(' · 预发布版')}{platform === 'mac' && t(' · 适用于 M 系列芯片，Intel Mac 暂不支持')}{!platform && t(' · 请在电脑上安装')}</>
          : t('正在确认最新桌面版本')}
    </p>
  </div>;
}
