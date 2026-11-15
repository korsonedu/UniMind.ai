import { getLocale, t, useLocale } from '@/i18n';
import { useState, useEffect } from 'react';
import { Check } from '@phosphor-icons/react';
import api from '@/lib/api';
import { LearningRecordLayout } from '@/components/LearningRecordLayout';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';

interface AchievementData {
  id: number;
  key: string;
  name: string;
  description: string;
  category: string;
  category_label: string;
  threshold: number;
  is_unlocked: boolean;
  unlocked_at: string | null;
  progress: number;
}

const CATEGORIES = [
  { key: 'all', label: '全部' },
  { key: 'streak', label: '连续打卡' },
  { key: 'question', label: '答题' },
  { key: 'diagnostic', label: '诊断' },
  { key: 'mastery', label: '知识掌握' },
  { key: 'exam', label: '考试' },
];

export function Achievements() {
  useLocale();
  const [data, setData] = useState<AchievementData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [category, setCategory] = useState('all');
  const fetchData = () => {
    api.get<AchievementData[]>('/users/achievements/')
      .then(res => { setData(res.data); setError(false); })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  };
  useEffect(() => { fetchData(); }, []);

  const unlocked = data.filter(item => item.is_unlocked).length;
  const filtered = category === 'all' ? data : data.filter(item => item.category === category);
  return <LearningRecordLayout>
    {loading ? <div className="um-record-loading" aria-label={t('加载成就')} aria-busy="true"><Skeleton className="h-16 w-full" /><Skeleton className="h-64 w-full" /></div>
      : error ? <div className="um-record-empty" role="alert"><p>{t('成就加载失败。')}</p><button className="um-record-button" onClick={() => { setLoading(true); setError(false); fetchData(); }}>{t('重试')}</button></div>
      : !data.length ? <div className="um-record-empty"><p>{t('暂无成就')}</p><span>{t('开始学习后，在这里查看解锁进度。')}</span></div>
      : <>
        <div className="um-achievement-summary"><div><strong>{unlocked}<span> / {data.length}</span></strong><p>{t('已解锁成就')}</p></div><progress value={unlocked} max={data.length} aria-label={t('成就解锁进度')} /></div>
        <Tabs value={category} onValueChange={setCategory}>
          <TabsList className="um-achievement-filters" aria-label={t('成就分类')}>
            {CATEGORIES.map(item => <TabsTrigger key={item.key} value={item.key}>{t(item.label)}</TabsTrigger>)}
          </TabsList>
        </Tabs>
        <ul className="um-achievement-list">
          {filtered.map(item => {
            const progress = Math.min(item.threshold, Math.max(0, item.progress));
            return <li key={item.key} data-unlocked={item.is_unlocked}>
              <div className="um-achievement-status" aria-hidden="true">{item.is_unlocked ? <Check size={16} /> : <span />}</div>
              <div className="um-achievement-description"><h2>{t(item.name)}</h2><p>{t(item.description)}</p></div>
              <div className="um-achievement-progress">
                {item.is_unlocked ? <><span>{t('已解锁')}</span>{item.unlocked_at && <time dateTime={item.unlocked_at}>{new Date(item.unlocked_at).toLocaleDateString(getLocale())}</time>}</>
                  : <><span>{progress} / {item.threshold}</span><progress value={progress} max={Math.max(1, item.threshold)} aria-label={t('{0}进度', { 0: item.name })} /></>}
              </div>
            </li>;
          })}
        </ul>
        {!filtered.length && <p className="um-record-empty">{t('该分类暂无成就。')}</p>}
      </>}
  </LearningRecordLayout>;
}
