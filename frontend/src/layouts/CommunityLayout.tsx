import { type ReactNode } from 'react';
import { Link, NavLink, Navigate, Outlet, useLocation, useOutletContext } from 'react-router-dom';
import { CaretLeft } from '@phosphor-icons/react';
import { FEATURES, useInstitutionStore } from '@/store/useInstitutionStore';
import { useAuthStore } from '@/store/useAuthStore';
import '@/styles/community.css';

const channels = [
  { path: '/study', name: '自习室', description: '专注计时与即时交流', feature: FEATURES.STUDY_ROOM },
  { path: '/qa', name: '课程答疑', description: '问题、解答与后续讨论', feature: FEATURES.FAQ_SYSTEM },
];

export function CommunityEntry() {
  const { hasFeature, loading } = useInstitutionStore();
  if (loading) return <p className="p-6 text-sm text-muted-foreground">正在打开学习社区…</p>;
  return <Navigate to={hasFeature(FEATURES.FAQ_SYSTEM) ? '/qa' : hasFeature(FEATURES.STUDY_ROOM) ? '/study' : '/qa'} replace />;
}

export function CommunityLayout() {
  const { workspaceHeader } = useOutletContext<{ workspaceHeader?: ReactNode }>() || {};
  const { hasFeature, loading } = useInstitutionStore();
  const user = useAuthStore(s => s.user);
  const location = useLocation();
  const currentChannel = channels.find(channel => channel.path === location.pathname || location.pathname.startsWith(`${channel.path}/`));
  const homePath = user?.institution_role === 'student' ? '/xiaoyu' : '/workbench';

  return (
    <div className="um-community">
      <aside className="um-community-directory" aria-label="社区频道">
        <div className="um-community-heading"><h1>学习社区</h1><p>一起学习，也一起讨论。</p></div>
        <nav aria-label="学习社区频道">
          {channels.filter(channel => !loading && hasFeature(channel.feature)).map(channel => (
            <NavLink key={channel.path} to={channel.path} className={({ isActive }) => `um-community-channel${isActive ? ' is-active' : ''}`}>
              <span>{channel.name}</span><small>{channel.description}</small>
            </NavLink>
          ))}
        </nav>
      </aside>
      <section className="um-community-main" aria-label={currentChannel?.name || '学习社区'}>
        <header className="um-community-header">
          <div className="um-community-header-title">
            <Link to={homePath} className="um-community-back" aria-label="返回主页"><CaretLeft size={20} /></Link>
            <div><h2><span className="um-community-desktop-title">{currentChannel?.name || '学习社区'}</span><span className="um-community-mobile-title">学习社区</span></h2><p>{currentChannel?.description}</p></div>
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
