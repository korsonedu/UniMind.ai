import React, { useState, useEffect, useCallback } from 'react';
import { Portal as TooltipPortal } from '@radix-ui/react-tooltip';
import { Link, useLocation, Outlet, useNavigate } from 'react-router-dom';
import { BookOpen, Trophy, User as UserIcon, SignOut, CreditCard, ChartBar, ChatCircleText, Robot } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';
import api from '@/lib/api';
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
import '@/styles/app-shell.css';

type NavItem = { to: string; icon: React.ComponentType<{ className?: string }>; label: string; mobileLabel: string; feature?: string };

const navItems: NavItem[] = [
  { to: '/xiaoyu', icon: Robot, label: '小宇', mobileLabel: '小宇', feature: 'ai.assistant' },
  { to: '/report-card', icon: ChartBar, label: '学习记录', mobileLabel: '记录', feature: 'full.report' },
  { to: '/courses', icon: BookOpen, label: '课程中心', mobileLabel: '课程', feature: 'course.video' },
  { to: '/tests', icon: Trophy, label: '习题训练', mobileLabel: '做题', feature: 'quiz.exam' },
  { to: '/community', icon: ChatCircleText, label: '学习社区', mobileLabel: '社区' },
];

const tourSteps: TourStep[] = [
  { target: '[data-tour="xiaoyu-input"]', title: '跟小宇对话', content: '问知识点、刷题、看分析。试试「帮我复习一下三角函数」', placement: 'bottom' },
  { target: '[data-tour="sidebar"]', title: '你的学习空间', content: '课程、习题训练、学习记录和学习社区都在这里。', placement: 'right' },
  { target: '[data-tour="header-right"]', title: '账号和消息', content: '修改资料、系统通知、签到', placement: 'bottom' },
];

export const MainLayout: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const user = useAuthStore(state => state.user);
  const logout = useAuthStore(state => state.logout);
  const updateUser = useAuthStore(state => state.updateUser);
  const { primaryColor } = useSystemStore();
  const { fetchFeatures, hasFeature, loading: featuresLoading, exitPreview } = useInstitutionStore();
  const isMobile = useIsMobile();
  const [showLogoutAlert, setShowLogoutAlert] = useState(false);
  const [showTour, setShowTour] = useState(false);
  const isCommunityWorkspace = ['/community', '/qa', '/study'].includes(location.pathname) || location.pathname.startsWith('/qa/');
  const isIntegratedWorkspace = isCommunityWorkspace
    || (location.pathname === '/xiaoyu' && hasFeature('ai.assistant'))
    || ((location.pathname === '/courses' || /^\/course\/\d+/.test(location.pathname)) && hasFeature('course.video'));
  const isMobileStudyPage = isMobile && location.pathname === '/study';
  const isMobileImmersivePage = isMobile && ((location.pathname.startsWith('/tests/session') && hasFeature('quiz.exam')) || (location.pathname.startsWith('/xiaoyu/practice') && hasFeature('ai.assistant')));
  const isMobileVideoPage = isMobile && location.pathname.startsWith('/course/') && hasFeature('course.video');
  const hideMobileBottomNav = isMobile && (isMobileImmersivePage || isMobileVideoPage || (location.pathname === '/study' && hasFeature('study.room')));
  const isTourPage = location.pathname === '/xiaoyu';

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
    <div className="um-app-shell flex h-dvh bg-background text-foreground overflow-hidden font-sans selection:bg-primary selection:text-primary-foreground">
      <aside data-tour="sidebar" aria-label="应用导航" className="um-app-rail relative border-r border-border flex-col p-2 z-0 shrink-0 hidden md:flex w-16">
        <div className="um-app-brand flex justify-center"><Link to="/xiaoyu" className="shrink-0" aria-label="返回小宇"><div className="h-10 w-10 rounded-xl overflow-hidden"><img src="/unimind_logo_small.png" alt="UniMind.ai" className="w-full h-full object-contain brand-logo-invert" /></div></Link></div>
        <nav aria-label="功能导航" className="flex-1 min-h-0 overflow-y-auto space-y-0.5">
          {navItems.map(item => <div key={item.to} className="px-1"><Tooltip><TooltipTrigger asChild><Button variant="ghost" asChild className={cn('w-full h-10 rounded-lg justify-center p-0', !canEnter(item) ? 'opacity-40 cursor-not-allowed text-muted-foreground' : isActive(item) ? 'bg-primary/10 text-primary' : 'cursor-pointer text-muted-foreground hover:bg-muted hover:text-foreground')}>{canEnter(item) ? <Link to={item.to} aria-label={item.label} aria-current={isActive(item) ? 'page' : undefined}><item.icon className="h-[18px] w-[18px] shrink-0" /><span className="sr-only">{item.label}</span></Link> : <span role="link" tabIndex={0} aria-label={item.label} aria-disabled="true"><item.icon className="h-[18px] w-[18px] shrink-0" /><span className="sr-only">{item.label}</span></span>}</Button></TooltipTrigger><TooltipPortal><TooltipContent side="right" sideOffset={10} className="font-medium text-[13px] rounded-lg border-border shadow-sm">{item.label}{!canEnter(item) && ' · 暂未开通'}</TooltipContent></TooltipPortal></Tooltip></div>)}
        </nav>
      </aside>
      <main className={cn('um-app-main flex-1 min-w-0 min-h-0 relative z-[var(--z-base)] flex flex-col bg-background',
        isMobileImmersivePage || isMobileStudyPage ? 'overflow-hidden pb-0' : isIntegratedWorkspace ? hideMobileBottomNav ? 'overflow-hidden pb-0' : 'overflow-hidden pb-[calc(61px+env(safe-area-inset-bottom))] md:pb-0' : 'overflow-y-auto pb-[calc(5rem+env(safe-area-inset-bottom))] md:pb-0')}>
        {!isMobileImmersivePage && !isIntegratedWorkspace && <header className="um-app-global-header sticky top-0 h-12 shrink-0 z-[var(--z-sticky)] flex items-center justify-end gap-2 px-3 md:px-6">{workspaceHeader}</header>}
        <div className={cn('um-app-page-content flex-1 w-full relative min-h-0', isMobileImmersivePage || isMobileStudyPage ? 'px-0 py-0 h-full overflow-hidden' : isMobileVideoPage ? 'px-0 py-0' : !isIntegratedWorkspace && 'px-4 py-4 md:px-8 md:py-6', isMobile && !hideMobileBottomNav && !isIntegratedWorkspace && 'pb-20')}>
          <Outlet context={{ workspaceHeader }} />
        </div>
      </main>
      <nav className={cn('md:hidden fixed bottom-0 inset-x-0 z-[var(--z-dropdown)] border-t border-border bg-card/95 backdrop-blur-xl pb-[env(safe-area-inset-bottom)]', hideMobileBottomNav && 'hidden')}>
        <div className="um-app-mobile-links flex items-center justify-around px-1 py-2">{navItems.map(item => canEnter(item) ? <Link key={item.to} to={item.to} aria-current={isActive(item) ? 'page' : undefined} className={cn('relative flex flex-col items-center justify-center gap-0.5 py-1 px-1 rounded-lg transition-colors min-h-[44px] min-w-[40px]', isActive(item) ? 'text-primary' : 'text-muted-foreground hover:text-foreground')}>{isActive(item) && <span className="absolute top-0 inset-x-3 h-0.5 bg-primary rounded-full" />}<item.icon className="h-5 w-5" /><span className="text-[10px] font-bold">{item.mobileLabel}</span></Link> : <span key={item.to} role="link" aria-disabled="true" aria-label={`${item.label}，暂未开通`} className="flex flex-col items-center justify-center gap-0.5 py-1 px-1 min-h-[44px] min-w-[40px] text-muted-foreground opacity-40 cursor-not-allowed"><item.icon className="h-5 w-5" /><span className="text-[10px] font-bold">{item.mobileLabel}</span></span>)}</div>
      </nav>
      <AlertDialog open={showLogoutAlert} onOpenChange={setShowLogoutAlert}><AlertDialogContent className="rounded-lg border-border bg-card"><AlertDialogHeader><AlertDialogTitle>确认退出登录？</AlertDialogTitle><AlertDialogDescription>退出后需要重新登录才能访问学习记录和课程。</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>返回</AlertDialogCancel><AlertDialogAction onClick={async () => { try { await api.post('/users/logout/'); } catch { /* Local logout remains available. */ } logout(); navigate('/login'); }}>确认退出</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
      {showTour && isTourPage && <GuidedTour steps={tourSteps} onDismiss={handleTourDismiss} />}
    </div>
  </TooltipProvider>;
};
