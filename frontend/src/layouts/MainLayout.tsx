import React, { useState, useEffect, useRef } from 'react';
import { Link, useLocation, Outlet, useNavigate } from 'react-router-dom';
import { BookOpen, FileText, Trophy, Clock, User as UserIcon, SignOut, ShieldCheck, CreditCard, CaretLeft, CaretRight, Sparkle, Gear, Brain, ChartBar, Gauge, Buildings, ChatCircleText, Wrench, Eye, EyeSlash, UserPlus, Users, Robot, TreeStructure, Storefront, Code } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';
import api from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { useAuthStore } from '@/store/useAuthStore';
import { useSystemStore } from '@/store/useSystemStore';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import { NotificationBell } from '@/components/NotificationBell';
import { UpgradeModal } from '@/components/UpgradeModal';
import { TrialBanner } from '@/components/TrialBanner';
import { EloPopover } from '@/components/EloPopover';
import { AchievementPill } from '@/components/AchievementPill';
import { InvitePopover } from '@/pages/workbench/InvitePopover';

import { useIsMobile } from '@/lib/useIsMobile';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { toast } from 'sonner';
import UnimindLogo from '../../Unimind_logo.png';
import { PersistentUploadToast } from '@/components/PersistentUploadToast';
import GuidedTour, { type TourStep } from '@/components/GuidedTour';

interface SidebarItemProps {
  to: string;
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  active: boolean;
  collapsed: boolean;
}

const SidebarItem = ({ to, icon: Icon, label, active, collapsed }: SidebarItemProps) => {
  const content = (
    <div className="px-1">
      <Button
        variant="ghost"
        asChild
        className={cn(
          "w-full justify-start gap-3 h-10 px-3 overflow-hidden rounded-lg cursor-pointer",
          active
            ? "bg-card text-foreground shadow-sm border border-border"
            : "text-muted-foreground hover:bg-muted hover:text-foreground",
        )}
      >
        <Link to={to} className="flex items-center gap-3 w-full h-full">
          <Icon className={cn("h-4 w-4 shrink-0", active ? "text-foreground" : "text-muted-foreground")} />
          <span className={cn(
            "font-bold text-[13px] tracking-tight whitespace-nowrap transition-all duration-200 overflow-hidden",
            collapsed ? "opacity-0 max-w-0" : "opacity-100 max-w-[176px]"
          )}>{label}</span>
        </Link>
      </Button>
    </div>
  );

  return collapsed ? (
    <TooltipProvider delayDuration={0}>
      <Tooltip>
        <TooltipTrigger asChild>{content}</TooltipTrigger>
        <TooltipContent side="right" className="font-bold border-none shadow">{label}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  ) : content;
};

// ── Module-level pure helpers ──

const isMobileAllowedPath = (pathname: string) =>
  pathname === '/' ||
  pathname === '/articles' ||
  pathname.startsWith('/article/') ||
  pathname === '/qa' ||
  pathname.startsWith('/qa/') ||
  pathname === '/study' ||
  pathname === '/knowledge-map' ||
  pathname.startsWith('/knowledge-map/') ||
  pathname === '/tests' ||
  pathname.startsWith('/tests/') ||
  pathname === '/settings' ||
  pathname === '/courses' ||
  pathname.startsWith('/course/') ||
  pathname === '/xiaoyu' ||
  pathname.startsWith('/xiaoyu/practice') ||
  pathname === '/achievements' ||
  pathname === '/report-card' ||
  pathname === '/workbench' ||
  pathname === '/parent' ||
  pathname.startsWith('/institution');

const planLevel = (p: string) => ({ free: 1, starter: 2, growth: 3, enterprise: 4 })[p] || 1;

const teacherTourSteps: TourStep[] = [
  {
    target: '[data-tour="workbench-input"]',
    title: '一切从对话开始',
    content: '出题、查数据、管学生，都从这里输入。对话试试！',
    placement: 'bottom',
  },
  {
    target: '[data-tour="sidebar"]',
    title: '功能导航',
    content: '所有的功能都在这里，试着探索一下吧',
    placement: 'right',
  },
  {
    target: '[data-tour="header-right"]',
    title: '账号和消息',
    content: '修改资料、系统通知，都在这里',
    placement: 'bottom',
  },
];

const studentTourSteps: TourStep[] = [
  {
    target: '[data-tour="xiaoyu-input"]',
    title: '跟小宇对话',
    content: '问知识点、刷题、看分析。试试「帮我复习一下三角函数」',
    placement: 'bottom',
  },
  {
    target: '[data-tour="sidebar"]',
    title: '你的学习空间',
    content: '知识图谱看掌握度、错题本自动收集做错的题、模拟考试',
    placement: 'right',
  },
  {
    target: '[data-tour="header-right"]',
    title: '账号和消息',
    content: '修改资料、系统通知、签到',
    placement: 'bottom',
  },
];

const panelTourSteps: TourStep[] = [
  {
    target: '[data-tour="workbench-panel"]',
    title: '工作台面板',
    content: '主要工作区，几乎所有内容都会在这里呈现',
    placement: 'right',
    width: 240,
  },
];

export const MainLayout: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const user = useAuthStore(s => s.user);
  const logout = useAuthStore(s => s.logout);
  const updateUser = useAuthStore(s => s.updateUser);
  const { primaryColor, pageTitle } = useSystemStore();
  const [collapsed, setCollapsed] = useState(false);
  const [studentPreview, setStudentPreview] = useState(false);
  const [showLogoutAlert, setShowLogoutAlert] = useState(false);
  const isMobile = useIsMobile();
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);
  const [invitePopoverOpen, setInvitePopoverOpen] = useState(false);
  const [showTour, setShowTour] = useState(false);
  const [showPanelTour, setShowPanelTour] = useState(false);
  const avatarRef = useRef<HTMLButtonElement>(null);

  const { institution: instFromStore, fetchFeatures, hasFeature, loading: featuresLoading, previewMode, previewInstitution, exitPreview } = useInstitutionStore();
  const instInfo = instFromStore || user?.institution || null;

  const isFullPage = ['/platform'].includes(location.pathname);
  const isEdgeToEdge = ['/workbench', '/xiaoyu'].includes(location.pathname);
  const isMobileStudyPage = isMobile && location.pathname === '/study';
  const isMobileImmersivePage = isMobile && (
    location.pathname.startsWith('/tests/session') ||
    location.pathname.startsWith('/xiaoyu/practice')
  );
  const isMobileVideoPage = isMobile && location.pathname.startsWith('/course/');
  const hideMobileBottomNav = isMobile && (
    location.pathname.startsWith('/tests/session') ||
    location.pathname.startsWith('/xiaoyu/practice') ||
    location.pathname.startsWith('/course/') ||
    location.pathname === '/study'
  );

  useEffect(() => {
    document.documentElement.style.setProperty('--primary-override', primaryColor);
  }, [primaryColor]);

  useEffect(() => {
    document.title = instInfo?.name
      ? `${instInfo.name} - UniMind.ai - 新一代AI教育基础设施`
      : 'UniMind.ai - 新一代AI教育基础设施';
  }, [instInfo?.name]);

  useEffect(() => {
    if (!studentPreview) fetchFeatures();
  }, [studentPreview]);

  useEffect(() => {
    if (!isMobile) return;
    if (!isMobileAllowedPath(location.pathname)) {
      navigate('/qa', { replace: true });
    }
  }, [isMobile, location.pathname, navigate]);


  // ── 身份与方案层级 ──
  const isPlatformAdmin = user?.is_admin === true;
  const isInstStudent = Boolean(instInfo) && user?.institution_role === 'student';
  const effectiveIsInstStudent = studentPreview || isInstStudent;
  const homePath = effectiveIsInstStudent ? '/xiaoyu' : '/workbench';
  const effectivePlan = instInfo?.plan || user?.personal_plan || user?.membership_tier || 'free';
  const myPlanLevel = planLevel(effectivePlan);

  // ── Guided Tour ──
  const isTourPage = location.pathname === '/workbench' || location.pathname === '/xiaoyu';
  const tourSteps = effectiveIsInstStudent ? studentTourSteps : teacherTourSteps;

  const handleTourDismiss = async () => {
    setShowTour(false);
    try {
      await api.patch('/users/me/tour-dismiss/');
      updateUser({ tour_dismissed_at: new Date().toISOString() });
    } catch {
      // silently ignore — will retry next time
    }
  };

  // Poll for first target element, then show tour
  useEffect(() => {
    if (!isTourPage || isMobile) return;
    if (user?.tour_dismissed_at) return;

    const firstTarget = tourSteps[0]?.target;
    if (!firstTarget) return;

    let attempts = 0;
    const maxAttempts = 20;

    const poll = setInterval(() => {
      const el = document.querySelector(firstTarget);
      if (el) {
        clearInterval(poll);
        setShowTour(true);
        return;
      }
      attempts++;
      if (attempts >= maxAttempts) clearInterval(poll);
    }, 300);

    return () => clearInterval(poll);
  }, [isTourPage, tourSteps, isMobile, user?.tour_dismissed_at]);

  // Dismiss tour when navigating away from tour page
  useEffect(() => {
    if (showTour && !isTourPage) {
      setShowTour(false);
      handleTourDismiss();
    }
  }, [location.pathname, showTour, isTourPage]);

  // ── Panel Tour（工作台首次对话后双栏布局）──
  const handlePanelTourDismiss = async () => {
    setShowPanelTour(false);
    try {
      await api.patch('/users/me/tour-panel-dismiss/');
      updateUser({ tour_panel_dismissed_at: new Date().toISOString() });
    } catch {
      // silently ignore
    }
  };

  // Poll for workbench panel element after layout tour is done
  useEffect(() => {
    if (location.pathname !== '/workbench' || isMobile) return;
    if (user?.tour_panel_dismissed_at) return;
    if (!user?.tour_dismissed_at) return; // wait for layout tour

    const target = '[data-tour="workbench-panel"]';
    let attempts = 0;

    const poll = setInterval(() => {
      const el = document.querySelector(target);
      if (el) {
        clearInterval(poll);
        setShowPanelTour(true);
        return;
      }
      attempts++;
      if (attempts >= 120) clearInterval(poll); // 60s timeout
    }, 500);

    return () => clearInterval(poll);
  }, [location.pathname, isMobile, user?.tour_panel_dismissed_at, user?.tour_dismissed_at]);

  type NavItem = { to: string; icon: React.ComponentType<{ className?: string }>; label: string };

  // ── 路由 → 功能标志映射（与 App.tsx FeatureGuard 一致）──
  const NAV_FEATURE_MAP: Record<string, string> = {
    '/tests': 'quiz.exam',
    '/knowledge-map': 'knowledge.graph',
    '/qa': 'faq.system',
    '/study': 'study.room',
  };

  // 功能可见性：有 feature 要求的项，必须 hasFeature 通过才显示
  const itemVisible = (item: NavItem) => {
    const feat = NAV_FEATURE_MAP[item.to];
    if (!feat) return true;
    if (featuresLoading) return false;
    return hasFeature(feat);
  };

  // ── 超级管理员 ──（不再替换侧边栏，作为附加入口注入到角色侧边栏中）
  const platformAdminItem: NavItem = { to: '/platform', icon: Gauge, label: '平台管理' };

  // ── 教师端 ──
  const teacherNavItems: NavItem[] = [
    { to: '/workbench', icon: Robot, label: '工作台' },
    { to: '/questions', icon: Brain, label: '题库' },
    { to: '/courses', icon: BookOpen, label: '课程' },
    { to: '/articles', icon: FileText, label: '文章' },
    { to: '/knowledge-tree', icon: TreeStructure, label: '知识树' },
    { to: '/qa', icon: ChatCircleText, label: '答疑' },
    { to: '/marketplace', icon: Storefront, label: '内容市场' },
    ...(isPlatformAdmin ? [platformAdminItem] : []),
    ...(user?.is_institution_admin ? [{ to: '/management', icon: Wrench, label: '维护中心' } as NavItem] : []),
  ];

  // ── 学生端 9 套件 ──
  const studentNavItems: NavItem[] = [
    { to: '/xiaoyu', icon: Robot, label: '小宇' },
    { to: '/achievements', icon: Trophy, label: '成就' },
    { to: '/report-card', icon: FileText, label: '成绩报告' },
    { to: '/courses', icon: BookOpen, label: '课程中心' },
    { to: '/tests', icon: Trophy, label: '习题训练' },
    { to: '/knowledge-map', icon: Brain, label: '知识地图' },
    { to: '/articles', icon: FileText, label: '文章' },
    { to: '/qa', icon: ChatCircleText, label: '答疑' },
    { to: '/study', icon: Clock, label: '自习室' },
    ...(isPlatformAdmin ? [platformAdminItem] : []),
  ];

  const navItems: NavItem[] = effectiveIsInstStudent ? studentNavItems : teacherNavItems;

  const visibleNavItems = navItems.filter(itemVisible);

  const mobileNavItems: NavItem[] = effectiveIsInstStudent ? [
        { to: '/xiaoyu', icon: Robot, label: '小宇' },
        { to: '/achievements', icon: Trophy, label: '成就' },
        { to: '/courses', icon: BookOpen, label: '课程' },
        { to: '/tests', icon: Trophy, label: '做题' },
        { to: '/knowledge-map', icon: Brain, label: '知识' },
        { to: '/articles', icon: FileText, label: '文章' },
        { to: '/qa', icon: ChatCircleText, label: '答疑' },
        ...(isPlatformAdmin ? [{ to: '/platform', icon: Gauge, label: '平台' } as NavItem] : []),
      ]
    : [
        { to: '/workbench', icon: Robot, label: '工作台' },
        { to: '/questions', icon: Brain, label: '题库' },
        { to: '/courses', icon: BookOpen, label: '课程' },
        { to: '/articles', icon: FileText, label: '文章' },
        { to: '/knowledge-tree', icon: TreeStructure, label: '知识树' },
        { to: '/qa', icon: ChatCircleText, label: '答疑' },
        { to: '/marketplace', icon: Storefront, label: '市场' },
        ...(isPlatformAdmin ? [{ to: '/platform', icon: Gauge, label: '平台' } as NavItem] : []),
      ];

  const visibleMobileNavItems = mobileNavItems.filter(itemVisible);

  return (
    <TooltipProvider delayDuration={0}>
      <div className="flex h-dvh bg-background text-foreground overflow-hidden font-sans selection:bg-primary selection:text-primary-foreground">
        <aside data-tour="sidebar" className={cn(
          "relative border-r border-border flex-col p-2 bg-card/70 backdrop-blur-2xl transition-[width] duration-300 ease-in-out z-0 shrink-0 hidden md:flex",
          collapsed ? "w-16" : "w-48"
        )}>
          {/* Logo — simple, clickable */}
          <div className="mb-6 mt-2 flex justify-center">
            <Link to={homePath} className="shrink-0">
              {collapsed ? (
                <div className="h-10 w-10 rounded-xl overflow-hidden">
                  <img src="/unimind_logo_small.png" alt="UniMind.ai" className="w-full h-full object-contain brand-logo-invert" />
                </div>
              ) : (
                <img src={UnimindLogo} alt="Unimind.ai" className="h-10 w-32 object-contain brand-logo-invert" />
              )}
            </Link>
          </div>

          <nav className="flex-1 space-y-0.5">
            {visibleNavItems.map(item => (
              <SidebarItem
                key={item.to}
                {...item}
                active={location.pathname === item.to}
                collapsed={collapsed}
              />
            ))}

          </nav>

          {/* Collapse/expand toggle */}
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="flex items-center justify-center h-10 w-full rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors mt-1"
          >
            {collapsed ? <CaretRight className="h-4 w-4" /> : <CaretLeft className="h-4 w-4" />}
          </button>
        </aside>

        <main className={cn(
          "flex-1 min-h-0 relative z-[var(--z-base)] flex flex-col bg-background",
          (isMobileImmersivePage || isMobileStudyPage)
            ? "overflow-hidden pb-0"
            : "overflow-y-auto pb-[calc(5rem+env(safe-area-inset-bottom))] md:pb-0"
        )}>
          {!isFullPage && !isMobileImmersivePage && user && (
            <header className="sticky top-0 shrink-0 z-[var(--z-sticky)] hidden md:flex items-center justify-end gap-2 px-6 py-2 border-b border-border bg-background/90 backdrop-blur-xl">
              {/* 学生预览指示 */}
              {studentPreview && (
                <div className="flex items-center gap-1.5 text-xs text-primary font-bold mr-auto">
                  <Eye className="h-3 w-3" />
                  <span className="opacity-70">{'学生视角'}</span>
                  <button onClick={() => { setStudentPreview(false); navigate('/workbench'); }} className="ml-1 px-2 py-0.5 rounded-md bg-primary/10 hover:bg-primary/20 transition-colors text-[11px] font-bold">
                    {'退出预览'}
                  </button>
                </div>
              )}
              <div data-tour="header-right" className="flex items-center gap-2">
                <EloPopover />
                <AchievementPill />
                <NotificationBell />
                <DropdownMenu modal={false}>
                <DropdownMenuTrigger asChild>
                  <button ref={avatarRef} id="avatar-btn" className="rounded-full border border-border p-0.5 bg-card hover:scale-105 transition-transform">
                    <Avatar className="h-7 w-7">
                      <AvatarImage src={user?.avatar_url} />
                      <AvatarFallback className="text-[10px] font-bold">{user?.username?.[0]}</AvatarFallback>
                    </Avatar>
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" side="bottom" className="w-52 rounded-2xl p-2 bg-card/95 backdrop-blur-xl border-border shadow-lg">
                  <DropdownMenuLabel className="px-3 py-2 text-[11px] font-bold text-muted-foreground uppercase tracking-wider">
                    {user?.nickname || user?.username}
                    {user.is_member && <ShieldCheck className="h-3 w-3 text-amber-500 inline ml-1" />}
                  </DropdownMenuLabel>
                  <DropdownMenuItem onClick={() => navigate('/settings')} className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                    <UserIcon className="h-3.5 w-3.5" />
                    <span className="font-bold text-xs">{'个人设置'}</span>
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate('/billing')} className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                    <CreditCard className="h-3.5 w-3.5" />
                    <span className="font-bold text-xs">{'方案与账单'}</span>
                  </DropdownMenuItem>
                  {!isPlatformAdmin && instInfo && user?.is_institution_owner && (
                    <DropdownMenuItem onClick={() => navigate('/institution/admin')} className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                      <Gear className="h-3.5 w-3.5" />
                      <span className="font-bold text-xs">{'机构设置'}</span>
                    </DropdownMenuItem>
                  )}
                  {!isPlatformAdmin && instInfo && user?.is_institution_admin && (
                    <DropdownMenuItem id="invite-menu-item" onClick={() => setInvitePopoverOpen(true)} className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                      <UserPlus className="h-3.5 w-3.5" />
                      <span className="font-bold text-xs">{'邀请学员'}</span>
                    </DropdownMenuItem>
                  )}
                  {!isPlatformAdmin && instInfo && !isInstStudent && !studentPreview && (
                    <>
                      <DropdownMenuItem onClick={() => navigate('/institution/students')} className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                        <Users className="h-3.5 w-3.5" />
                        <span className="font-bold text-xs">{'学员管理'}</span>
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => { setStudentPreview(true); navigate('/xiaoyu'); }} className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                        <Eye className="h-3.5 w-3.5" />
                        <span className="font-bold text-xs">{'预览学生端'}</span>
                      </DropdownMenuItem>
                    </>
                  )}
                  {studentPreview && (
                    <DropdownMenuItem onClick={() => { setStudentPreview(false); navigate('/workbench'); }} className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                      <EyeSlash className="h-3.5 w-3.5" />
                      <span className="font-bold text-xs">{'退出学生端预览'}</span>
                    </DropdownMenuItem>
                  )}
                  {user?.role === 'admin' && (
                    <DropdownMenuItem onClick={() => navigate('/system-settings')} className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                      <Gear className="h-3.5 w-3.5" />
                      <span className="font-bold text-xs">{'外观与系统'}</span>
                    </DropdownMenuItem>
                  )}
                  {user?.is_member && (
                    <DropdownMenuItem onClick={() => window.dispatchEvent(new Event('open-weekly-report'))} className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                      <ChartBar className="h-3.5 w-3.5" />
                      <span className="font-bold text-xs">{'周报'}</span>
                    </DropdownMenuItem>
                  )}
                  {!isInstStudent && myPlanLevel < 3 && (
                    <DropdownMenuItem onClick={() => setShowUpgradeModal(true)} className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                      <Sparkle className="h-3.5 w-3.5 text-amber-500" />
                      <span className="font-bold text-xs">{'升级方案'}</span>
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuSeparator className="my-2 bg-border" />
                  <DropdownMenuItem onClick={() => setShowLogoutAlert(true)} className="rounded-xl px-3 py-2 gap-3 cursor-pointer text-destructive focus:bg-destructive focus:text-destructive-foreground transition-colors">
                    <SignOut className="h-3.5 w-3.5" />
                    <span className="font-bold text-xs">{'退出登录'}</span>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
              </div>
            </header>
          )}
          {!isFullPage && !isMobileImmersivePage && (
            <header className="sticky top-0 h-14 shrink-0 border-b border-border bg-background/90 backdrop-blur-xl z-[var(--z-sticky)] px-4 flex items-center justify-between md:hidden">
              <div className="flex items-center gap-2 min-w-0">
                <img src={UnimindLogo} alt="Unimind.ai" className="w-20 h-5 object-contain shrink-0 brand-logo-invert" />
                {pageTitle && <span className="text-xs font-black tracking-tight truncate">{pageTitle}</span>}
              </div>
              {user && (
                <DropdownMenu modal={false}>
                  <DropdownMenuTrigger asChild>
                    <button className="rounded-full border border-border p-0.5 bg-card">
                      <Avatar className="h-7 w-7">
                        <AvatarImage src={user?.avatar_url} />
                        <AvatarFallback className="text-[10px] font-bold">{user?.username?.[0]}</AvatarFallback>
                      </Avatar>
                    </button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-48 rounded-2xl p-2 bg-card/95 backdrop-blur-xl border-border shadow-lg">
                    <DropdownMenuItem onClick={() => navigate('/settings')} className="rounded-xl px-3 py-2 gap-2 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                      <UserIcon className="h-3.5 w-3.5" />
                      <span className="font-bold text-xs">{'个人设置'}</span>
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => navigate('/billing')} className="rounded-xl px-3 py-2 gap-2 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                      <CreditCard className="h-3.5 w-3.5" />
                      <span className="font-bold text-xs">{'方案与账单'}</span>
                    </DropdownMenuItem>
                    {!isPlatformAdmin && instInfo && user?.is_institution_owner && (
                      <DropdownMenuItem onClick={() => navigate('/institution/admin')} className="rounded-xl px-3 py-2 gap-2 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                        <Gear className="h-3.5 w-3.5" />
                        <span className="font-bold text-xs">{'机构设置'}</span>
                      </DropdownMenuItem>
                    )}
                    {/* 机构看板：管理员可见 */}
                    {!isPlatformAdmin && instInfo && !isInstStudent && (
                      <DropdownMenuItem onClick={() => navigate('/institution')} className="rounded-xl px-3 py-2 gap-2 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                        <ChartBar className="h-3.5 w-3.5" />
                        <span className="font-bold text-xs">{'机构看板'}</span>
                      </DropdownMenuItem>
                    )}
                    {!isPlatformAdmin && instInfo && user?.is_institution_admin && (
                      <DropdownMenuItem
                        onClick={() => setInvitePopoverOpen(true)}
                        className="rounded-xl px-3 py-2 gap-2 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors"
                      >
                        <UserPlus className="h-3.5 w-3.5" />
                        <span className="font-bold text-xs">{'复制邀请链接'}</span>
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuSeparator className="my-2 bg-border" />
                    <DropdownMenuItem onClick={() => setShowLogoutAlert(true)} className="rounded-xl px-3 py-2 gap-2 cursor-pointer text-destructive focus:bg-destructive focus:text-destructive-foreground transition-colors">
                      <SignOut className="h-3.5 w-3.5" />
                      <span className="font-bold text-xs">{'退出登录'}</span>
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              )}
            </header>
          )}
          <TrialBanner />
          <div className={cn(
            "flex-1 w-full relative min-h-0",
            (isMobileImmersivePage || isMobileStudyPage)
              ? "px-0 py-0 h-full overflow-hidden"
              : isMobileVideoPage
                ? "px-0 py-4"
                : !isFullPage && !isEdgeToEdge && "px-4 py-4 md:px-8 md:py-6",
            isMobile && !hideMobileBottomNav && "pb-20",
          )}>
            {/* Preview mode banner */}
            {previewMode && previewInstitution && (
              <div className="flex items-center justify-between bg-primary text-white px-4 py-2.5 rounded-xl mb-3">
                <div className="flex items-center gap-2 text-sm font-bold">
                  <Eye className="h-4 w-4" />
                  <span>{`预览模式：${previewInstitution.name}（${previewInstitution.plan_label}）`}</span>
                </div>
                <Button size="sm" variant="ghost" className="text-white hover:bg-white/10 text-xs"
                  onClick={exitPreview}>
                  <EyeSlash className="h-3.5 w-3.5 mr-1" /> {'退出预览'}
                </Button>
              </div>
            )}
            <Outlet />
          </div>
        </main>

        <nav className={cn(
          "md:hidden fixed bottom-0 inset-x-0 z-[var(--z-dropdown)] border-t border-border bg-card/95 backdrop-blur-xl pb-[env(safe-area-inset-bottom)]",
          hideMobileBottomNav && "hidden"
        )}>
          <div className="flex items-center justify-around px-1 py-2">
            {visibleMobileNavItems.map((item) => {
              const isActive = (() => {
                const p = location.pathname;
                if (item.to === '/courses') return p.startsWith('/courses') || p.startsWith('/course');
                if (item.to === '/tests') return p.startsWith('/tests');
                if (item.to === '/knowledge-map') return p.startsWith('/knowledge-map');
                if (item.to === '/articles') return p === '/articles' || p.startsWith('/article/');
                if (item.to === '/qa') return p.startsWith('/qa');
                return p === item.to || p.startsWith(`${item.to}/`);
              })();
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={cn(
                    "relative flex flex-col items-center justify-center gap-0.5 py-1 px-3 rounded-lg transition-colors min-h-[44px] min-w-[44px]",
                    isActive ? "text-primary" : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  {isActive && <span className="absolute top-0 inset-x-3 h-0.5 bg-primary rounded-full" />}
                  <item.icon className="h-5 w-5" />
                  <span className="text-[10px] font-bold">{item.label}</span>
                </Link>
              );
            })}
          </div>
        </nav>

        {!isInstStudent && (
          <UpgradeModal
            open={showUpgradeModal}
            onOpenChange={setShowUpgradeModal}
            currentPlan={user?.membership_tier || instInfo?.plan || 'free'}
          />
        )}

        <AlertDialog open={showLogoutAlert} onOpenChange={setShowLogoutAlert}>
          <AlertDialogContent className="rounded-[2.5rem] border-none shadow-2xl bg-card">
            <AlertDialogHeader>
              <AlertDialogTitle className="text-xl font-bold text-foreground">{'确认退出登录？'}</AlertDialogTitle>
              <AlertDialogDescription className="font-medium text-muted-foreground">{'退出后你将需要重新验证身份以访问网校资源。'}</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel className="rounded-xl font-bold border-border text-foreground hover:bg-muted">{'返回'}</AlertDialogCancel>
              <AlertDialogAction onClick={async () => { try { await api.post('/users/logout/'); } catch (err) { console.error('Logout API failed:', err); } logout(); navigate('/login'); }} className="rounded-xl bg-primary text-primary-foreground font-bold hover:opacity-90">{'确认退出'}</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        <PersistentUploadToast />
        {invitePopoverOpen && instInfo?.invite_slug && (
          <div className="fixed z-50" style={{
            top: (avatarRef.current?.getBoundingClientRect().bottom ?? 60) + 8,
            right: window.innerWidth - (avatarRef.current?.getBoundingClientRect().right ?? window.innerWidth - 200),
          }}>
            <InvitePopover
              inviteSlug={instInfo.invite_slug}
              onClose={() => setInvitePopoverOpen(false)}
            />
          </div>
        )}
        {invitePopoverOpen && (
          <div className="fixed inset-0 z-40" onClick={() => setInvitePopoverOpen(false)} />
        )}

        {showTour && (
          <GuidedTour
            steps={tourSteps}
            onDismiss={handleTourDismiss}
          />
        )}
        {showPanelTour && (
          <GuidedTour
            steps={panelTourSteps}
            onDismiss={handlePanelTourDismiss}
          />
        )}
      </div>
    </TooltipProvider>
  );
};
