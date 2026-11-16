import { useState } from 'react';
import { t, useLocale } from '@/i18n';
import { demoPractice } from '@/lib/demoSeed';
import { demoPlaybackStage } from '@/lib/demoPlayback';

export function OfflineTrialPage({ calendar = false }: { calendar?: boolean }) {
  useLocale();
  const [answer, setAnswer] = useState<number | null>(null);
  const [stage, setStage] = useState(1);
  const practice = demoPractice();
  const steps = [t('今天 · 阅读学习笔记 · 20分钟'), t('明天 · 主动回忆知识点 · 15分钟'), t('后天 · 整理学习笔记 · 10分钟')];
  return <section className="min-w-0 max-w-full p-5 space-y-4" aria-label={t('离线试用')}>
    <h1 className="text-xl font-semibold">{calendar ? t('学习日历') : t('离线练习')}</h1>
    <p>{t('离线示例保存在本机。连接服务器后可使用完整学习服务。')}</p>
    {calendar ? <>
      <ul className="space-y-4" aria-live="polite">{demoPlaybackStage(steps, stage).map(step => <li key={step}>{step}</li>)}</ul>
      <button className="min-h-11 rounded-lg border px-4" disabled={stage >= steps.length} onClick={() => setStage(value => value + 1)}>{t('下一步')}</button>
      <button className="min-h-11 rounded-lg border px-4 ml-2" onClick={() => setStage(1)}>{t('重置')}</button>
    </> : <>
      <p>{practice.question}</p>
      {practice.options.map((option, index) => <button key={index} className="block min-h-11 w-full rounded-lg border p-3 text-left" aria-pressed={answer === index} onClick={() => setAnswer(index)}>{option}</button>)}
      {answer !== null && <p role="status">{answer === 0 ? practice.explanation : practice.retry}</p>}
    </>}
  </section>;
}
