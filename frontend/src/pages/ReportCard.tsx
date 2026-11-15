import { getLocale, t, useLocale } from '@/i18n';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts';
import { Download } from '@phosphor-icons/react';
import { toast } from 'sonner';
import { LearningRecordLayout } from '@/components/LearningRecordLayout';
import { Skeleton } from '@/components/ui/skeleton';
import api from '@/lib/api';

interface ReportData {
  student: { id: number; nickname: string; elo_score: number; date_joined: string };
  stats: {
    total_attempted: number; total_distinct: number; correct_count: number; wrong_count: number;
    mastered_count: number; accuracy: number; study_streak: number; checkin_streak: number;
    last_accuracy?: number | null; lifetime_accuracy?: number | null;
    attempted_questions?: number; has_attempts?: boolean;
    diagnostic_mastered_count?: number; diagnostic_kp_count?: number;
  };
  radar: { subject: string; avg_mastery: number; kp_count: number }[];
  daily_activity: { date: string; count: number }[];
  exams: { id: number; total_score: number; max_score: number; percentage: number; elo_change: number; created_at: string }[];
  achievements: { key: string; name: string; description: string; icon: string; category: string; unlocked_at: string }[];
}

export const ReportCard = () => {
  useLocale();
  const [data, setData] = useState<ReportData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const fetchData = () => {
    api.get<ReportData>('/users/me/report-card/')
      .then(res => { setData(res.data); setError(false); })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  };
  useEffect(() => { fetchData(); }, []);

  const handleDownloadPDF = async () => {
    if (downloading) return;
    setDownloading(true);
    try {
      const res = await api.get('/users/me/report-card/pdf/', { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `report_${data?.student.nickname || 'student'}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error(t('报告下载失败，请重试')); }
    finally { setDownloading(false); }
  };

  return <LearningRecordLayout action={<button className="um-record-button" onClick={handleDownloadPDF} disabled={downloading || loading || error || !data}><Download size={16} />{downloading ? t('生成中…') : t('下载 PDF')}</button>}>
    {loading ? <div className="um-record-loading" aria-label={t('加载成绩报告')} aria-busy="true"><Skeleton className="h-24 w-full" /><Skeleton className="h-64 w-full" /></div>
      : error ? <div className="um-record-empty" role="alert"><p>{t('成绩报告加载失败。')}</p><button className="um-record-button" onClick={() => { setLoading(true); setError(false); fetchData(); }}>{t('重试')}</button></div>
      : !data ? <div className="um-record-empty"><p>{t('暂无成绩报告')}</p><Link to="/xiaoyu">{t('开始学习')}</Link></div>
      : <>
        <div className="um-record-identity"><span>{data.student.nickname || t('学习者')}</span><span>{t('累计学习记录')}</span></div>
        <dl className="um-record-metrics">
          {[
            { label: t('累计答题'), value: data.stats.total_attempted, unit: t('次') },
            {
              label: t('最近作答正确率'),
              value: data.stats.last_accuracy ?? (data.stats.has_attempts === false ? '—' : data.stats.accuracy),
              unit: data.stats.has_attempts === false ? '' : '%',
            },
            { label: t('连续学习'), value: data.stats.study_streak, unit: t('天') },
            { label: 'ELO', value: data.student.elo_score, unit: '' },
          ].map(item => <div key={item.label}><dt>{item.label}</dt><dd>{item.value}<small>{item.unit}</small></dd></div>)}
        </dl>
        <dl className="um-record-details">
          {[
            [t('练习题目'), data.stats.attempted_questions ?? data.stats.total_distinct, t('道')],
            [t('最近答对'), data.stats.correct_count, t('道')],
            [t('曾答错'), data.stats.wrong_count, t('道')],
            [t('已标记掌握'), data.stats.mastered_count, t('道题')],
            [t('诊断掌握知识点'), `${data.stats.diagnostic_mastered_count ?? 0}/${data.stats.diagnostic_kp_count ?? 0}`, t('个')],
            [t('连续打卡'), data.stats.checkin_streak, t('天')],
            [t('已解锁成就'), data.achievements.length, t('个')],
          ].map(([label, value, unit]) => <div key={label}><dt>{label}</dt><dd>{value} {unit}</dd></div>)}
        </dl>
        <div className="um-record-charts">
          <section aria-label={t('知识点掌握度')}><h2>{t('知识点掌握度（基于诊断）')}</h2>
            {data.radar.length ? <>
              <div className="um-record-chart"><ResponsiveContainer width="100%" height="100%"><RadarChart data={data.radar}>
                <PolarGrid stroke="var(--um-color-border)" />
                <PolarAngleAxis dataKey="subject" tick={{ fontSize: 12, fill: 'var(--um-color-text-muted)' }} />
                <PolarRadiusAxis angle={90} domain={[0, 100]} tick={false} />
                <Radar name={t('掌握度')} dataKey="avg_mastery" stroke="var(--um-color-accent)" fill="var(--um-color-accent)" fillOpacity={0.12} strokeWidth={2} />
              </RadarChart></ResponsiveContainer></div>
              <ul className="um-record-subjects">{data.radar.map(item => <li key={item.subject}><span>{item.subject}</span><strong>{item.avg_mastery}%</strong></li>)}</ul>
            </> : <p className="um-record-chart-empty">{t('完成诊断后查看知识点掌握度。')}</p>}
          </section>
          <section aria-label={t('考试成绩趋势')}><h2>{t('考试成绩趋势')}</h2>
            {data.exams.length ? <div className="um-record-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={data.exams.slice().reverse()} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
              <CartesianGrid vertical={false} stroke="var(--um-color-border)" strokeDasharray="3 3" />
              <XAxis dataKey="created_at" tickFormatter={(value: string) => value.slice(5, 10)} tick={{ fontSize: 12, fill: 'var(--um-color-text-muted)' }} axisLine={false} tickLine={false} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 12, fill: 'var(--um-color-text-muted)' }} axisLine={false} tickLine={false} />
              <Tooltip formatter={(value: unknown) => [`${value}%`, t('得分率')]} labelFormatter={(label: unknown) => t('考试 {0}', { 0: String(label) })} contentStyle={{ background: 'var(--um-color-surface)', borderColor: 'var(--um-color-border)', borderRadius: 8, fontSize: 12 }} />
              <Bar dataKey="percentage" fill="var(--um-color-accent)" radius={[3, 3, 0, 0]} maxBarSize={32} />
            </BarChart></ResponsiveContainer></div> : <p className="um-record-chart-empty">{t('完成考试后查看成绩变化。')}</p>}
          </section>
        </div>
        <section className="um-record-section"><header><h2>{t('考试记录')}</h2><Link to="/tests">{t('进入习题训练')}</Link></header>
          {data.exams.length ? <div className="um-record-table-scroll"><table><thead><tr><th scope="col">{t('日期')}</th><th scope="col">{t('得分')}</th><th scope="col">{t('得分率')}</th><th scope="col">{t('ELO 变化')}</th></tr></thead><tbody>{data.exams.map(item => <tr key={item.id}><td><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleDateString(getLocale())}</time></td><td>{item.total_score} / {item.max_score}</td><td>{item.percentage}%</td><td>{item.elo_change >= 0 ? '+' : ''}{item.elo_change}</td></tr>)}</tbody></table></div> : <p className="um-record-muted">{t('暂无考试记录。')}</p>}
        </section>
        {!!data.achievements.length && <section className="um-record-section"><header><h2>{t('已解锁成就')}</h2><Link to="/achievements">{t('查看全部成就')}</Link></header><ul className="um-record-unlocked">{data.achievements.map(item => <li key={item.key}><span>{item.name}</span><span>{item.description}</span></li>)}</ul></section>}
      </>}
  </LearningRecordLayout>;
};

export default ReportCard;
