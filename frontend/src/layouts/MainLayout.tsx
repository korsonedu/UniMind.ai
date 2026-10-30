import React, { useState, useEffect, useCallback } from 'react';
import { Portal as TooltipPortal } from '@radix-ui/react-tooltip';
import { Link, useLocation, Outlet, useNavigate, useNavigationType } from 'react-router-dom';
import { User as UserIcon, SignOut, CreditCard, ChartBar, Trophy, ArrowLeft, ArrowRight, SidebarSimple } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';
import api from '@/lib/api';
import { queryClient } from '@/lib/queryClient';
import { Button } from '@/components/ui/button';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { useAuthStore } from '@/store/useAuthStore';
import { useSystemStore } from '@/store/useSystemStore';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import { NotificationBell } from '@/components/NotificationBell';
import { EloPopover } from '@/components/EloPopover';
import { useIsMobile } from '@/lib/useIsMobile';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog';
import GuidedTour, { type TourStep } from '@/components/GuidedTour';
import { ExamActivityBar } from '@/components/ExamActivityBar';
import { WorkspaceTrail } from '@/components/WorkspaceTrail';
import { WorkspaceActiveContext, WorkspaceToolbarHostContext } from '@/components/WorkspaceContext';
import { XiaoYu } from '@/pages/XiaoYu';
import { useExamActivity } from '@/hooks/useExamActivity';
import '@/styles/app-shell.css';
import { useDesktopStore } from '@/lib/desktop';
import { useDesktopRuntime } from '@/hooks/useDesktopRuntime';

type NavItem = { to: string; icon: string; label: string; mobileLabel: string; feature?: string };

const navItems: NavItem[] = [
  { to: '/notes', icon: '0% 0%', label: '我的笔记', mobileLabel: '笔记' },
  { to: '/xiaoyu', icon: '50% 0%', label: '小宇', mobileLabel: '小宇', feature: 'ai.assistant' },
  { to: '/report-card', icon: '100% 0%', label: '学习记录', mobileLabel: '记录', feature: 'full.report' },
  { to: '/courses', icon: '0% 100%', label: '课程中心', mobileLabel: '课程', feature: 'course.video' },
  { to: '/tests', icon: '50% 100%', label: '习题训练', mobileLabel: '做题', feature: 'quiz.exam' },
  { to: '/community', icon: '100% 100%', label: '学习社区', mobileLabel: '社区' },
];

function NavIcon({ position }: { position: string }) {
  return <span aria-hidden="true" className="um-nav-icon" style={{ maskPosition: position, WebkitMaskPosition: position }} />;
}

const tourSteps: TourStep[] = [
  { target: '[data-tour="xiaoyu-input"]', title: '跟小宇对话', content: '问知识点、刷题、看分析。试试「帮我复习一下三角函数」', placement: 'bottom' },
  { target: '[data-tour="sidebar"]', title: '你的学习空间', content: '课程、习题训练、学习记录和学习社区都在这里。', placement: 'right' },
  { target: '[data-tour="header-right"]', title: '账号和消息', content: '修改资料、系统通知、签到', placement: 'bottom' },
];

export const MainLayout: React.FC = () => {
  const location = useLocation();
  const navigationType = useNavigationType();
  const historyIndex: number = window.history.state?.idx ?? 0;
  const [historyEnd, setHistoryEnd] = useState(historyIndex);
  const [toolbarHost, setToolbarHost] = useState<HTMLDivElement | null>(null);
  const [railHidden, setRailHidden] = useState(false);
  useEffect(() => { setHistoryEnd(old => navigationType === 'PUSH' ? historyIndex : Math.max(old, historyIndex)); }, [location.key, navigationType, historyIndex]);
  const navigate = useNavigate();
  const user = useAuthStore(state => state.user);
  useDesktopRuntime(user?.id);
  const pendingLearningRecords = useDesktopStore(state => state.state?.learningSync?.pending ?? 0);
  const logout = useAuthStore(state => state.logout);
  const updateUser = useAuthStore(state => state.updateUser);
  const { primaryColor, pageTitle } = useSystemStore();
  const { fetchFeatures, hasFeature, loading: featuresLoading, exitPreview } = useInstitutionStore();
  const isMobile = useIsMobile();
  const [showLogoutAlert, setShowLogoutAlert] = useState(false);
  const [showTour, setShowTour] = useState(false);
  const [xiaoyuMounted, setXiaoyuMounted] = useState(location.pathname === '/xiaoyu');
  const hasWorkspaceToolbar = ['/xiaoyu', '/courses', '/notes'].includes(location.pathname) || location.pathname.startsWith('/notes/') || /^\/course\/\d+/.test(location.pathname);
  const isCommunityWorkspace = ['/community', '/qa', '/study'].includes(location.pathname) || location.pathname.startsWith('/qa/');
  const isIntegratedWorkspace = isCommunityWorkspace || location.pathname === '/settings' || location.pathname === '/notes' || location.pathname.startsWith('/notes/')
    || (location.pathname === '/xiaoyu' && hasFeature('ai.assistant'))
    || ((location.pathname === '/courses' || /^\/course\/\d+/.test(location.pathname)) && hasFeature('course.video'));
  const isMobileStudyPage = isMobile && location.pathname === '/study';
  const isMobileImmersivePage = isMobile && ((location.pathname.startsWith('/tests/session') && hasFeature('quiz.exam')) || (location.pathname.startsWith('/xiaoyu/practice') && hasFeature('ai.assistant')));
  const isMobileVideoPage = isMobile && location.pathname.startsWith('/course/') && hasFeature('course.video');
  const hideMobileBottomNav = isMobile && (isMobileImmersivePage || isMobileVideoPage || (location.pathname === '/study' && hasFeature('study.room')));
  const isTourPage = location.pathname === '/xiaoyu';
  const xiaoyuVisible = location.pathname === '/xiaoyu';
  const showXiaoyu = (xiaoyuMounted || xiaoyuVisible) && !featuresLoading && hasFeature('ai.assistant');
  useExamActivity();

  useEffect(() => {
    if (xiaoyuVisible) setXiaoyuMounted(true);
  }, [xiaoyuVisible]);

  useEffect(() => {
    document.documentElement.style.setProperty('--primary-override', primaryColor);
    document.title = 'UniMind.ai 学习平台';
  }, [primaryColor]);

  useEffect(() => {
    if (useInstitutionStore.getState().previewMode) void exitPreview();
    else void fetchFeatures();
  }, [fetchFeatures, exitPreview, location.pathname]);

  useEffect(() => {
    const refresh = () => { if (document.visibilityState === 'visible') void fetchFeatures(); };
    window.addEventListener('focus', refresh);
    return () => window.removeEventListener('focus', refresh);
  }, [fetchFeatures]);

  const handleTourDismiss = useCallback(async () => {
    setShowTour(false);
    try {
      await api.patch('/users/me/tour-dismiss/');
      updateUser({ tour_dismissed_at: new Date().toISOString() });
    } catch {
      // Retry on a later visit when the account update is unavailable.
    }
  }, [updateUser]);

  useEffect(() => {
    if (!isTourPage || isMobile || user?.tour_dismissed_at) return;
    let attempts = 0;
    const poll = setInterval(() => {
      if (document.querySelector(tourSteps[0].target)) {
        clearInterval(poll);
        setShowTour(true);
      } else if (++attempts >= 20) clearInterval(poll);
    }, 300);
    return () => clearInterval(poll);
  }, [isTourPage, isMobile, user?.tour_dismissed_at]);

  useEffect(() => {
    if (showTour && !isTourPage) void handleTourDismiss();
  }, [showTour, isTourPage, handleTourDismiss]);

  const canEnter = (item: NavItem) => {
    if (item.to === '/community') return !featuresLoading && (hasFeature('faq.system') || hasFeature('study.room'));
    return !item.feature || (!featuresLoading && hasFeature(item.feature));
  };
  const isActive = (item: NavItem) => {
    const path = location.pathname;
    if (item.to === '/community') return isCommunityWorkspace;
    if (item.to === '/courses') return path === '/courses' || path.startsWith('/course/');
    if (item.to === '/report-card') return path === '/report-card' || path === '/achievements';
    return path === item.to || path.startsWith(`${item.to}/`);
  };

  const workspaceHeader = user ? <div data-tour="header-right" className="um-app-header-actions">
    <EloPopover />
    <NotificationBell />
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild><button id="avatar-btn" aria-label="账户菜单" className="um-app-avatar-button"><Avatar className="h-7 w-7"><AvatarImage src={user.avatar_url} /><AvatarFallback className="text-[10px] font-bold">{user.username?.[0]}</AvatarFallback></Avatar></button></DropdownMenuTrigger>
      <DropdownMenuContent align="end" side="bottom" className="um-app-menu w-52 p-1">
        <DropdownMenuLabel className="px-3 py-2 text-xs font-medium text-muted-foreground">{user.nickname || user.username}</DropdownMenuLabel>
        {[
          { to: '/settings', icon: UserIcon, label: '个人设置' },
          { to: '/billing', icon: CreditCard, label: '我的服务' },
          { to: '/achievements', icon: Trophy, label: '成就' },
        ].map(item => <DropdownMenuItem key={item.to} onClick={() => navigate(item.to)} className="rounded-lg px-3 py-2 gap-3 cursor-pointer"><item.icon className="h-3.5 w-3.5" /><span className="font-medium text-[13px]">{item.label}</span></DropdownMenuItem>)}
        <DropdownMenuItem onClick={() => window.dispatchEvent(new Event('open-weekly-report'))} className="rounded-lg px-3 py-2 gap-3 cursor-pointer"><ChartBar className="h-3.5 w-3.5" /><span className="font-medium text-[13px]">周报</span></DropdownMenuItem>
        <DropdownMenuSeparator className="my-2 bg-border" />
        <DropdownMenuItem onClick={() => setShowLogoutAlert(true)} className="rounded-lg px-3 py-2 gap-3 cursor-pointer text-destructive focus:bg-destructive focus:text-destructive-foreground"><SignOut className="h-3.5 w-3.5" /><span className="font-medium text-[13px]">退出登录</span></DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  </div> : null;

  return <TooltipProvider delayDuration={0}>
    <div className="um-app-shell flex flex-col h-dvh bg-background text-foreground overflow-hidden font-sans selection:bg-primary selection:text-primary-foreground">
      <header className="um-window-toolbar" aria-label="工作区功能区">
        <div className="um-window-navigation"><button aria-label="返回" title="返回" disabled={historyIndex <= 0} onClick={() => navigate(-1)}><ArrowLeft size={17} /></button><button aria-label="前进" title="前进" disabled={historyIndex >= historyEnd} onClick={() => navigate(1)}><ArrowRight size={17} /></button></div>
        <div className="um-window-workspace" ref={setToolbarHost}>{!hasWorkspaceToolbar && <><button className="um-agent-icon-button" aria-label="切换导航栏" onClick={() => setRailHidden(old => !old)}><SidebarSimple size={18} /></button><WorkspaceTrail title={pageTitle || '学习空间'} crumbs={[]} /></>}</div>
        {workspaceHeader}
      </header>
      <div className="um-window-body flex flex-1 min-h-0 overflow-hidden">
      <aside data-tour="sidebar" aria-label="应用导航" className={cn('um-app-rail relative flex-col p-1.5 z-0 shrink-0 hidden md:flex w-[58px]', railHidden && 'md:hidden')}>
        <div className="um-app-brand flex justify-center"><Link to="/xiaoyu" className="shrink-0" aria-label="返回小宇"><div className="h-9 w-9 rounded-lg overflow-hidden"><img src="/unimind_logo_small.png" alt="UniMind.ai" className="w-full h-full object-contain brand-logo-invert" /></div></Link></div>
        <nav aria-label="功能导航" className="flex-1 min-h-0 overflow-y-auto space-y-1.5">
          {navItems.map(item => <div key={item.to} className="px-1"><Tooltip><TooltipTrigger asChild><Button variant="ghost" asChild className={cn('w-full h-9 rounded-lg justify-center p-0', !canEnter(item) ? 'opacity-40 cursor-not-allowed text-muted-foreground' : isActive(item) ? 'bg-primary/10 text-primary' : 'cursor-pointer text-muted-foreground hover:bg-muted hover:text-foreground')}>{canEnter(item) ? <Link to={item.to} aria-label={item.label} aria-current={isActive(item) ? 'page' : undefined}><NavIcon position={item.icon} /><span className="sr-only">{item.label}</span></Link> : <span role="link" tabIndex={0} aria-label={item.label} aria-disabled="true"><NavIcon position={item.icon} /><span className="sr-only">{item.label}</span></span>}</Button></TooltipTrigger><TooltipPortal><TooltipContent side="right" sideOffset={10} className="font-medium text-[13px] rounded-lg border-border shadow-sm">{item.label}{!canEnter(item) && ' · 暂未开通'}</TooltipContent></TooltipPortal></Tooltip></div>)}
        </nav>
      </aside>
      <main className={cn('um-app-main flex-1 min-w-0 min-h-0 relative z-[var(--z-base)] flex flex-col bg-background',
        isMobileImmersivePage || isMobileStudyPage ? 'overflow-hidden pb-0' : isIntegratedWorkspace ? hideMobileBottomNav ? 'overflow-hidden pb-0' : 'overflow-hidden pb-[calc(61px+env(safe-area-inset-bottom))] md:pb-0' : 'overflow-y-auto pb-[calc(5rem+env(safe-area-inset-bottom))] md:pb-0')}>
        <ExamActivityBar />
        <div className={cn('um-app-page-content flex-1 w-full relative min-h-0', isMobileImmersivePage || isMobileStudyPage ? 'px-0 py-0 h-full overflow-hidden' : isMobileVideoPage ? 'px-0 py-0' : !isIntegratedWorkspace && 'px-4 py-4 md:px-8 md:py-6', isMobile && !hideMobileBottomNav && !isIntegratedWorkspace && 'pb-20')}>
          <WorkspaceToolbarHostContext.Provider value={{ host: toolbarHost, enabled: xiaoyuVisible }}>
            <WorkspaceActiveContext.Provider value={xiaoyuVisible}>
              {showXiaoyu && <div className={xiaoyuVisible ? 'contents' : 'hidden'} aria-hidden={!xiaoyuVisible || undefined} inert={!xiaoyuVisible || undefined}>
                <XiaoYu />
              </div>}
            </WorkspaceActiveContext.Provider>
          </WorkspaceToolbarHostContext.Provider>
          <Outlet context={{ toolbarHost }} />
        </div>
      </main>
      </div>
      <nav className={cn('md:hidden fixed bottom-0 inset-x-0 z-[var(--z-dropdown)] border-t border-border bg-card/95 backdrop-blur-xl pb-[env(safe-area-inset-bottom)]', hideMobileBottomNav && 'hidden')}>
        <div className="um-app-mobile-links flex items-center justify-around px-1 py-2">{navItems.map(item => canEnter(item) ? <Link key={item.to} to={item.to} aria-current={isActive(item) ? 'page' : undefined} className={cn('relative flex flex-col items-center justify-center gap-0.5 py-1 px-1 rounded-lg transition-colors min-h-[44px] min-w-[40px]', isActive(item) ? 'text-primary' : 'text-muted-foreground hover:text-foreground')}>{isActive(item) && <span className="absolute top-0 inset-x-3 h-0.5 bg-primary rounded-full" />}<NavIcon position={item.icon} /><span className="text-[10px] font-bold">{item.mobileLabel}</span></Link> : <span key={item.to} role="link" aria-disabled="true" aria-label={`${item.label}，暂未开通`} className="flex flex-col items-center justify-center gap-0.5 py-1 px-1 min-h-[44px] min-w-[40px] text-muted-foreground opacity-40 cursor-not-allowed"><NavIcon position={item.icon} /><span className="text-[10px] font-bold">{item.mobileLabel}</span></span>)}</div>
      </nav>
      <AlertDialog open={showLogoutAlert} onOpenChange={setShowLogoutAlert}><AlertDialogContent className="rounded-lg border-border bg-card"><AlertDialogHeader><AlertDialogTitle>确认退出登录？</AlertDialogTitle><AlertDialogDescription>退出后需要重新登录才能访问学习记录和课程。{pendingLearningRecords > 0 && ` 当前还有 ${pendingLearningRecords} 条离线学习记录未同步，退出会清除这些记录，建议先返回桌面设置联网同步。`}</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>返回</AlertDialogCancel><AlertDialogAction onClick={async () => { try { await api.post('/users/logout/'); } catch { /* Local logout remains available. */ } await queryClient.cancelQueries(); queryClient.clear(); logout(); navigate('/login', { replace: true }); }}>确认退出</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
      {showTour && isTourPage && <GuidedTour steps={tourSteps} onDismiss={handleTourDismiss} />}
    </div>
  </TooltipProvider>;
};
