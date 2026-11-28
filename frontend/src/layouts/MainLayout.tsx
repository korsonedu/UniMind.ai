import { isNativeOffline, subscribeOffline, setNativeOffline } from '@/lib/offlineSession';
import { activeWorkspace, spaceStorageKey } from '@/lib/activeWorkspace';
import { t, useLocale } from '@/i18n';
import { useXiaoYuChat } from '@/pages/xiaoyu/xiaoYuChatContext';
import { learningUrl } from '@/lib/projectLearning';
import { personalWorkbenchProjectId } from '@/lib/workbenchMode';
import React, { useState, useEffect, useLayoutEffect, useSyncExternalStore, useCallback, useRef } from 'react';
import { Portal as TooltipPortal } from '@radix-ui/react-tooltip';
import { Link, useLocation, Outlet, useNavigate, useNavigationType } from 'react-router-dom';

import { User as UserIcon, SignOut, CreditCard, ArrowLeft, ArrowRight, ArrowsOutSimple, ArrowsInSimple, SidebarSimple, Gear, ChatCircle, ListBullets, Files, NotePencil, BookOpen, SquaresFour, TreeStructure, Sparkle, Exam, X, UserPlus, Copy, CaretRight, type Icon } from '@phosphor-icons/react';
import { GlobalMobileDrawer, type MobileNavigationSlot } from '@/components/MobileNavPrimitives';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
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
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useWorkspace } from '@/lib/workspace';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog';
import GuidedTour, { type TourStep } from '@/components/GuidedTour';
import { ExamActivityBar } from '@/components/ExamActivityBar';
import { WorkspaceTrail } from '@/components/WorkspaceTrail';
import { LearningPathSidebarContext, ProjectChatSidebarContext, CourseSidebarContext, type SidebarView, type SidebarRecentItem, NotesSidebarContext, RightSidebarLayoutContext, WorkbenchSidebarContext, WorkspaceActiveContext, WorkspaceToolbarHostContext } from '@/components/WorkspaceContext';
import { useExamActivity } from '@/hooks/useExamActivity';
import '@/styles/app-shell.css';
import NotesSidebar from '@/pages/notes/NotesSidebar';
import { SavedCoursesPanel } from '@/components/course/SavedCoursesPanel';
import { SpaceSwitcher } from '@/components/SpaceSwitcher';
import { SidebarHome } from '@/components/SidebarHome';
import { SidebarResizeHandle } from '@/components/SidebarResizeHandle';
import { clampSidebarWidth, MIN_SIDEBAR_WIDTH, type SidebarDragPreview } from '@/lib/rightSidebarLayout';
import { useDesktopStore } from '@/lib/desktop';
import { useDesktopRuntime } from '@/hooks/useDesktopRuntime';

type NavItem = { to: string; icon: string | Icon; label: string; mobileLabel: string; feature?: string };

const NAV_ITEMS: NavItem[] = [
  { to: '/notes', icon: '0% 0%', label: '我的笔记', mobileLabel: '笔记' },
  { to: '/xiaoyu', icon: '50% 0%', label: '小宇', mobileLabel: '小宇', feature: 'ai.assistant' },
  { to: '/courses', icon: '0% 100%', label: '课程中心', mobileLabel: '课程', feature: 'course.video' },
  { to: '/tests', icon: Exam, label: '习题训练', mobileLabel: '做题', feature: 'quiz.exam' },
];

function NavIcon({ icon: Icon }: { icon: NavItem['icon'] }) {
  useLocale();
  if (typeof Icon !== 'string') return <Icon size={23} aria-hidden="true" />;
  return <span aria-hidden="true" className="um-nav-icon" style={{ maskPosition: Icon, WebkitMaskPosition: Icon }} />;
}

const TOUR_STEPS: TourStep[] = [
  { target: '[data-tour="xiaoyu-input"]', title: '跟小宇对话', content: '问知识点、刷题、看分析。试试「帮我复习一下三角函数」', placement: 'bottom' },
  { target: '[data-tour="sidebar"]', title: '你的学习空间', content: '从这里打开笔记和习题训练。', placement: 'right' },
  { target: '#avatar-btn', title: '账户菜单', content: '修改资料', placement: 'right' },
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
  const [addedSidebarTools, setAddedSidebarTools] = useState<SidebarView[]>(['chat', 'outline', 'notes', 'saved-courses', 'learning-path', 'studio']);
  const [sidebarRecent, setSidebarRecent] = useState<SidebarRecentItem[]>([]);
  const recordSidebarRecent = useCallback((item: SidebarRecentItem) => {
    setSidebarRecent(previous => [item, ...previous.filter(entry => entry.key !== item.key)].slice(0, 8));
  }, []);
  const [noteOpenRequest, setNoteOpenRequest] = useState<{ id: number; sequence: number } | null>(null);
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    try { const saved = Number(localStorage.getItem(spaceStorageKey('unimind-right-sidebar-width'))); return Number.isFinite(saved) && saved >= MIN_SIDEBAR_WIDTH ? saved : 400; } catch { return 400; }
  });
  const [sidebarFullscreen, setSidebarFullscreen] = useState(false);
  const [sidebarPreview, setSidebarPreview] = useState<SidebarDragPreview | null>(null);
  const panesRef = useRef<HTMLDivElement>(null);
  const [panesWidth, setPanesWidth] = useState(0);
  useLayoutEffect(() => {
    const panes = panesRef.current;
    if (!panes) return;
    setPanesWidth(panes.getBoundingClientRect().width);
    const observer = new ResizeObserver(([entry]) => setPanesWidth(entry.contentRect.width));
    observer.observe(panes);
    return () => observer.disconnect();
  }, []);
  const saveSidebarWidth = (value: number) => {
    setSidebarWidth(value);
    if (value >= MIN_SIDEBAR_WIDTH) {
      try { localStorage.setItem(spaceStorageKey('unimind-right-sidebar-width'), String(value)); } catch { /* Best effort. */ }
    }
  };
  const [projectChatHost, setProjectChatHost] = useState<HTMLDivElement | null>(null);
  const [projectChatAvailability, setProjectChatAvailability] = useState({ key: '', available: false });
  const setProjectChatAvailable = useCallback((available: boolean) => { setProjectChatAvailability({ key: location.key, available }); }, [location.key]);
  const [courseSidebarHost, setCourseSidebarHost] = useState<HTMLDivElement | null>(null);
  const [courseSidebarAvailability, setCourseSidebarAvailability] = useState({ key: '', available: false });
  const setCourseSidebarAvailable = useCallback((available: boolean) => { setCourseSidebarAvailability({ key: location.key, available }); }, [location.key]);
  const [learningPathHost, setLearningPathHost] = useState<HTMLDivElement | null>(null);
  const [workbenchSidebarHost, setWorkbenchSidebarHost] = useState<HTMLDivElement | null>(null);
  const [learningPathAvailability, setLearningPathAvailability] = useState(false);
  const [learningPathWidth, setLearningPathWidth] = useState(480);
  const selectSidebarView = useCallback((view: SidebarView) => {
    setSidebarView(view); setNotesOpen(true);
    if (view !== 'home' && view !== 'studio') {
      setOpenedSidebarTools(previous => previous.includes(view) ? previous : [...previous, view]);
      setAddedSidebarTools(previous => previous.includes(view) ? previous : [...previous, view]);
    }
    if (view === 'notes') setNotesMounted(true);
  }, []);
  const openLearningPath = useCallback(() => selectSidebarView('learning-path'), [selectSidebarView]);
  const openSidebarNotes = useCallback(() => selectSidebarView('notes'), [selectSidebarView]);
  const openProjectChat = useCallback(() => selectSidebarView('chat'), [selectSidebarView]);
  const [historyKey, setHistoryKey] = useState(location.key);
  if (historyKey !== location.key) {
    setHistoryKey(location.key);
    setHistoryEnd(navigationType === 'PUSH' ? historyIndex : Math.max(historyEnd, historyIndex));
  }
  const navigate = useNavigate();
  const user = useAuthStore(state => state.user);
  const { data: workspace } = useWorkspace();
  const [inviteOpen, setInviteOpen] = useState(false);
  const invite = useQuery({
    queryKey: ['friend-invitation', user?.account_id ?? user?.id],
    enabled: inviteOpen && !!user,
    queryFn: async ({ signal }) => {
      const { data } = await api.get<{ url: string }>('/payments/referral/', { signal });
      if (!data.url) throw new Error('Missing invitation URL');
      return data.url;
    },
  });
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
    setSidebarFullscreen(false);
    setSidebarPreview(null);
    document.getElementById('um-notes-toggle')?.focus({ preventScroll: true });
  }, [setSidebarFullscreen]);
  const inNotesPage = location.pathname === '/notes' || location.pathname.startsWith('/notes/');
  useDesktopRuntime(user?.id);
  const pendingLearningRecords = useDesktopStore(state => state.state?.learningSync?.pending ?? 0);
  const logout = useAuthStore(state => state.logout);
  const updateUser = useAuthStore(state => state.updateUser);
  const { primaryColor, pageTitle } = useSystemStore();
  const { fetchFeatures, hasFeature, loading: featuresLoading, hasCourseCatalog, exitPreview } = useInstitutionStore();
  const isMobile = useIsMobile();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [showLogoutAlert, setShowLogoutAlert] = useState(false);
  const [showTour, setShowTour] = useState(false);
  const [pendingTourDismiss, setPendingTourDismiss] = useState(false);
  const isPersonalVideo = activeWorkspace() === 'personal' && /^\/course\/\d+/.test(location.pathname);
  const isMobileImmersivePage = isMobile && ((location.pathname.startsWith('/tests/session') && hasFeature('quiz.exam')) || (location.pathname.startsWith('/xiaoyu/practice') && hasFeature('ai.assistant')));
  const hasWorkspaceToolbar = ['/xiaoyu', '/courses', '/notes'].includes(location.pathname) || location.pathname.startsWith('/notes/') || /^\/course\/\d+/.test(location.pathname) || isMobileImmersivePage;
  const isIntegratedWorkspace = isPersonalVideo || location.pathname.startsWith('/settings') || location.pathname === '/notes' || location.pathname.startsWith('/notes/')
    || (location.pathname === '/xiaoyu' && hasFeature('ai.assistant'))
    || ((location.pathname === '/xiaoyu/knowledge-builder' || location.pathname.startsWith('/xiaoyu/knowledge-builder/')) && hasFeature('ai.assistant'))
    || ((location.pathname === '/courses' || /^\/course\/\d+/.test(location.pathname)) && hasFeature('course.video'));
  const isMobileVideoPage = isMobile && (isPersonalVideo || (location.pathname.startsWith('/course/') && hasFeature('course.video')));
  const isMobilePracticeCanvas = isMobile && (
    location.pathname === '/tests'
    || (location.pathname.startsWith('/tests/') && !location.pathname.startsWith('/tests/session'))
    || location.pathname.startsWith('/settings')
    || location.pathname.startsWith('/billing')
  );
  const shellRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!isMobile || !window.visualViewport) return;
    const viewport = window.visualViewport;
    const shell = shellRef.current;
    const root = document.documentElement;
    const syncViewport = () => {
      // The visual viewport shrinks for the browser keyboard before layout dvh does.
      if (!shell || viewport.scale !== 1) return;
      const height = `${viewport.height}px`;
      shell.style.setProperty('--um-viewport-height', height);
      root.style.setProperty('--um-mobile-visual-height', height);
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
      root.style.removeProperty('--um-mobile-visual-height');
      if (shell) delete shell.dataset.keyboardOpen;
    };
  }, [isMobile]);
  const isTourPage = location.pathname === '/xiaoyu' && activeWorkspace() === 'personal';
  if (showTour && !isTourPage) { setShowTour(false); setPendingTourDismiss(true); }
  const xiaoyuVisible = location.pathname === '/xiaoyu';
  const mobileXiaoyu = isMobile && xiaoyuVisible && hasFeature('ai.assistant');
  const [notesPageAvailability, setNotesPageAvailability] = useState({ key: '', available: false });
  const setNotesAvailable = useCallback((available: boolean) => { setNotesPageAvailability({ key: location.key, available }); }, [location.key]);
  const notesAvailable = notesPageAvailability.key === location.key && notesPageAvailability.available;
  const courseSidebarAvailable = courseSidebarAvailability.key === location.key && courseSidebarAvailability.available;
  const savedCoursesAvailable = !hasCourseCatalog && hasFeature('course.video') && (xiaoyuVisible || location.pathname === '/courses' || /^\/course\/\d+/.test(location.pathname));
  const projectChatAvailable = xiaoyuVisible && projectChatAvailability.key === location.key && projectChatAvailability.available;
  const learningPathAvailable = xiaoyuVisible && learningPathAvailability;
  const inProjectChat = xiaoyuVisible && projectChat.projectId !== null;
  const workbenchAvailable = inProjectChat && personalWorkbenchProjectId(projectChat.projectId) !== null;
  const workbenchView = sidebarView === 'project-sources' || sidebarView === 'studio' ? sidebarView : null;
  const sidebarAvailable = workbenchAvailable || learningPathAvailable || projectChatAvailable || notesAvailable || courseSidebarAvailable || savedCoursesAvailable;
  const sidebarVisible = notesOpen && sidebarAvailable && (!workbenchView || workbenchAvailable);
  const activeSidebarView = workbenchView ? (workbenchAvailable ? workbenchView : 'home') : sidebarView === 'learning-path' ? (learningPathAvailable ? sidebarView : 'home') : (projectChatAvailable && sidebarView === 'chat') || courseSidebarAvailable || sidebarView === 'notes' || (savedCoursesAvailable && sidebarView === 'saved-courses') ? sidebarView : 'home';
  useEffect(() => {
    if (workbenchView && !workbenchAvailable) {
      closeNotes();
      setSidebarView('home');
    }
  }, [closeNotes, workbenchAvailable, workbenchView]);
  useEffect(() => {
    if (isMobile && sidebarVisible && workbenchView) document.getElementById(`sidebar-tab-${workbenchView}`)?.focus({ preventScroll: true });
  }, [isMobile, sidebarVisible, workbenchView]);
  const notesVisible = sidebarVisible && activeSidebarView === 'notes';
  const sidebarTools: { id: SidebarView; label: string; icon: typeof NotePencil }[] = [...(courseSidebarAvailable ? [
    { id: 'chat' as const, label: t('小宇'), icon: ChatCircle },
    { id: 'outline' as const, label: t('课程大纲'), icon: ListBullets },
    { id: 'materials' as const, label: t('资料'), icon: Files },
    { id: 'notes' as const, label: t('笔记'), icon: NotePencil },
  ] : [...(projectChatAvailable ? [{ id: 'chat' as const, label: t('小宇'), icon: ChatCircle }] : []), { id: 'notes' as const, label: t('笔记'), icon: NotePencil }]), ...(savedCoursesAvailable ? [{ id: 'saved-courses' as const, label: t('已保存课程'), icon: BookOpen }] : [])];
  const rawSplitWidth = activeSidebarView === 'learning-path' ? learningPathWidth : sidebarWidth;
  const lastSplitWidth = panesWidth > 0 ? clampSidebarWidth(rawSplitWidth, panesWidth) : rawSplitWidth;
  const rightSidebarWidth = isMobile ? rawSplitWidth
    : sidebarPreview ? Math.min(sidebarPreview.width, panesWidth) : sidebarFullscreen ? panesWidth : lastSplitWidth;
  const workspaceFullscreen = !isMobile && sidebarVisible && panesWidth > 0 && (sidebarPreview ? rightSidebarWidth === panesWidth : sidebarFullscreen);
  const commitSidebarLayout = (width: number, fullscreen: boolean) => {
    const splitWidth = clampSidebarWidth(width, panesWidth);
    if (activeSidebarView === 'learning-path') setLearningPathWidth(splitWidth);
    else saveSidebarWidth(splitWidth);
    setSidebarFullscreen(fullscreen);
  };
  if (learningPathAvailable) sidebarTools.push({ id: 'learning-path', label: t('学习路径'), icon: TreeStructure });
  if (workbenchAvailable) sidebarTools.push({ id: 'project-sources', label: t('资料源'), icon: Files }, { id: 'studio', label: 'Studio', icon: Sparkle });
  const visibleTabIds = [...new Set<SidebarView>([
    ...(workbenchAvailable ? ['project-sources'] as const : []),
    ...(workbenchAvailable && workbenchView === 'studio' ? ['studio'] as const : []),
    ...(learningPathAvailable ? ['notes', 'learning-path'] as const : []),
    ...openedSidebarTools,
  ])];
  const sidebarTabs = visibleTabIds.map(id => sidebarTools.find(tool => tool.id === id)).filter(tool => !!tool);
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

  const personalSpace = activeWorkspace() === 'personal';
  const visibleNavItems = personalSpace ? navItems.filter(item => item.to !== '/courses') : navItems;
  const canEnter = (item: NavItem) => {
    return !item.feature || (!featuresLoading && hasFeature(item.feature));
  };
  const isActive = (item: NavItem) => {
    const path = location.pathname;
    if (item.to === '/courses') return path === '/courses' || path.startsWith('/course/');
    return path === item.to || path.startsWith(`${item.to}/`);
  };

  const accountInRail = !isMobile && !railHidden;
  const managesInstitution = !!workspace?.enterprise || workspace?.workspaces?.some(item => item.role === 'admin');
  const isLearner = !!workspace?.workspaces?.some(item => item.role === 'student') || !!(user?.is_member && !user.is_admin);
  const accountType = managesInstitution ? t('机构主用户') : isLearner ? t('学员用户') : t('个人用户');
  const accountSection = activeWorkspace() !== 'personal' && workspace?.role === 'admin' && workspace.workspace?.service_active
    ? '/settings/institution'
    : managesInstitution || isLearner ? '/settings?section=institution' : '/settings?section=account';
  const accountName = user?.nickname || user?.username || '';
  const accountMenu = user && (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild><button id="avatar-btn" aria-label={t('账户菜单')} className="um-app-avatar-button"><Avatar className="h-7 w-7"><AvatarImage src={user.avatar_url} /><AvatarFallback className="text-[10px] font-bold">{user.username?.[0]}</AvatarFallback></Avatar></button></DropdownMenuTrigger>
      <DropdownMenuContent align="end" side={accountInRail ? 'right' : 'bottom'} sideOffset={accountInRail ? 8 : 4} className="um-app-menu um-account-menu">
        <DropdownMenuItem className="um-account-menu-profile" asChild>
          <Link to={accountSection}>
            <Avatar className="h-8 w-8 shrink-0"><AvatarImage src={user.avatar_url} /><AvatarFallback>{accountName[0]}</AvatarFallback></Avatar>
            <span className="um-account-menu-identity"><strong>{accountName}</strong><small>{accountType}</small></span>
            <CaretRight size={13} aria-hidden="true" />
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        {[
          { to: '/settings?section=account', icon: UserIcon, label: t('个人设置') },
          { to: '/billing', icon: CreditCard, label: t('我的服务') },
        ].map(item => <DropdownMenuItem key={item.to} asChild><Link to={item.to}><item.icon size={15} />{item.label}</Link></DropdownMenuItem>)}
        <DropdownMenuItem onSelect={() => setInviteOpen(true)}><UserPlus size={15} />{t('邀请好友')}</DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => setShowLogoutAlert(true)} className="text-[var(--um-color-danger)] focus:bg-[var(--um-color-danger)] focus:text-[var(--um-color-on-danger)]"><SignOut size={15} />{t('退出登录')}</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );

  const isMobileTopLevel = isMobile && (
    location.pathname === '/xiaoyu'
    || location.pathname === '/notes'
    || location.pathname === '/courses'
    || location.pathname === '/tests'
  );
  const sessionSearchParams = location.pathname.startsWith('/tests/session') ? new URLSearchParams(location.search) : null;
  const mobileBackTarget = location.pathname.startsWith('/notes/')
    ? '/notes'
    : location.pathname.startsWith('/course/')
      ? '/courses'
      : location.pathname.startsWith('/tests/session')
        ? (sessionSearchParams?.get('source') === 'xiaoyu' ? '/xiaoyu' : sessionSearchParams?.has('ids') ? '/tests/review' : '/tests')
        : location.pathname.startsWith('/tests/')
          ? '/tests'
          : '/xiaoyu';
  const mobileDrawerOrder = ['/xiaoyu', '/notes', '/courses', '/tests'];
  const mobileNavItems = isMobile
    ? mobileDrawerOrder
      .map(path => navItems.find(item => item.to === path))
      .filter((item): item is NavItem => !!item && canEnter(item) && !(personalSpace && item.to === '/courses'))
    : [];
  const mobileNavLinks = (
    <nav className="um-m-drawer-nav" aria-label={t('功能导航')}>
      {mobileNavItems.map(item => {
        const active = isActive(item);
        const Icon = item.to === '/xiaoyu' ? Sparkle : item.to === '/notes' ? NotePencil : item.to === '/courses' ? BookOpen : Exam;
        return (
          <Link key={item.to} to={routeFor(item.to)} aria-current={active ? 'page' : undefined}>
            <Icon size={17} weight={active ? 'duotone' : 'regular'} />
            <span>{item.mobileLabel}</span>
          </Link>
        );
      })}
    </nav>
  );
  const mobileDrawerAccount = (
    <>
      {user && (
        <Link to={accountSection} className="um-m-drawer-user">
          <Avatar className="h-7 w-7 shrink-0">
            <AvatarImage src={user.avatar_url} />
            <AvatarFallback className="text-[11px] font-semibold bg-[var(--m-accent-soft)] text-[var(--m-accent)]">
              {(user.nickname || user.username)?.[0]}
            </AvatarFallback>
          </Avatar>
          <span className="um-account-menu-identity"><strong>{accountName}</strong><small>{accountType}</small></span>
        </Link>
      )}
      <div className="um-m-drawer-footer-actions">
        {user && <button type="button" id="mobile-invite-friend" aria-label={t('邀请好友')} title={t('邀请好友')} onClick={() => setInviteOpen(true)}><UserPlus size={17} /></button>}
        {user && <div className="um-app-header-actions"><NotificationBell /></div>}
        <Link to="/settings" aria-label={t('设置')} title={t('设置')}><Gear size={17} /></Link>
      </div>
    </>
  );
  const mobileNavigation: MobileNavigationSlot | undefined = mobileXiaoyu ? {
    onOpen: () => { if (sidebarVisible) closeNotes(); },
    links: mobileNavLinks,
    account: mobileDrawerAccount,
  } : undefined;

  const nativeOffline = useSyncExternalStore(subscribeOffline, isNativeOffline);
  const demoActive = useAuthStore(state => state.demoActive);
  return <TooltipProvider delayDuration={0}>
    <div ref={shellRef} data-mobile-xiaoyu={mobileXiaoyu || undefined} data-mobile-notes={(isMobile && inNotesPage) || undefined} data-mobile-canvas={isMobilePracticeCanvas || undefined} data-mobile-immersive={isMobileImmersivePage || undefined} className="um-app-shell flex flex-col h-dvh bg-background text-foreground overflow-hidden font-sans selection:bg-primary selection:text-primary-foreground" data-nav-history={historyIndex > 0 || historyIndex < historyEnd ? 'true' : undefined}>
      <header className="um-window-toolbar" aria-label={t('工作区功能区')}>
        {!isMobile && <SpaceSwitcher />}
        {isMobile && !mobileXiaoyu && isMobileTopLevel && (
          <GlobalMobileDrawer
            open={mobileMenuOpen}
            onOpenChange={open => { if (open && sidebarVisible) closeNotes(); setMobileMenuOpen(open); }}
            links={mobileNavLinks}
            account={mobileDrawerAccount}
          />
        )}
        {isMobile && !isMobileTopLevel && (
          <Link className="um-mobile-back-button" to={mobileBackTarget} aria-label={t('返回')}>
            <ArrowLeft size={20} />
          </Link>
        )}
        <div className="um-window-navigation"><button aria-label={t('返回')} title={t('返回')} disabled={historyIndex <= 0} onClick={() => navigate(-1)}><ArrowLeft size={17} /></button><button aria-label={t('前进')} title={t('前进')} disabled={historyIndex >= historyEnd} onClick={() => navigate(1)}><ArrowRight size={17} /></button></div>
        <div className="um-window-workspace" ref={setToolbarHost}>{!hasWorkspaceToolbar && <>{!isMobile && <button className="um-agent-icon-button hidden md:inline-flex" aria-label={t('切换导航栏')} onClick={() => setRailHidden(old => !old)}><SidebarSimple size={18} /></button>}<WorkspaceTrail title={pageTitle || t('学习空间')} crumbs={[]} /></>}</div>
        {!isMobile && user && <div data-tour="header-right" className="um-app-header-actions"><NotificationBell />{!accountInRail && accountMenu}</div>}
        {sidebarAvailable && (!mobileXiaoyu || projectChat.hasConversation || projectChat.projectId || sidebarVisible) && <button id="um-notes-toggle" data-native-back-close={sidebarVisible ? true : undefined} type="button" className="um-right-sidebar-toggle um-agent-icon-button" aria-label={t('切换右侧栏')} title={sidebarVisible ? t('收起右侧栏') : t('展开右侧栏')} aria-expanded={sidebarVisible} aria-controls="um-right-panel" onClick={() => { if (sidebarVisible) closeNotes(); else if (inProjectChat) selectSidebarView('home'); else setNotesOpen(true); }}><SidebarSimple size={19} style={{ transform: 'scaleX(-1)' }} /></button>}
      </header>
      {(nativeOffline || demoActive) && <div role="status" className="flex shrink-0 items-center justify-between gap-2 bg-amber-50 text-amber-950 px-3 py-1 text-xs"><span>{demoActive ? t('离线试用 · 数据仅保存在本机') : t('离线缓存 · 已使用本地离线缓存')}</span><button type="button" className="min-h-11 underline shrink-0" onClick={() => { if (demoActive) { void useAuthStore.getState().exitDemo().then(() => { queryClient.clear(); navigate('/login', { replace: true }); }); } else { setNativeOffline(false); navigate('/settings'); void queryClient.invalidateQueries(); } }}>{demoActive ? t('连接服务器 / 退出试用') : t('重新连接 / 服务器设置')}</button></div>}
      <div className="um-window-body flex flex-1 min-h-0 overflow-hidden">
      <aside data-tour="sidebar" aria-label={t('应用导航')} className={cn('um-app-rail relative flex-col p-1.5 z-0 shrink-0 hidden md:flex w-[58px]', railHidden && 'md:hidden')}>
        <div className="um-app-brand flex justify-center"><Link to="/xiaoyu" className="um-app-brand-link flex h-9 w-9 shrink-0 items-center justify-center rounded-lg" aria-label={t('小宇')} title={t('小宇')} aria-current={location.pathname.startsWith('/xiaoyu') ? 'page' : undefined}>
          <svg viewBox="-2 4 100 100" className="h-8 w-8" aria-hidden="true" focusable="false">
            <defs><linearGradient id="um-sidebar-brand-gradient" gradientUnits="userSpaceOnUse" x1="15" y1="90" x2="90" y2="10"><stop stopColor="var(--um-sidebar-brand-start, #2f6cea)" /><stop offset=".5" stopColor="var(--um-sidebar-brand-middle, #535fe7)" /><stop offset="1" stopColor="var(--um-sidebar-brand-end, #9252d8)" /></linearGradient></defs>
            <g fill="url(#um-sidebar-brand-gradient)">
              <path d="M18 36C18 13 48 13 48 36C48 13 78 13 78 36V61C78 79 67 89 48 89S18 79 18 61Z" fill="none" stroke="url(#um-sidebar-brand-gradient)" strokeWidth="12" strokeLinejoin="round" />
              <rect x="33" y="48" width="8" height="13" rx="4" />
              <rect x="56" y="48" width="8" height="13" rx="4" />
              <circle cx="90" cy="14" r="5" />
            </g>
          </svg>
        </Link></div>
        <nav aria-label={t('功能导航')} className="flex-1 min-h-0 overflow-y-auto space-y-1.5">
          {visibleNavItems.filter(item => item.to !== '/xiaoyu').map(item => <div key={item.to} className="px-1"><Tooltip><TooltipTrigger asChild><Button variant="ghost" asChild className={cn('w-full h-9 rounded-lg justify-center p-0', !canEnter(item) ? 'opacity-40 cursor-not-allowed text-muted-foreground' : isActive(item) ? 'bg-primary/10 text-primary' : 'cursor-pointer text-muted-foreground hover:bg-muted hover:text-foreground')}>{canEnter(item) ? <Link to={routeFor(item.to)} aria-label={item.label} aria-current={isActive(item) ? 'page' : undefined}>{<NavIcon icon={item.icon} />}<span className="sr-only">{item.label}</span></Link> : <span role="link" tabIndex={0} aria-label={item.label} aria-disabled="true">{<NavIcon icon={item.icon} />}<span className="sr-only">{item.label}</span></span>}</Button></TooltipTrigger><TooltipPortal><TooltipContent side="right" sideOffset={10} className="font-medium text-[13px] rounded-lg border-border shadow-sm">{item.label}{!canEnter(item) && t(' · 暂未开通')}</TooltipContent></TooltipPortal></Tooltip></div>)}
        </nav>
        {accountInRail && accountMenu}
      </aside>
      <div ref={panesRef} className="um-window-panes" data-notes-open={sidebarVisible} data-fullscreen={workspaceFullscreen} data-resizing={!!sidebarPreview} data-snap={sidebarPreview?.snap ?? undefined} style={{ '--um-notes-width': `${rightSidebarWidth}px` } as React.CSSProperties}>
      <main inert={(isMobile && sidebarVisible) || workspaceFullscreen} aria-hidden={workspaceFullscreen || undefined} className={cn('um-app-main flex-1 min-w-0 min-h-0 relative z-[var(--z-base)] flex flex-col bg-background',
        isMobileImmersivePage || isIntegratedWorkspace ? 'overflow-hidden' : 'overflow-y-auto')}>
        <ExamActivityBar />
        <div className={cn('um-app-page-content flex-1 w-full relative min-h-0', isMobileImmersivePage ? 'px-0 py-0 h-full overflow-hidden' : isMobileVideoPage ? 'px-0 py-0' : !isIntegratedWorkspace && 'px-4 py-4 md:px-8 md:py-6')}>
          <RightSidebarLayoutContext.Provider value={{ fullscreen: workspaceFullscreen, exitFullscreen: () => { setSidebarPreview(null); setSidebarFullscreen(false); } }}>
            <WorkspaceToolbarHostContext.Provider value={{ host: toolbarHost, enabled: hasWorkspaceToolbar }}>
              <WorkspaceActiveContext.Provider value={xiaoyuVisible}>
                <NotesSidebarContext.Provider value={{ open: notesVisible, close: closeNotes, setAvailable: setNotesAvailable }}>
                  <CourseSidebarContext.Provider value={{ host: courseSidebarHost, view: activeSidebarView, visible: sidebarVisible, recordRecent: recordSidebarRecent, setAvailable: setCourseSidebarAvailable }}>
                    <ProjectChatSidebarContext.Provider value={{ host: projectChatHost, visible: sidebarVisible && activeSidebarView === 'chat', open: openProjectChat, close: closeNotes, setAvailable: setProjectChatAvailable }}>
                      <LearningPathSidebarContext.Provider value={{ host: learningPathHost, visible: sidebarVisible && activeSidebarView === 'learning-path', open: openLearningPath, openNotes: openSidebarNotes, close: closeNotes, setAvailable: setLearningPathAvailability }}>
                        <WorkbenchSidebarContext.Provider value={{ host: workbenchSidebarHost, view: sidebarVisible ? workbenchView : null, open: selectSidebarView, close: closeNotes }}>
                          <Outlet context={{ toolbarHost, mobileNavigation }} />
                        </WorkbenchSidebarContext.Provider>
                      </LearningPathSidebarContext.Provider>
                    </ProjectChatSidebarContext.Provider>
                  </CourseSidebarContext.Provider>
                </NotesSidebarContext.Provider>
              </WorkspaceActiveContext.Provider>
            </WorkspaceToolbarHostContext.Provider>
          </RightSidebarLayoutContext.Provider>
        </div>
      </main>
      {sidebarVisible && <button className="um-notes-mobile-backdrop" aria-label={t('收起右侧栏')} onClick={closeNotes} />}
      {sidebarVisible && !isMobile && <SidebarResizeHandle width={rightSidebarWidth} splitWidth={lastSplitWidth} containerWidth={panesWidth} fullscreen={sidebarFullscreen} preview={sidebarPreview} onPreview={setSidebarPreview} onCommit={commitSidebarLayout} onCollapse={closeNotes} />}
      <div id="um-right-panel" className="um-notes-sidebar-host um-unified-sidebar" data-open={sidebarVisible} data-fullscreen={workspaceFullscreen} aria-hidden={!sidebarVisible} inert={!sidebarVisible} onKeyDownCapture={event => {
        if (event.key === 'Escape' && workspaceFullscreen) { event.preventDefault(); event.stopPropagation(); setSidebarFullscreen(false); }
      }} onKeyDown={event => { if (event.key === 'Escape' && !event.defaultPrevented) { event.preventDefault(); closeNotes(); } }}>
        <header className="um-right-panel-header">
          <button type="button" className="um-agent-icon-button" aria-label={t('工具入口')} aria-pressed={activeSidebarView === 'home'} onClick={() => selectSidebarView('home')}><SquaresFour size={18} /></button>
          <div role="tablist" aria-label={t('侧栏功能')}>{sidebarTabs.map((tab, index) => <div className="um-sidebar-tab" key={tab.id}><button id={`sidebar-tab-${tab.id}`} role="tab" type="button" aria-selected={activeSidebarView === tab.id} aria-controls={`sidebar-panel-${tab.id}`} tabIndex={activeSidebarView === tab.id || (activeSidebarView === 'home' && index === 0) ? 0 : -1} onClick={() => selectSidebarView(tab.id)} onKeyDown={event => {
            if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
            event.preventDefault();
            const next = event.key === 'Home' ? 0 : event.key === 'End' ? sidebarTabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + sidebarTabs.length) % sidebarTabs.length;
            selectSidebarView(sidebarTabs[next].id);
            document.getElementById(`sidebar-tab-${sidebarTabs[next].id}`)?.focus();
          }}>{tab.id !== 'project-sources' && tab.id !== 'studio' && <tab.icon size={16} />}<span>{tab.label}</span></button>{tab.id !== 'project-sources' && tab.id !== 'studio' && !(learningPathAvailable && (tab.id === 'learning-path' || tab.id === 'notes')) && <button type="button" className="um-sidebar-tab-close" aria-label={t('关闭{0}标签', { 0: tab.label })} onClick={() => {
            setOpenedSidebarTools(previous => previous.filter(id => id !== tab.id));
            if (activeSidebarView === tab.id) setSidebarView('home');
          }}><X size={12} /></button>}</div>)}</div>
          {!isMobile && <button type="button" className="um-agent-icon-button" aria-label={sidebarFullscreen ? t('恢复分屏') : t('全屏展开')} title={sidebarFullscreen ? t('恢复分屏') : t('全屏展开')} aria-pressed={sidebarFullscreen} onClick={() => setSidebarFullscreen(value => !value)}>{sidebarFullscreen ? <ArrowsInSimple size={17} /> : <ArrowsOutSimple size={17} />}</button>}
          <button type="button" className="um-agent-icon-button" aria-label={t('关闭右侧栏')} data-native-back-close={sidebarVisible ? true : undefined} onClick={closeNotes}><X size={17} /></button>
        </header>
        {activeSidebarView === 'home' && <SidebarHome tools={sidebarTools} added={addedSidebarTools} recent={sidebarRecent} onSelect={selectSidebarView} onOpenRecent={openSidebarRecent} />}
        <div ref={setWorkbenchSidebarHost} className="um-right-panel-content um-native-agent" hidden={!workbenchAvailable || !workbenchView} />
        <div ref={setLearningPathHost} id="sidebar-panel-learning-path" role="tabpanel" aria-labelledby="sidebar-tab-learning-path" className="um-right-panel-content um-native-agent" hidden={activeSidebarView !== 'learning-path'} />
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
      <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
        <DialogContent className="um-friend-invitation" onCloseAutoFocus={event => {
          event.preventDefault();
          (document.getElementById('avatar-btn') ?? document.getElementById('mobile-invite-friend'))?.focus();
        }}>
          <div className="um-friend-invitation-art">
            <span aria-hidden="true" /><span aria-hidden="true" />
            <img src="/unimind_logo_small.png" alt="UniMind.ai" width={80} height={80} />
          </div>
          <div className="um-friend-invitation-body">
            <DialogHeader>
              <DialogTitle>{t('邀请好友加入 UniMind.ai')}</DialogTitle>
              <DialogDescription>{t('好友通过你的链接完成注册，你们各获 3 天免费会员。')}</DialogDescription>
            </DialogHeader>
            {invite.data ? <div className="um-friend-invitation-link">
              <a href={invite.data} target="_blank" rel="noreferrer" title={invite.data}>{invite.data}</a>
              <Button size="sm" onClick={async () => {
                try {
                  await navigator.clipboard.writeText(invite.data);
                  toast.success(t('邀请链接已复制'));
                } catch {
                  toast.error(t('复制失败，请手动复制邀请链接'));
                }
              }}><Copy size={15} />{t('复制链接')}</Button>
            </div> : invite.isError ? <div className="um-friend-invitation-link" role="alert">
              <span>{t('暂时无法获取邀请链接。')}</span><Button size="sm" variant="outline" onClick={() => void invite.refetch()}>{t('重试')}</Button>
            </div> : <p className="text-sm text-muted-foreground" role="status">{t('正在获取邀请链接…')}</p>}
          </div>
        </DialogContent>
      </Dialog>
      <AlertDialog open={showLogoutAlert} onOpenChange={setShowLogoutAlert}><AlertDialogContent className="rounded-lg border-border bg-card"><AlertDialogHeader><AlertDialogTitle>{t('确认退出登录？')}</AlertDialogTitle><AlertDialogDescription>{t('退出后需要重新登录才能访问学习记录和课程。')}{pendingLearningRecords > 0 && t(' 当前还有 {0} 条离线学习记录未同步，退出会清除这些记录，建议先返回桌面设置联网同步。', { 0: pendingLearningRecords })}</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>{t('返回')}</AlertDialogCancel><AlertDialogAction onClick={async () => { try { await api.post('/users/logout/'); } catch { /* Local logout remains available. */ } await queryClient.cancelQueries(); queryClient.clear(); logout(); navigate('/login', { replace: true }); }}>{t('确认退出')}</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
      {showTour && isTourPage && <GuidedTour steps={tourSteps} onDismiss={handleTourDismiss} />}
    </div>
  </TooltipProvider>;
};
