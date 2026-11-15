import { t, useLocale } from '@/i18n';
import type { ReactNode } from 'react';
import { NavLink } from 'react-router-dom';
import { PageWrapper } from './PageWrapper';
import '@/styles/learning-record.css';

export function LearningRecordLayout({ children, action }: { children: ReactNode; action?: ReactNode }) {
  useLocale();
  return <PageWrapper title={t('学习记录')}>
    <div className="um-learning-record">
      <header className="um-record-header"><h1>{t('学习记录')}</h1>{action}</header>
      <nav className="um-record-tabs" aria-label={t('学习记录分类')}>
        <NavLink to="/report-card">{t('成绩报告')}</NavLink>
        <NavLink to="/achievements">{t('成就')}</NavLink>
      </nav>
      {children}
    </div>
  </PageWrapper>;
}
