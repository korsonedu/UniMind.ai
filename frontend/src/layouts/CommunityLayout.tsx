import { t, useLocale } from '@/i18n';
import { type ReactNode } from 'react';
import { Link, NavLink, Navigate, Outlet, useLocation, useOutletContext } from 'react-router-dom';
import { CaretLeft } from '@phosphor-icons/react';
import { FEATURES, useInstitutionStore } from '@/store/useInstitutionStore';
import '@/styles/community.css';

const channels = [
  { path: '/study', name: '自习室', description: '专注计时与即时交流', feature: FEATURES.STUDY_ROOM },
  { path: '/qa', name: '课程答疑', description: '问题、解答与后续讨论', feature: FEATURES.FAQ_SYSTEM },
];

export function CommunityEntry() {
  useLocale();
  const { hasFeature, loading } = useInstitutionStore();
  if (loading) return <p className="p-6 text-sm text-muted-foreground">{t('正在打开学习社区…')}</p>;
  return <Navigate to={hasFeature(FEATURES.FAQ_SYSTEM) ? '/qa' : hasFeature(FEATURES.STUDY_ROOM) ? '/study' : '/qa'} replace />;
}

export function CommunityLayout() {
  useLocale();
  const { workspaceHeader } = useOutletContext<{ workspaceHeader?: ReactNode }>() || {};
  const { hasFeature, loading } = useInstitutionStore();
  const location = useLocation();
  const currentChannel = channels.find(channel => channel.path === location.pathname || location.pathname.startsWith(`${channel.path}/`));
  const homePath = '/xiaoyu';

  return (
    <div className="um-community">
      <aside className="um-community-directory" aria-label={t('社区频道')}>
        <div className="um-community-heading"><h1>{t('学习社区')}</h1><p>{t('一起学习，也一起讨论。')}</p></div>
        <nav aria-label={t('学习社区频道')}>
          {channels.map(channel => !loading && hasFeature(channel.feature) ? (
            <NavLink key={channel.path} to={channel.path} className={({ isActive }) => `um-community-channel${isActive ? ' is-active' : ''}`}>
              <span>{t(channel.name)}</span><small>{t(channel.description)}</small>
            </NavLink>
          ) : <span key={channel.path} role="link" aria-disabled="true" title={t('暂未开通')} className="um-community-channel opacity-40 cursor-not-allowed"><span>{t(channel.name)}</span><small>{t(channel.description)}</small></span>)}
        </nav>
      </aside>
      <section className="um-community-main" aria-label={t(currentChannel?.name || '学习社区')}>
        <header className="um-community-header">
          <div className="um-community-header-title">
            <Link to={homePath} className="um-community-back" aria-label={t('返回主页')}><CaretLeft size={20} /></Link>
            <div><h2><span className="um-community-desktop-title">{t(currentChannel?.name || '学习社区')}</span><span className="um-community-mobile-title">{t('学习社区')}</span></h2><p>{t(currentChannel?.description || '')}</p></div>
          </div>
          <div className="um-community-account">{workspaceHeader}</div>
        </header>
        <div className={`um-community-content${location.pathname === '/study' ? ' is-study' : ''}`}>
          <Outlet context={{ workspaceHeader }} />
        </div>
      </section>
    </div>
  );
}
