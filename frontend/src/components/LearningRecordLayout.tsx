import type { ReactNode } from 'react';
import { NavLink } from 'react-router-dom';
import { PageWrapper } from './PageWrapper';
import '@/styles/learning-record.css';

export function LearningRecordLayout({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return <PageWrapper title="学习记录">
    <div className="um-learning-record">
      <header className="um-record-header"><h1>学习记录</h1>{action}</header>
      <nav className="um-record-tabs" aria-label="学习记录分类">
        <NavLink to="/report-card">成绩报告</NavLink>
        <NavLink to="/achievements">成就</NavLink>
      </nav>
      {children}
    </div>
  </PageWrapper>;
}
