import React, { useState, useEffect } from 'react';
import { Link, useLocation, Outlet, useNavigate } from 'react-router-dom';
import {
  BookOpen,
  FileText,
  Trophy,
  Clock,
  User as UserIcon,
  LogOut,
  ShieldCheck,
  CreditCard,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  Settings2,
  BrainCircuit,
  BarChart3,
  LineChart,
  Building2,
  MessageCircleQuestion,
  Wrench,
  Eye,
  EyeOff,
  UserPlus,
  Users,
  CalendarCheck,
  Globe,
  Bot,
} from 'lucide-react';
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
  const [showLogoutAlert, setShowLogoutAlert] = useState(false);
  const isMobile = useIsMobile();
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);

  const { t, i18n } = useTranslation(['layout', 'common']);
  const { institution: instFromStore, fetchFeatures, hasFeature, loading: featuresLoading, previewMode, previewInstitution, exitPreview } = useInstitutionStore();
  const instInfo = instFromStore || user?.institution || null;

  const isFullPage = ['/management'].includes(location.pathname);
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
    pathname === '/workbench' ||
    pathname === '/plan' ||
    pathname.startsWith('/institution');
  const isMobileStudyPage = isMobile && location.pathname === '/study';
  const isMobileImmersivePage = isMobile && location.pathname.startsWith('/tests/session');
  const isMobileVideoPage = isMobile && location.pathname.startsWith('/course/');
  const hideMobileBottomNav = isMobile && (
    location.pathname.startsWith('/tests/session') ||
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
    fetchFeatures();
  }, []);

  useEffect(() => {
    if (!isMobile) return;
    if (!isMobileAllowedPath(location.pathname)) {
      navigate('/qa', { replace: true });
    }
  }, [isMobile, location.pathname, navigate]);


  // ── 身份与方案层级 ──
  const isSuperAdmin = user?.role === 'admin' && !instInfo;
  const isInstStudent = Boolean(instInfo) && user?.institution_role === 'student';
  const homePath = isInstStudent ? '/xiaoyu' : '/workbench';
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

  // ── 超级管理员 —— 只看机构管理 + 邀请码 ──
  const navItems: NavItem[] = isSuperAdmin
    ? [
        { to: '/institution/admin', icon: Building2, label: t('layout:nav.institutionAdmin') },
        { to: '/invite-codes', icon: Sparkles, label: t('layout:nav.inviteCodes') },
        { to: '/platform-analytics', icon: LineChart, label: t('layout:nav.platformAnalytics') },
        { to: '/prompt-templates', icon: FileText, label: t('layout:nav.promptTemplates') },
      ]
    : [
        { to: '/xiaoyu', icon: Bot, label: t('layout:nav.xiaoyu') },
        { to: '/courses', icon: BookOpen, label: t('layout:nav.courses') },
        { to: '/tests', icon: Trophy, label: t('layout:nav.tests') },
        { to: '/knowledge-map', icon: BrainCircuit, label: t('layout:nav.knowledgeMap') },
        { to: '/articles', icon: FileText, label: t('layout:nav.articles') },
        { to: '/qa', icon: MessageCircleQuestion, label: t('layout:nav.qa') },
        { to: '/plan', icon: CalendarCheck, label: t('layout:nav.plan') },
        { to: '/study', icon: Clock, label: t('layout:nav.studyRoom') },

        { to: '/mock-exam', icon: FileText, label: t('layout:nav.mockExams') },
      ];

  // ── 机构管理菜单 ──
  if (!isSuperAdmin && instInfo) {
    if (user?.is_institution_admin) {
      navItems.unshift({ to: '/workbench', icon: Sparkles, label: t('layout:nav.workbench') });
      navItems.push({ to: '/institution/students', icon: Users, label: t('layout:nav.members') });
      navItems.push({ to: '/management', icon: Wrench, label: t('layout:nav.maintenance') });
    }
  }

  const visibleNavItems = navItems.filter(itemVisible);

  const mobileNavItems: NavItem[] = isSuperAdmin
    ? [
        { to: '/institution', icon: Building2, label: t('layout:nav.institutionShort') },
        { to: '/invite-codes', icon: Sparkles, label: t('layout:nav.inviteShort') },
        { to: '/prompt-templates', icon: FileText, label: t('layout:nav.promptShort') },
      ]
    : [
        { to: '/xiaoyu', icon: Bot, label: t('layout:nav.xiaoyuShort', '小宇') },
        { to: '/courses', icon: BookOpen, label: t('layout:nav.coursesShort') },
        { to: '/tests', icon: Trophy, label: t('layout:nav.testsShort') },
        { to: '/knowledge-map', icon: BrainCircuit, label: t('layout:nav.knowledgeShort') },
        { to: '/articles', icon: FileText, label: t('layout:nav.articlesShort') },
        { to: '/qa', icon: MessageCircleQuestion, label: t('layout:nav.qaShort') },
      ];

  const visibleMobileNavItems = mobileNavItems.filter(itemVisible);

  return (
    <TooltipProvider delayDuration={0}>
      <div className="flex h-screen bg-background text-foreground overflow-hidden font-sans selection:bg-primary selection:text-primary-foreground">
        <aside className={cn(
          "relative border-r border-border flex-col p-2 bg-card/70 backdrop-blur-2xl transition-[width] duration-300 ease-in-out z-30 shrink-0 hidden md:flex",
          collapsed ? "w-16" : "w-48"
        )}>
          {/* Header: logo icon fixed at left, expanded logo slides out from behind */}
          <div className="mb-6 mt-2 px-2 group/header">
            <div className="relative h-10 flex items-center">
              {/* Collapsed icon — always visible, always at left */}
              <Link to={homePath} className={cn(
                "absolute left-0 top-0 h-10 w-10 rounded-xl overflow-hidden shrink-0 transition-opacity duration-200 z-10",
                collapsed ? "opacity-100 group-hover/header:opacity-0" : "opacity-0 pointer-events-none"
              )}>
                <img src="/unimind_logo_small.png" alt="Unimind.ai" className="w-full h-full object-contain brand-logo-invert" />
              </Link>
              {/* Expand button — same position as icon, appears on hover when collapsed */}
              <div
                className={cn(
                  "absolute left-0 top-0 h-10 w-10 rounded-xl flex items-center justify-center shrink-0 cursor-pointer hover:bg-muted transition-all duration-200 z-20",
                  collapsed ? "opacity-0 group-hover/header:opacity-100" : "opacity-0 pointer-events-none"
                )}
                onClick={() => setCollapsed(false)}
              >
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              </div>
              {/* Expanded logo — slides out from behind the icon, clickable to XiaoYu */}
              <Link to={homePath} className={cn(
                "absolute left-0 top-0 h-10 overflow-hidden transition-all duration-300",
                collapsed ? "w-10 opacity-0" : "w-32 opacity-100"
              )}>
                <img src={UnimindLogo} alt="Unimind.ai" className="h-10 w-32 object-contain brand-logo-invert" />
              </Link>
              {/* Collapse button — absolutely positioned at right edge */}
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setCollapsed(true)}
                className={cn(
                  "absolute right-0 top-1/2 -translate-y-1/2 text-muted-foreground hover:bg-muted rounded-full h-6 w-6 shrink-0 transition-opacity duration-200 z-10",
                  collapsed ? "opacity-0 pointer-events-none" : "opacity-100"
                )}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
            </div>
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

          <div className="mt-auto">
            {user ? (
              <DropdownMenu modal={false}>
                <DropdownMenuTrigger asChild>
                  <div className="group flex items-center gap-2.5 p-2 rounded-xl cursor-pointer transition-all duration-300 hover:bg-muted border border-transparent hover:border-border">
                    <Avatar className="h-8 w-8 border border-border shadow-sm group-hover:scale-105 transition-transform shrink-0">
                      <AvatarImage src={user?.avatar_url} />
                      <AvatarFallback className="bg-muted text-[11px] font-bold">{user?.username?.[0]}</AvatarFallback>
                    </Avatar>
                    <div className={cn(
                      "flex-1 min-w-0 overflow-hidden transition-all duration-200",
                      collapsed ? "opacity-0 max-w-0" : "opacity-100 max-w-[200px]"
                    )}>
                      <div className="flex items-center gap-1.5">
                        <p className="text-[12px] font-bold truncate whitespace-nowrap">{user?.nickname || user?.username}</p>
                        {user.is_member && <ShieldCheck className="h-3 w-3 text-amber-500 shrink-0" />}
                      </div>
                      <p className="text-[11px] font-bold text-muted-foreground uppercase tracking-tight whitespace-nowrap">{instInfo ? `${instInfo.name} · ${instInfo.plan_label || instInfo.plan}` : isSuperAdmin ? t('layout:userStatus.superAdmin') : (user.is_member ? t('layout:userMenu.proMember') : t('layout:userMenu.freeScholar'))}</p>
                    </div>
                  </div>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" side={collapsed ? "right" : "top"} className="w-52 rounded-2xl p-2 bg-card/95 backdrop-blur-xl border-border shadow-lg">
                  <DropdownMenuLabel className="px-3 py-2 text-[11px] font-bold text-muted-foreground uppercase tracking-wider">{t('layout:userMenu.accountPreferences')}</DropdownMenuLabel>
                  <DropdownMenuItem onClick={() => navigate('/settings')} className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                    <UserIcon className="h-3.5 w-3.5" />
                    <span className="font-bold text-xs">{t('layout:userMenu.personalSettings')}</span>
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => navigate('/billing')} className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                    <CreditCard className="h-3.5 w-3.5" />
                    <span className="font-bold text-xs">{t('layout:nav.billing')}</span>
                  </DropdownMenuItem>
                  {/* 机构设置：仅机构所有者可见 */}
                  {!isSuperAdmin && instInfo && user?.is_institution_owner && (
                    <DropdownMenuItem onClick={() => navigate('/institution/admin')} className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                      <Settings2 className="h-3.5 w-3.5" />
                      <span className="font-bold text-xs">{t('layout:userMenu.institutionSettings')}</span>
                    </DropdownMenuItem>
                  )}
                  {/* 机构看板：管理员可见 */}
                  {!isSuperAdmin && instInfo && !isInstStudent && (
                    <DropdownMenuItem onClick={() => navigate('/institution')} className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                      <BarChart3 className="h-3.5 w-3.5" />
                      <span className="font-bold text-xs">{t('layout:userMenu.institutionDashboard')}</span>
                    </DropdownMenuItem>
                  )}
                  {/* 邀请学生：机构管理员可见 */}
                  {!isSuperAdmin && instInfo && user?.is_institution_admin && (
                    <DropdownMenuItem
                      onClick={() => {
                        navigator.clipboard.writeText(`${window.location.origin}/api/users/join/${instInfo.invite_slug}/`);
                        toast.success(t('layout:invite.copied'));
                      }}
                      className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors"
                    >
                      <UserPlus className="h-3.5 w-3.5" />
                      <span className="font-bold text-xs">{t('layout:invite.trigger')}</span>
                    </DropdownMenuItem>
                  )}
                  {user?.role === 'admin' && (
                    <DropdownMenuItem onClick={() => navigate('/system-settings')} className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                      <Settings2 className="h-3.5 w-3.5" />
                      <span className="font-bold text-xs">{t('layout:userMenu.appearanceSettings')}</span>
                    </DropdownMenuItem>
                  )}
                  {user?.is_member && (
                    <DropdownMenuItem
                      onClick={() => window.dispatchEvent(new Event('open-weekly-report'))}
                      className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors"
                    >
                      <BarChart3 className="h-3.5 w-3.5" />
                      <span className="font-bold text-xs">{t('layout:nav.weeklyReport')}</span>
                    </DropdownMenuItem>
                  )}
                  {/* 升级方案：非机构学生且未达最高方案 */}
                  {!isInstStudent && myPlanLevel < 3 && (
                    <DropdownMenuItem onClick={() => setShowUpgradeModal(true)} className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                      <Sparkles className="h-3.5 w-3.5 text-amber-500" />
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
                    <LogOut className="h-3.5 w-3.5" />
                    <span className="font-bold text-xs">{t('layout:userMenu.logout')}</span>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : (
              <Link to="/login">
                <Button variant="outline" className="w-full gap-2 justify-start overflow-hidden">
                  <LogOut className="h-4 w-4 shrink-0" />
                  <span className={cn("transition-all duration-200 whitespace-nowrap overflow-hidden", collapsed ? "opacity-0 max-w-0" : "opacity-100 max-w-[100px]")}>{t('common:login')}</span>
                </Button>
              </Link>
            )}
          </div>
        </aside>

        <main className={cn(
          "flex-1 h-screen relative z-10 flex flex-col bg-background",
          (isMobileImmersivePage || isMobileStudyPage)
            ? "overflow-hidden pb-0"
            : "overflow-y-auto pb-[calc(5rem+env(safe-area-inset-bottom))] md:pb-0"
        )}>
          {!isFullPage && !isMobileImmersivePage && (
            <header className="sticky top-0 shrink-0 z-20 hidden md:flex pointer-events-none">
               <div className="flex items-center gap-2 ml-auto pr-6 py-3 pointer-events-auto">
                  {user && <EloPopover />}
                  {user && <NotificationBell />}
               </div>
            </header>
          )}
          {!isFullPage && !isMobileImmersivePage && (
            <header className="sticky top-0 h-14 shrink-0 border-b border-border bg-background/90 backdrop-blur-xl z-20 px-4 flex items-center justify-between md:hidden">
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
                        <Settings2 className="h-3.5 w-3.5" />
                        <span className="font-bold text-xs">{t('layout:userMenu.institutionSettings')}</span>
                      </DropdownMenuItem>
                    )}
                    {/* 机构看板：管理员可见 */}
                    {!isSuperAdmin && instInfo && !isInstStudent && (
                      <DropdownMenuItem onClick={() => navigate('/institution')} className="rounded-xl px-3 py-2 gap-2 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                        <BarChart3 className="h-3.5 w-3.5" />
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
                        <BarChart3 className="h-3.5 w-3.5" />
                        <span className="font-bold text-xs">{t('layout:nav.weeklyReport')}</span>
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuSeparator className="my-2 bg-border" />
                    <DropdownMenuItem onClick={() => setShowLogoutAlert(true)} className="rounded-xl px-3 py-2 gap-2 cursor-pointer text-destructive focus:bg-destructive focus:text-destructive-foreground transition-colors">
                      <LogOut className="h-3.5 w-3.5" />
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
                : !isFullPage && "px-4 py-4 md:px-8 md:py-6",
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
                  <EyeOff className="h-3.5 w-3.5 mr-1" /> {t('layout:exitPreview')}
                </Button>
              </div>
            )}
            <Outlet />
          </div>
        </main>

        <nav className={cn(
          "md:hidden fixed bottom-0 inset-x-0 z-30 border-t border-border bg-card/95 backdrop-blur-xl pb-[env(safe-area-inset-bottom)]",
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
