import React, { useState, useEffect } from 'react';
import { Link, useLocation, Outlet, useNavigate } from 'react-router-dom';
import { BookOpen, FileText, Trophy, Clock, User as UserIcon, SignOut, ShieldCheck, CreditCard, CaretLeft, CaretRight, Sparkle, Gear, Brain, ChartBar, ChartLineUp, Buildings, ChatCircleText, Wrench, Eye, EyeSlash, UserPlus, Users, CalendarCheck, Globe, Robot } from '@phosphor-icons/react';
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

import { useTranslation } from 'react-i18next';
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

export const MainLayout: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();
  const { primaryColor, pageTitle } = useSystemStore();
  const [collapsed, setCollapsed] = useState(false);
  const [studentPreview, setStudentPreview] = useState(false);
  const [showLogoutAlert, setShowLogoutAlert] = useState(false);
  const isMobile = useIsMobile();
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);

  const { t, i18n } = useTranslation(['layout', 'common']);
  const { institution: instFromStore, fetchFeatures, hasFeature, loading: featuresLoading, previewMode, previewInstitution, exitPreview } = useInstitutionStore();
  const instInfo = instFromStore || user?.institution || null;

  const isFullPage = ['/management'].includes(location.pathname);
  const isEdgeToEdge = ['/workbench'].includes(location.pathname);
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
    pathname === '/workbench' ||
    pathname === '/plan' ||
    pathname.startsWith('/institution');
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
      ? t('layout:docTitle.withInstitution', { name: instInfo.name })
      : t('layout:docTitle.default');
  }, [instInfo?.name, t]);

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
  const isSuperAdmin = user?.role === 'admin' && !instInfo;
  const isInstStudent = Boolean(instInfo) && user?.institution_role === 'student';
  const effectiveIsInstStudent = studentPreview || isInstStudent;
  const homePath = effectiveIsInstStudent ? '/xiaoyu' : '/workbench';
  const instPlan = instInfo?.plan || 'free';
  const planLevel = (p: string) => ({ free: 1, starter: 2, growth: 3, enterprise: 4 })[p] || 1;
  const myPlanLevel = Math.max(planLevel(user?.membership_tier || 'free'), planLevel(instPlan));

  type NavItem = { to: string; icon: React.ComponentType<{ className?: string }>; label: string };

  // ── 路由 → 功能标志映射（与 App.tsx FeatureGuard 一致）──
  const NAV_FEATURE_MAP: Record<string, string> = {
    '/tests': 'quiz.exam',
    '/knowledge-map': 'knowledge.graph',
    '/qa': 'faq.system',
    '/plan': 'ai.assistant',
    '/study': 'study.room',
    '/interviews': 'interview.mock',
    '/mock-exam': 'pdf.mock',
  };

  // 功能可见性：有 feature 要求的项，必须 hasFeature 通过才显示
  const itemVisible = (item: NavItem) => {
    const feat = NAV_FEATURE_MAP[item.to];
    if (!feat) return true;
    if (featuresLoading) return false;
    return hasFeature(feat);
  };

  // ── 超级管理员 4 套件 ──
  const superAdminNavItems: NavItem[] = [
    { to: '/institution/admin', icon: Buildings, label: t('layout:nav.institutionAdmin') },
    { to: '/invite-codes', icon: Sparkle, label: t('layout:nav.inviteCodes') },
    { to: '/platform-analytics', icon: ChartLineUp, label: t('layout:nav.platformAnalytics') },
    { to: '/prompt-templates', icon: FileText, label: t('layout:nav.promptTemplates') },
  ];

  // ── 教师端 6 套件 ──
  const teacherNavItems: NavItem[] = [
    { to: '/workbench', icon: Robot, label: '工作台' },
    { to: '/assets', icon: Gear, label: '资产管理' },
    { to: '/knowledge-tree', icon: ChartBar, label: '知识树' },
    { to: '/qa', icon: ChatCircleText, label: t('layout:nav.qa') },
    { to: '/institution/students', icon: Users, label: t('layout:nav.members') },
    { to: '/management', icon: Wrench, label: t('layout:nav.maintenance') },
  ];

  // ── 学生端 9 套件 ──
  const studentNavItems: NavItem[] = [
    { to: '/xiaoyu', icon: Robot, label: t('layout:nav.xiaoyu') },
    { to: '/courses', icon: BookOpen, label: t('layout:nav.courses') },
    { to: '/tests', icon: Trophy, label: t('layout:nav.tests') },
    { to: '/knowledge-map', icon: Brain, label: t('layout:nav.knowledgeMap') },
    { to: '/articles', icon: FileText, label: t('layout:nav.articles') },
    { to: '/qa', icon: ChatCircleText, label: t('layout:nav.qa') },
    { to: '/plan', icon: CalendarCheck, label: t('layout:nav.plan') },
    { to: '/study', icon: Clock, label: t('layout:nav.studyRoom') },
    { to: '/mock-exam', icon: FileText, label: t('layout:nav.mockExams') },
  ];

  const navItems: NavItem[] = isSuperAdmin
    ? superAdminNavItems
    : (effectiveIsInstStudent ? studentNavItems : teacherNavItems);

  const visibleNavItems = navItems.filter(itemVisible);

  const mobileNavItems: NavItem[] = isSuperAdmin
    ? [
        { to: '/institution', icon: Buildings, label: t('layout:nav.institutionShort') },
        { to: '/invite-codes', icon: Sparkle, label: t('layout:nav.inviteShort') },
        { to: '/prompt-templates', icon: FileText, label: t('layout:nav.promptShort') },
      ]
    : effectiveIsInstStudent ? [
        { to: '/xiaoyu', icon: Robot, label: t('layout:nav.xiaoyuShort', '小宇') },
        { to: '/courses', icon: BookOpen, label: t('layout:nav.coursesShort') },
        { to: '/tests', icon: Trophy, label: t('layout:nav.testsShort') },
        { to: '/knowledge-map', icon: Brain, label: t('layout:nav.knowledgeShort') },
        { to: '/articles', icon: FileText, label: t('layout:nav.articlesShort') },
        { to: '/qa', icon: ChatCircleText, label: t('layout:nav.qaShort') },
      ]
    : [
        { to: '/workbench', icon: Robot, label: '工作台' },
        { to: '/assets', icon: Gear, label: '资产' },
        { to: '/knowledge-tree', icon: ChartBar, label: '知识树' },
        { to: '/qa', icon: ChatCircleText, label: t('layout:nav.qaShort') },
        { to: '/institution', icon: Users, label: '学员' },
      ];

  const visibleMobileNavItems = mobileNavItems.filter(itemVisible);

  return (
    <TooltipProvider delayDuration={0}>
      <div className="flex h-screen bg-background text-foreground overflow-hidden font-sans selection:bg-primary selection:text-primary-foreground">
        <aside className={cn(
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
          "flex-1 h-screen relative z-[var(--z-base)] flex flex-col bg-background",
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
                  <span className="opacity-70">学生视角</span>
                  <button onClick={() => { setStudentPreview(false); navigate('/workbench'); }} className="ml-1 px-2 py-0.5 rounded-md bg-primary/10 hover:bg-primary/20 transition-colors text-[11px] font-bold">
                    退出预览
                  </button>
                </div>
              )}
              <EloPopover />
              <NotificationBell />
              {/* 头像下拉 */}
              <DropdownMenu modal={false}>
                <DropdownMenuTrigger asChild>
                  <button className="rounded-full border border-border p-0.5 bg-card hover:scale-105 transition-transform">
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
                    <span className="font-bold text-xs">{t('layout:userMenu.personalSettings')}</span>
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate('/billing')} className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                    <CreditCard className="h-3.5 w-3.5" />
                    <span className="font-bold text-xs">{t('layout:nav.billing')}</span>
                  </DropdownMenuItem>
                  {!isSuperAdmin && instInfo && user?.is_institution_owner && (
                    <DropdownMenuItem onClick={() => navigate('/institution/admin')} className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                      <Gear className="h-3.5 w-3.5" />
                      <span className="font-bold text-xs">{t('layout:userMenu.institutionSettings')}</span>
                    </DropdownMenuItem>
                  )}
                  {!isSuperAdmin && instInfo && user?.is_institution_admin && (
                    <DropdownMenuItem onClick={() => {
                      navigator.clipboard.writeText(`${window.location.origin}/api/users/join/${instInfo.invite_slug}/`);
                      toast.success(t('layout:invite.copied'));
                    }} className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                      <UserPlus className="h-3.5 w-3.5" />
                      <span className="font-bold text-xs">{t('layout:invite.trigger')}</span>
                    </DropdownMenuItem>
                  )}
                  {!isSuperAdmin && instInfo && !isInstStudent && !studentPreview && (
                    <DropdownMenuItem onClick={() => { setStudentPreview(true); navigate('/xiaoyu'); }} className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                      <Eye className="h-3.5 w-3.5" />
                      <span className="font-bold text-xs">预览学生端</span>
                    </DropdownMenuItem>
                  )}
                  {studentPreview && (
                    <DropdownMenuItem onClick={() => { setStudentPreview(false); navigate('/workbench'); }} className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                      <EyeSlash className="h-3.5 w-3.5" />
                      <span className="font-bold text-xs">退出学生端预览</span>
                    </DropdownMenuItem>
                  )}
                  {user?.role === 'admin' && (
                    <DropdownMenuItem onClick={() => navigate('/system-settings')} className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                      <Gear className="h-3.5 w-3.5" />
                      <span className="font-bold text-xs">{t('layout:userMenu.appearanceSettings')}</span>
                    </DropdownMenuItem>
                  )}
                  {user?.is_member && (
                    <DropdownMenuItem onClick={() => window.dispatchEvent(new Event('open-weekly-report'))} className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                      <ChartBar className="h-3.5 w-3.5" />
                      <span className="font-bold text-xs">{t('layout:nav.weeklyReport')}</span>
                    </DropdownMenuItem>
                  )}
                  {!isInstStudent && myPlanLevel < 3 && (
                    <DropdownMenuItem onClick={() => setShowUpgradeModal(true)} className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                      <Sparkle className="h-3.5 w-3.5 text-amber-500" />
                      <span className="font-bold text-xs">{t('layout:upgradePlan')}</span>
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuSeparator className="my-2 bg-border" />
                  <DropdownMenuItem onClick={() => i18n.changeLanguage(i18n.language?.startsWith('zh') ? 'en' : 'zh')} className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                    <Globe className="h-3.5 w-3.5" />
                    <span className="font-bold text-xs">{i18n.language?.startsWith('zh') ? 'English' : '中文'}</span>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator className="my-2 bg-border" />
                  <DropdownMenuItem onClick={() => setShowLogoutAlert(true)} className="rounded-xl px-3 py-2 gap-3 cursor-pointer text-destructive focus:bg-destructive focus:text-destructive-foreground transition-colors">
                    <SignOut className="h-3.5 w-3.5" />
                    <span className="font-bold text-xs">{t('layout:userMenu.logout')}</span>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
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
                      <span className="font-bold text-xs">{t('layout:userMenu.personalSettings')}</span>
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => navigate('/billing')} className="rounded-xl px-3 py-2 gap-2 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                      <CreditCard className="h-3.5 w-3.5" />
                      <span className="font-bold text-xs">{t('layout:nav.billing')}</span>
                    </DropdownMenuItem>
                    {!isSuperAdmin && instInfo && user?.is_institution_owner && (
                      <DropdownMenuItem onClick={() => navigate('/institution/admin')} className="rounded-xl px-3 py-2 gap-2 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                        <Gear className="h-3.5 w-3.5" />
                        <span className="font-bold text-xs">{t('layout:userMenu.institutionSettings')}</span>
                      </DropdownMenuItem>
                    )}
                    {/* 机构看板：管理员可见 */}
                    {!isSuperAdmin && instInfo && !isInstStudent && (
                      <DropdownMenuItem onClick={() => navigate('/institution')} className="rounded-xl px-3 py-2 gap-2 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                        <ChartBar className="h-3.5 w-3.5" />
                        <span className="font-bold text-xs">{t('layout:userMenu.institutionDashboard')}</span>
                      </DropdownMenuItem>
                    )}
                    {!isSuperAdmin && instInfo && user?.is_institution_admin && (
                      <DropdownMenuItem
                        onClick={() => {
                          navigator.clipboard.writeText(`${window.location.origin}/api/users/join/${instInfo.invite_slug}/`);
                          toast.success(t('layout:invite.copied'));
                        }}
                        className="rounded-xl px-3 py-2 gap-2 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors"
                      >
                        <UserPlus className="h-3.5 w-3.5" />
                        <span className="font-bold text-xs">{t('layout:invite.mobileCopy')}</span>
                      </DropdownMenuItem>
                    )}
                    {user?.is_member && (
                      <DropdownMenuItem
                        onClick={() => window.dispatchEvent(new Event('open-weekly-report'))}
                        className="rounded-xl px-3 py-2 gap-2 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors"
                      >
                        <ChartBar className="h-3.5 w-3.5" />
                        <span className="font-bold text-xs">{t('layout:nav.weeklyReport')}</span>
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuSeparator className="my-2 bg-border" />
                    <DropdownMenuItem onClick={() => setShowLogoutAlert(true)} className="rounded-xl px-3 py-2 gap-2 cursor-pointer text-destructive focus:bg-destructive focus:text-destructive-foreground transition-colors">
                      <SignOut className="h-3.5 w-3.5" />
                      <span className="font-bold text-xs">{t('layout:userMenu.logout')}</span>
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
                  <span>{t('layout:previewMode', { name: previewInstitution.name, plan: previewInstitution.plan_label })}</span>
                </div>
                <Button size="sm" variant="ghost" className="text-white hover:bg-white/10 text-xs"
                  onClick={exitPreview}>
                  <EyeSlash className="h-3.5 w-3.5 mr-1" /> {t('layout:exitPreview')}
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
            currentPlan={user?.membership_tier || instPlan || 'free'}
          />
        )}

        <AlertDialog open={showLogoutAlert} onOpenChange={setShowLogoutAlert}>
          <AlertDialogContent className="rounded-[2.5rem] border-none shadow-2xl bg-card">
            <AlertDialogHeader>
              <AlertDialogTitle className="text-xl font-bold text-foreground">{t('layout:logout.title')}</AlertDialogTitle>
              <AlertDialogDescription className="font-medium text-muted-foreground">{t('layout:logout.description')}</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel className="rounded-xl font-bold border-border text-foreground hover:bg-muted">{t('layout:logout.cancel')}</AlertDialogCancel>
              <AlertDialogAction onClick={async () => { try { await api.post('/users/logout/'); } catch {} logout(); navigate('/login'); }} className="rounded-xl bg-primary text-primary-foreground font-bold hover:opacity-90">{t('layout:logout.confirm')}</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        <PersistentUploadToast />
      </div>
    </TooltipProvider>
  );
};
