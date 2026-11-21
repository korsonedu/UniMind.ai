import { isNativeOffline, subscribeOffline, setNativeOffline } from '@/lib/offlineSession';
import { activeWorkspace, spaceStorageKey } from '@/lib/activeWorkspace';
import { t, useLocale } from '@/i18n';
import { useXiaoYuChat } from '@/pages/xiaoyu/xiaoYuChatContext';
import { learningUrl } from '@/lib/projectLearning';
import React, { useState, useEffect, useSyncExternalStore, useCallback, useRef } from 'react';
import { Portal as TooltipPortal } from '@radix-ui/react-tooltip';
import { Link, useLocation, Outlet, useNavigate, useNavigationType } from 'react-router-dom';

import { User as UserIcon, SignOut, CreditCard, ArrowLeft, ArrowRight, SidebarSimple, ChatCircle, ListBullets, Files, NotePencil, BookOpen, SquaresFour, X } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';
import api from '@/lib/api';
import { queryClient } from '@/lib/queryClient';
import { Button } from '@/components/ui/button';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { useAuthStore } from '@/store/useAuthStore';
import { useSystemStore } from '@/store/useSystemStore';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import { NotificationBell } from '@/components/NotificationBell';
import { useIsMobile } from '@/lib/useIsMobile';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog';
import GuidedTour, { type TourStep } from '@/components/GuidedTour';
import { ExamActivityBar } from '@/components/ExamActivityBar';
import { WorkspaceTrail } from '@/components/WorkspaceTrail';
import { ProjectChatSidebarContext, CourseSidebarContext, type SidebarView, type SidebarRecentItem, NotesSidebarContext, WorkspaceActiveContext, WorkspaceToolbarHostContext } from '@/components/WorkspaceContext';
import { useExamActivity } from '@/hooks/useExamActivity';
import '@/styles/app-shell.css';
import NotesSidebar from '@/pages/notes/NotesSidebar';
import { SavedCoursesPanel } from '@/components/course/SavedCoursesPanel';
import { SpaceSwitcher } from '@/components/SpaceSwitcher';
import { SidebarHome } from '@/components/SidebarHome';
import { SidebarResizeHandle } from '@/components/SidebarResizeHandle';
import { useDesktopStore } from '@/lib/desktop';
import { useDesktopRuntime } from '@/hooks/useDesktopRuntime';

type NavItem = { to: string; icon: string; label: string; mobileLabel: string; feature?: string };

const NAV_ITEMS: NavItem[] = [
  { to: '/notes', icon: '0% 0%', label: '我的笔记', mobileLabel: '笔记' },
  { to: '/xiaoyu', icon: '50% 0%', label: '小宇', mobileLabel: '小宇', feature: 'ai.assistant' },
  { to: '/courses', icon: '0% 100%', label: '课程中心', mobileLabel: '课程', feature: 'course.video' },
  { to: '/tests', icon: '50% 100%', label: '习题训练', mobileLabel: '做题', feature: 'quiz.exam' },
];

function NavIcon({ position }: { position: string }) {
  useLocale();
  return <span aria-hidden="true" className="um-nav-icon" style={{ maskPosition: position, WebkitMaskPosition: position }} />;
}

const TOUR_STEPS: TourStep[] = [
  { target: '[data-tour="xiaoyu-input"]', title: '跟小宇对话', content: '问知识点、刷题、看分析。试试「帮我复习一下三角函数」', placement: 'bottom' },
  { target: '[data-tour="sidebar"]', title: '你的学习空间', content: '从这里打开笔记、课程和习题训练。', placement: 'right' },
  { target: '[data-tour="header-right"]', title: '账号和消息', content: '修改资料和查看系统通知', placement: 'bottom' },
];

export const MainLayout: React.FC = () => {
  useLocale();
  const navItems = NAV_ITEMS.map(item => ({ ...item, label: t(item.label), mobileLabel: t(item.mobileLabel) }));
  const tourSteps = TOUR_STEPS.map(step => ({ ...step, title: t(step.title), content: t(step.content) }));
  const location = useLocation();
  const { chat: projectChat } = useXiaoYuChat();
  const routeFor = (path: string) => ['/notes', '/xiaoyu'].includes(path)
    ? learningUrl(path, projectChat.projectId, projectChat.activeSessionId !== null ? projectChat.conversationId : undefined) : path;
  const navigationType = useNavigationType();
  const historyIndex: number = window.history.state?.idx ?? 0;
  const [historyEnd, setHistoryEnd] = useState(historyIndex);
  const [toolbarHost, setToolbarHost] = useState<HTMLDivElement | null>(null);
  const [railHidden, setRailHidden] = useState(false);
  const [notesOpen, setNotesOpen] = useState(false);
  const [notesMounted, setNotesMounted] = useState(false);
  const [sidebarView, setSidebarView] = useState<SidebarView>('home');
  const [sidebarLocationKey, setSidebarLocationKey] = useState('');
  const [openedSidebarTools, setOpenedSidebarTools] = useState<SidebarView[]>([]);
  const [addedSidebarTools, setAddedSidebarTools] = useState<SidebarView[]>(['chat', 'outline', 'notes', 'saved-courses']);
  const [sidebarRecent, setSidebarRecent] = useState<SidebarRecentItem[]>([]);
  const recordSidebarRecent = useCallback((item: SidebarRecentItem) => {
    setSidebarRecent(previous => [item, ...previous.filter(entry => entry.key !== item.key)].slice(0, 8));
  }, []);
  const [noteOpenRequest, setNoteOpenRequest] = useState<{ id: number; sequence: number } | null>(null);
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    try { const saved = Number(localStorage.getItem(spaceStorageKey('unimind-right-sidebar-width'))); return saved >= 320 && saved <= 640 ? saved : 400; } catch { return 400; }
  });
  const saveSidebarWidth = (value: number) => {
    setSidebarWidth(value);
    try { localStorage.setItem(spaceStorageKey('unimind-right-sidebar-width'), String(value)); } catch { /* Best effort. */ }
  };
  const [projectChatHost, setProjectChatHost] = useState<HTMLDivElement | null>(null);
  const [projectChatAvailability, setProjectChatAvailability] = useState({ key: '', available: false });
  const setProjectChatAvailable = useCallback((available: boolean) => { setProjectChatAvailability({ key: location.key, available }); }, [location.key]);
  const [courseSidebarHost, setCourseSidebarHost] = useState<HTMLDivElement | null>(null);
  const [courseSidebarAvailability, setCourseSidebarAvailability] = useState({ key: '', available: false });
  const setCourseSidebarAvailable = useCallback((available: boolean) => { setCourseSidebarAvailability({ key: location.key, available }); }, [location.key]);
  const selectSidebarView = useCallback((view: SidebarView) => {
    setSidebarView(view); setNotesOpen(true);
    if (view !== 'home') {
      setOpenedSidebarTools(previous => previous.includes(view) ? previous : [...previous, view]);
      setAddedSidebarTools(previous => previous.includes(view) ? previous : [...previous, view]);
    }
    if (view === 'notes') setNotesMounted(true);
  }, []);
  const openProjectChat = useCallback(() => selectSidebarView('chat'), [selectSidebarView]);
  const [historyKey, setHistoryKey] = useState(location.key);
  if (historyKey !== location.key) {
    setHistoryKey(location.key);
    setHistoryEnd(navigationType === 'PUSH' ? historyIndex : Math.max(historyEnd, historyIndex));
  }
  const navigate = useNavigate();
  const user = useAuthStore(state => state.user);
  const [noteSession, setNoteSession] = useState<{ userId?: number; id: number | null }>({ id: null });
  const rememberNote = useCallback((id: number | null, title?: string) => {
    setNoteSession({ userId: user?.id, id });
    if (id) recordSidebarRecent({ key: `note:${id}`, view: 'notes', title: title || t('未命名笔记'), noteId: id });
  }, [user?.id, recordSidebarRecent]);
  const openSidebarRecent = (item: SidebarRecentItem) => {
    if (item.view === 'notes' && item.noteId) setNoteOpenRequest(previous => ({ id: item.noteId!, sequence: (previous?.sequence || 0) + 1 }));
    if (item.view === 'chat' && item.courseId && item.conversationId) navigate(`/course/${item.courseId}?conversation=${encodeURIComponent(item.conversationId)}`);
    selectSidebarView(item.view);
  };
  const closeNotes = useCallback(() => {
    setNotesOpen(false);
    document.getElementById('um-notes-toggle')?.focus({ preventScroll: true });
  }, []);
  const inNotesPage = location.pathname === '/notes' || location.pathname.startsWith('/notes/');
  useDesktopRuntime(user?.id);
  const pendingLearningRecords = useDesktopStore(state => state.state?.learningSync?.pending ?? 0);
  const logout = useAuthStore(state => state.logout);
  const updateUser = useAuthStore(state => state.updateUser);
  const { primaryColor, pageTitle } = useSystemStore();
  const { fetchFeatures, hasFeature, loading: featuresLoading, hasCourseCatalog, exitPreview } = useInstitutionStore();
  const isMobile = useIsMobile();
  const [showLogoutAlert, setShowLogoutAlert] = useState(false);
  const [showTour, setShowTour] = useState(false);
  const [pendingTourDismiss, setPendingTourDismiss] = useState(false);
  const hasWorkspaceToolbar = ['/xiaoyu', '/courses', '/notes'].includes(location.pathname) || location.pathname.startsWith('/notes/') || /^\/course\/\d+/.test(location.pathname);
  const isIntegratedWorkspace = location.pathname.startsWith('/settings') || location.pathname === '/notes' || location.pathname.startsWith('/notes/')
    || (location.pathname === '/xiaoyu' && hasFeature('ai.assistant'))
    || ((location.pathname === '/xiaoyu/knowledge-builder' || location.pathname.startsWith('/xiaoyu/knowledge-builder/')) && hasFeature('ai.assistant'))
    || ((location.pathname === '/courses' || /^\/course\/\d+/.test(location.pathname)) && hasFeature('course.video'));
  const isMobileImmersivePage = isMobile && ((location.pathname.startsWith('/tests/session') && hasFeature('quiz.exam')) || (location.pathname.startsWith('/xiaoyu/practice') && hasFeature('ai.assistant')));
  const isMobileVideoPage = isMobile && location.pathname.startsWith('/course/') && hasFeature('course.video');
  const hideMobileBottomNav = isMobile && (isMobileImmersivePage || isMobileVideoPage);
  const shellRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!isMobile || !window.visualViewport) return;
    const viewport = window.visualViewport;
    const shell = shellRef.current;
    const syncViewport = () => {
      // The visual viewport shrinks for the browser keyboard before layout dvh does.
      if (!shell || viewport.scale !== 1) return;
      shell.style.setProperty('--um-viewport-height', `${viewport.height}px`);
      const editing = document.activeElement?.matches('input, textarea, [contenteditable="true"]');
      shell.dataset.keyboardOpen = String(Boolean(editing && window.innerHeight - viewport.height > 150));
    };
    syncViewport();
    viewport.addEventListener('resize', syncViewport);
    document.addEventListener('focusin', syncViewport);
    document.addEventListener('focusout', syncViewport);
    return () => {
      viewport.removeEventListener('resize', syncViewport);
      document.removeEventListener('focusin', syncViewport);
      document.removeEventListener('focusout', syncViewport);
      shell?.style.removeProperty('--um-viewport-height');
      if (shell) delete shell.dataset.keyboardOpen;
    };
  }, [isMobile]);
  const isTourPage = location.pathname === '/xiaoyu' && activeWorkspace() === 'personal';
  if (showTour && !isTourPage) { setShowTour(false); setPendingTourDismiss(true); }
  const xiaoyuVisible = location.pathname === '/xiaoyu';
  const [notesPageAvailability, setNotesPageAvailability] = useState({ key: '', available: false });
  const setNotesAvailable = useCallback((available: boolean) => { setNotesPageAvailability({ key: location.key, available }); }, [location.key]);
  const notesAvailable = notesPageAvailability.key === location.key && notesPageAvailability.available;
  const courseSidebarAvailable = courseSidebarAvailability.key === location.key && courseSidebarAvailability.available;
  const savedCoursesAvailable = !hasCourseCatalog && hasFeature('course.video') && (xiaoyuVisible || location.pathname === '/courses' || /^\/course\/\d+/.test(location.pathname));
  const projectChatAvailable = xiaoyuVisible && projectChatAvailability.key === location.key && projectChatAvailability.available;
  const sidebarAvailable = projectChatAvailable || notesAvailable || courseSidebarAvailable || savedCoursesAvailable;
  const sidebarVisible = notesOpen && sidebarAvailable;
  const activeSidebarView = (projectChatAvailable && sidebarView === 'chat') || courseSidebarAvailable || sidebarView === 'notes' || (savedCoursesAvailable && sidebarView === 'saved-courses') ? sidebarView : 'home';
  const notesVisible = sidebarVisible && activeSidebarView === 'notes';
  const sidebarTools = [...(courseSidebarAvailable ? [
    { id: 'chat' as const, label: t('小宇'), icon: ChatCircle },
    { id: 'outline' as const, label: t('课程大纲'), icon: ListBullets },
    { id: 'materials' as const, label: t('资料'), icon: Files },
    { id: 'notes' as const, label: t('笔记'), icon: NotePencil },
  ] : [...(projectChatAvailable ? [{ id: 'chat' as const, label: t('小宇'), icon: ChatCircle }] : []), { id: 'notes' as const, label: t('笔记'), icon: NotePencil }]), ...(savedCoursesAvailable ? [{ id: 'saved-courses' as const, label: t('已保存课程'), icon: BookOpen }] : [])];
  const sidebarTabs = openedSidebarTools.map(id => sidebarTools.find(tool => tool.id === id)).filter(tool => !!tool);
  if (!featuresLoading && sidebarLocationKey !== location.key) {
    setSidebarLocationKey(location.key);
    if (savedCoursesAvailable && new URLSearchParams(location.search).get('panel') === 'saved-courses') selectSidebarView('saved-courses');
    else if (sidebarView === 'saved-courses') setSidebarView('home');
  }
  useExamActivity();

  useEffect(() => {
    document.documentElement.style.setProperty('--primary-override', primaryColor);
    document.title = t('UniMind.ai 学习平台');
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
    if (!pendingTourDismiss) return;
    void api.patch('/users/me/tour-dismiss/').then(() => {
      updateUser({ tour_dismissed_at: new Date().toISOString() });
    }).catch(() => {}).finally(() => setPendingTourDismiss(false));
  }, [pendingTourDismiss, updateUser]);

  const visibleNavItems = navItems;
  const canEnter = (item: NavItem) => {
    return !item.feature || (!featuresLoading && hasFeature(item.feature));
  };
  const isActive = (item: NavItem) => {
    const path = location.pathname;
    if (item.to === '/courses') return path === '/courses' || path.startsWith('/course/');
    return path === item.to || path.startsWith(`${item.to}/`);
  };

  const workspaceHeader = user ? <div data-tour="header-right" className="um-app-header-actions">
    <NotificationBell />
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild><button id="avatar-btn" aria-label={t('账户菜单')} className="um-app-avatar-button"><Avatar className="h-7 w-7"><AvatarImage src={user.avatar_url} /><AvatarFallback className="text-[10px] font-bold">{user.username?.[0]}</AvatarFallback></Avatar></button></DropdownMenuTrigger>
      <DropdownMenuContent align="end" side="bottom" className="um-app-menu w-52 p-1">
        <DropdownMenuLabel className="px-3 py-2 text-xs font-medium text-muted-foreground">{user.nickname || user.username}</DropdownMenuLabel>
        {[
          { to: '/settings', icon: UserIcon, label: t('个人设置') },
          { to: '/billing', icon: CreditCard, label: t('我的服务') },
        ].map(item => <DropdownMenuItem key={item.to} onClick={() => navigate(item.to)} className="rounded-lg px-3 py-2 gap-3 cursor-pointer"><item.icon className="h-3.5 w-3.5" /><span className="font-medium text-[13px]">{item.label}</span></DropdownMenuItem>)}
        <DropdownMenuSeparator className="my-2 bg-border" />
        <DropdownMenuItem onClick={() => setShowLogoutAlert(true)} className="rounded-lg px-3 py-2 gap-3 cursor-pointer text-destructive focus:bg-destructive focus:text-destructive-foreground"><SignOut className="h-3.5 w-3.5" /><span className="font-medium text-[13px]">{t('退出登录')}</span></DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  </div> : null;

  const nativeOffline = useSyncExternalStore(subscribeOffline, isNativeOffline);
  const demoActive = useAuthStore(state => state.demoActive);
  return <TooltipProvider delayDuration={0}>
    <div ref={shellRef} data-mobile-nav-hidden={hideMobileBottomNav} className="um-app-shell flex flex-col h-dvh bg-background text-foreground overflow-hidden font-sans selection:bg-primary selection:text-primary-foreground" data-nav-history={historyIndex > 0 || historyIndex < historyEnd ? 'true' : undefined}>
      <header className="um-window-toolbar" aria-label={t('工作区功能区')}>
        <SpaceSwitcher />
        <div className="um-window-navigation"><button aria-label={t('返回')} title={t('返回')} disabled={historyIndex <= 0} onClick={() => navigate(-1)}><ArrowLeft size={17} /></button><button aria-label={t('前进')} title={t('前进')} disabled={historyIndex >= historyEnd} onClick={() => navigate(1)}><ArrowRight size={17} /></button></div>
        <div className="um-window-workspace" ref={setToolbarHost}>{!hasWorkspaceToolbar && <><button className="um-agent-icon-button hidden md:inline-flex" aria-label={t('切换导航栏')} onClick={() => setRailHidden(old => !old)}><SidebarSimple size={18} /></button><WorkspaceTrail title={pageTitle || t('学习空间')} crumbs={[]} /></>}</div>
        {workspaceHeader}
        {sidebarAvailable && <button id="um-notes-toggle" data-native-back-close={sidebarVisible ? true : undefined} type="button" className="um-right-sidebar-toggle um-agent-icon-button" aria-label={t('切换右侧栏')} title={sidebarVisible ? t('收起右侧栏') : t('展开右侧栏')} aria-expanded={sidebarVisible} aria-controls="um-right-panel" onClick={() => { setNotesOpen(value => !value); }}><SidebarSimple size={19} style={{ transform: 'scaleX(-1)' }} /></button>}
      </header>
      {(nativeOffline || demoActive) && <div role="status" className="flex shrink-0 items-center justify-between gap-2 bg-amber-50 text-amber-950 px-3 py-1 text-xs"><span>{demoActive ? t('离线试用 · 数据仅保存在本机') : t('离线缓存 · 已使用本地离线缓存')}</span><button type="button" className="min-h-11 underline shrink-0" onClick={() => { if (demoActive) { void useAuthStore.getState().exitDemo().then(() => { queryClient.clear(); navigate('/login', { replace: true }); }); } else { setNativeOffline(false); navigate('/settings'); void queryClient.invalidateQueries(); } }}>{demoActive ? t('连接服务器 / 退出试用') : t('重新连接 / 服务器设置')}</button></div>}
      <div className="um-window-body flex flex-1 min-h-0 overflow-hidden">
      <aside data-tour="sidebar" aria-label={t('应用导航')} className={cn('um-app-rail relative flex-col p-1.5 z-0 shrink-0 hidden md:flex w-[58px]', railHidden && 'md:hidden')}>
        <div className="um-app-brand flex justify-center"><Link to="/xiaoyu" className={cn('flex h-9 w-9 shrink-0 items-center justify-center rounded-lg', location.pathname.startsWith('/xiaoyu') && 'bg-primary/10')} aria-label={t('小宇')} title={t('小宇')} aria-current={location.pathname.startsWith('/xiaoyu') ? 'page' : undefined}>
          <svg viewBox="0 0 100 100" className="h-8 w-8" aria-hidden="true" focusable="false">
            <defs><linearGradient id="um-sidebar-brand-gradient" gradientUnits="userSpaceOnUse" x1="15" y1="90" x2="90" y2="10"><stop stopColor="#2f6cea" /><stop offset=".5" stopColor="#535fe7" /><stop offset="1" stopColor="#9252d8" /></linearGradient></defs>
            <g fill="url(#um-sidebar-brand-gradient)">
              <path d="M18 36C18 13 48 13 48 36C48 13 78 13 78 36V61C78 79 67 89 48 89S18 79 18 61Z" fill="none" stroke="url(#um-sidebar-brand-gradient)" strokeWidth="12" strokeLinejoin="round" />
              <rect x="33" y="48" width="8" height="13" rx="4" />
              <rect x="56" y="48" width="8" height="13" rx="4" />
              <circle cx="90" cy="14" r="5" />
            </g>
          </svg>
        </Link></div>
        <nav aria-label={t('功能导航')} className="flex-1 min-h-0 overflow-y-auto space-y-1.5">
          {visibleNavItems.filter(item => item.to !== '/xiaoyu').map(item => <div key={item.to} className="px-1"><Tooltip><TooltipTrigger asChild><Button variant="ghost" asChild className={cn('w-full h-9 rounded-lg justify-center p-0', !canEnter(item) ? 'opacity-40 cursor-not-allowed text-muted-foreground' : isActive(item) ? 'bg-primary/10 text-primary' : 'cursor-pointer text-muted-foreground hover:bg-muted hover:text-foreground')}>{canEnter(item) ? <Link to={routeFor(item.to)} aria-label={item.label} aria-current={isActive(item) ? 'page' : undefined}>{<NavIcon position={item.icon} />}<span className="sr-only">{item.label}</span></Link> : <span role="link" tabIndex={0} aria-label={item.label} aria-disabled="true">{<NavIcon position={item.icon} />}<span className="sr-only">{item.label}</span></span>}</Button></TooltipTrigger><TooltipPortal><TooltipContent side="right" sideOffset={10} className="font-medium text-[13px] rounded-lg border-border shadow-sm">{item.label}{!canEnter(item) && t(' · 暂未开通')}</TooltipContent></TooltipPortal></Tooltip></div>)}
        </nav>
      </aside>
      <div className="um-window-panes" data-notes-open={sidebarVisible} style={{ '--um-notes-width': `${sidebarWidth}px` } as React.CSSProperties}>
      <main inert={isMobile && sidebarVisible} className={cn('um-app-main flex-1 min-w-0 min-h-0 relative z-[var(--z-base)] flex flex-col bg-background',
        isMobileImmersivePage ? 'overflow-hidden pb-0' : isIntegratedWorkspace ? hideMobileBottomNav ? 'overflow-hidden pb-0' : 'overflow-hidden pb-[calc(61px+var(--safe-area-inset-bottom,env(safe-area-inset-bottom,0px)))] md:pb-0' : 'overflow-y-auto pb-[calc(61px+var(--safe-area-inset-bottom,env(safe-area-inset-bottom,0px)))] md:pb-0')}>
        <ExamActivityBar />
        <div className={cn('um-app-page-content flex-1 w-full relative min-h-0', isMobileImmersivePage ? 'px-0 py-0 h-full overflow-hidden' : isMobileVideoPage ? 'px-0 py-0' : !isIntegratedWorkspace && 'px-4 py-4 md:px-8 md:py-6')}>
          <WorkspaceToolbarHostContext.Provider value={{ host: toolbarHost, enabled: hasWorkspaceToolbar }}>
            <WorkspaceActiveContext.Provider value={xiaoyuVisible}>
              <NotesSidebarContext.Provider value={{ open: notesVisible, close: closeNotes, setAvailable: setNotesAvailable }}>
                <CourseSidebarContext.Provider value={{ host: courseSidebarHost, view: activeSidebarView, visible: sidebarVisible, recordRecent: recordSidebarRecent, setAvailable: setCourseSidebarAvailable }}>
                  <ProjectChatSidebarContext.Provider value={{ host: projectChatHost, visible: sidebarVisible && activeSidebarView === 'chat', open: openProjectChat, close: closeNotes, setAvailable: setProjectChatAvailable }}>
                    <Outlet context={{ toolbarHost }} />
                  </ProjectChatSidebarContext.Provider>
                </CourseSidebarContext.Provider>
              </NotesSidebarContext.Provider>
            </WorkspaceActiveContext.Provider>
          </WorkspaceToolbarHostContext.Provider>
        </div>
      </main>
      {sidebarVisible && <button className="um-notes-mobile-backdrop" aria-label={t('收起右侧栏')} onClick={closeNotes} />}
      {sidebarVisible && !isMobile && <SidebarResizeHandle width={sidebarWidth} onChange={setSidebarWidth} onCommit={saveSidebarWidth} onCollapse={closeNotes} />}
      <div id="um-right-panel" className="um-notes-sidebar-host um-unified-sidebar" data-open={sidebarVisible} aria-hidden={!sidebarVisible} inert={!sidebarVisible} onKeyDown={event => { if (event.key === 'Escape' && !event.defaultPrevented) { event.preventDefault(); closeNotes(); } }}>
        <header className="um-right-panel-header">
          <button type="button" className="um-agent-icon-button" aria-label={t('工具入口')} aria-pressed={activeSidebarView === 'home'} onClick={() => selectSidebarView('home')}><SquaresFour size={18} /></button>
          <div role="tablist" aria-label={t('侧栏功能')}>{sidebarTabs.map((tab, index) => <div className="um-sidebar-tab" key={tab.id}><button id={`sidebar-tab-${tab.id}`} role="tab" type="button" aria-selected={activeSidebarView === tab.id} aria-controls={`sidebar-panel-${tab.id}`} tabIndex={activeSidebarView === tab.id || (activeSidebarView === 'home' && index === 0) ? 0 : -1} onClick={() => selectSidebarView(tab.id)} onKeyDown={event => {
            if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
            event.preventDefault();
            const next = event.key === 'Home' ? 0 : event.key === 'End' ? sidebarTabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + sidebarTabs.length) % sidebarTabs.length;
            selectSidebarView(sidebarTabs[next].id);
            document.getElementById(`sidebar-tab-${sidebarTabs[next].id}`)?.focus();
          }}><tab.icon size={16} /><span>{tab.label}</span></button><button type="button" className="um-sidebar-tab-close" aria-label={t('关闭{0}标签', { 0: tab.label })} onClick={() => {
            setOpenedSidebarTools(previous => previous.filter(id => id !== tab.id));
            if (activeSidebarView === tab.id) setSidebarView('home');
          }}><X size={12} /></button></div>)}</div>
          <button type="button" className="um-agent-icon-button" aria-label={t('关闭右侧栏')} onClick={closeNotes}><X size={17} /></button>
        </header>
        {activeSidebarView === 'home' && <SidebarHome tools={sidebarTools} added={addedSidebarTools} recent={sidebarRecent} onSelect={selectSidebarView} onOpenRecent={openSidebarRecent} />}
        <div ref={setProjectChatHost} id={projectChatAvailable ? 'sidebar-panel-chat' : undefined} role="tabpanel" aria-labelledby="sidebar-tab-chat" className="um-right-panel-content um-native-agent" hidden={!projectChatAvailable || activeSidebarView !== 'chat'} />
        <div ref={setCourseSidebarHost} className="um-course-sidebar-host" hidden={!courseSidebarAvailable || activeSidebarView === 'notes' || activeSidebarView === 'home' || activeSidebarView === 'saved-courses'} />
        <div id="sidebar-panel-saved-courses" role="tabpanel" aria-labelledby="sidebar-tab-saved-courses" className="um-right-panel-content" hidden={activeSidebarView !== 'saved-courses'}>
          {sidebarVisible && savedCoursesAvailable && activeSidebarView === 'saved-courses' && <SavedCoursesPanel />}
        </div>
        <div id="sidebar-panel-notes" role="tabpanel" aria-labelledby="sidebar-tab-notes" className="um-right-panel-content" hidden={activeSidebarView !== 'notes'}>
          {notesMounted && !inNotesPage && user && <NotesSidebar key={user.id} userId={user.id} visible={notesVisible} openRequest={noteOpenRequest} initialNoteId={noteSession.userId === user.id ? noteSession.id : null} onSelect={rememberNote} onClose={closeNotes} />}
        </div>
      </div>
      </div>
      </div>
      <nav className={cn('um-app-mobile-nav md:hidden fixed bottom-0 inset-x-0 z-[var(--z-dropdown)] border-t border-border bg-card/95 backdrop-blur-xl pb-[var(--safe-area-inset-bottom,env(safe-area-inset-bottom,0px))]', hideMobileBottomNav && 'hidden')}>
        <div className="um-app-mobile-links flex items-center justify-start px-1 py-2">{visibleNavItems.map(item => canEnter(item) ? <Link key={item.to} to={routeFor(item.to)} aria-current={isActive(item) ? 'page' : undefined} className={cn('relative flex flex-col items-center justify-center gap-0.5 py-1 px-1 rounded-lg transition-colors min-h-[44px] min-w-[44px] whitespace-nowrap shrink-0', isActive(item) ? 'text-primary' : 'text-muted-foreground hover:text-foreground')}>{isActive(item) && <span className="absolute top-0 inset-x-3 h-0.5 bg-primary rounded-full" />}{<NavIcon position={item.icon} />}<span className="text-[10px] font-bold">{item.mobileLabel}</span></Link> : <span key={item.to} role="link" aria-disabled="true" aria-label={t('{0}，暂未开通', { 0: item.label })} className="flex flex-col items-center justify-center gap-0.5 py-1 px-1 min-h-[44px] min-w-[44px] whitespace-nowrap shrink-0 text-muted-foreground opacity-40 cursor-not-allowed">{<NavIcon position={item.icon} />}<span className="text-[10px] font-bold">{item.mobileLabel}</span></span>)}</div>
      </nav>
      <AlertDialog open={showLogoutAlert} onOpenChange={setShowLogoutAlert}><AlertDialogContent className="rounded-lg border-border bg-card"><AlertDialogHeader><AlertDialogTitle>{t('确认退出登录？')}</AlertDialogTitle><AlertDialogDescription>{t('退出后需要重新登录才能访问学习记录和课程。')}{pendingLearningRecords > 0 && t(' 当前还有 {0} 条离线学习记录未同步，退出会清除这些记录，建议先返回桌面设置联网同步。', { 0: pendingLearningRecords })}</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>{t('返回')}</AlertDialogCancel><AlertDialogAction onClick={async () => { try { await api.post('/users/logout/'); } catch { /* Local logout remains available. */ } await queryClient.cancelQueries(); queryClient.clear(); logout(); navigate('/login', { replace: true }); }}>{t('确认退出')}</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
      {showTour && isTourPage && <GuidedTour steps={tourSteps} onDismiss={handleTourDismiss} />}
    </div>
  </TooltipProvider>;
};
