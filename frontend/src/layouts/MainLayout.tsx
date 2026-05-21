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
  ChevronLeft,
  ChevronRight,
  Sparkles,
  Settings2,
  BrainCircuit,
  BarChart3,
  Building2,
  MessageCircleQuestion,
  Loader2,
  Lock,
  Mic,
  Wrench,
  Eye,
  EyeOff,
  UserPlus,
  Users,
  Copy,
  RefreshCw,
  GraduationCap,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { useAuthStore } from '@/store/useAuthStore';
import { useSystemStore } from '@/store/useSystemStore';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import { NotificationBell } from '@/components/NotificationBell';
import { OnboardingDialog } from '@/components/OnboardingDialog';
import { UpgradeModal } from '@/components/UpgradeModal';
import { EloPopover } from '@/components/EloPopover';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import { useTranslation } from 'react-i18next';
import api from '@/lib/api';
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import UnimindLogo from '../../Unimind_logo.png';
import { PersistentUploadToast } from '@/components/PersistentUploadToast';

const SidebarItem = ({ to, icon: Icon, label, active, collapsed, restricted, onRestrictedClick }: any) => {
  const { t } = useTranslation('layout');
  const content = (
    <div className="px-1">
      <Button
        variant="ghost"
        onClick={() => {
          if (restricted) onRestrictedClick();
        }}
        asChild={!restricted}
        className={cn(
          "w-full justify-start gap-3 h-10 px-3 transition-all duration-200 rounded-lg cursor-pointer",
          active
            ? "bg-card text-foreground shadow-sm border border-border"
            : "text-muted-foreground hover:bg-muted hover:text-foreground",
          collapsed && "justify-center px-0"
        )}
      >
        {restricted ? (
          <>
            <div className="relative">
              <Icon className={cn("h-4 w-4 shrink-0", active ? "text-foreground" : "text-muted-foreground")} />
              <div className="absolute -top-1 -right-1 h-3.5 w-3.5 bg-unimind-bg-secondary rounded-full flex items-center justify-center border border-border shadow-sm" title={t('lockedTooltip')}>
                <Lock className="h-2 w-2 text-muted-foreground" />
              </div>
            </div>
            {!collapsed && <span className="font-bold text-[13px] tracking-tight">{label}</span>}
          </>
        ) : (
          <Link to={to} className="flex items-center gap-3 w-full h-full">
            <Icon className={cn("h-4 w-4 shrink-0", active ? "text-foreground" : "text-muted-foreground")} />
            {!collapsed && <span className="font-bold text-[13px] tracking-tight">{label}</span>}
          </Link>
        )}
      </Button>
    </div>
  );

  return collapsed ? (
    <TooltipProvider delayDuration={0}>
      <Tooltip>
        <TooltipTrigger asChild>{content}</TooltipTrigger>
        <TooltipContent side="right" className="font-bold border-none shadow">{label}{restricted && ` (${t('lockedTooltip')})`}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  ) : content;
};

export const MainLayout: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout, updateUser } = useAuthStore();
  const { primaryColor, pageTitle, pageSubtitle } = useSystemStore();
  const [collapsed, setCollapsed] = useState(false);
  const [showLogoutAlert, setShowLogoutAlert] = useState(false);
  const [showActivateDialog, setShowActivateDialog] = useState(false);
  const [activationCode, setActivationCode] = useState('');
  const [isActivating, setIsActivating] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);
  const [restrictedFeature, setRestrictedFeature] = useState<string | undefined>(undefined);
  const [inviteRole, setInviteRole] = useState<'student' | 'teacher'>('student');

  const { t } = useTranslation(['layout', 'common']);
  const { institution: instFromStore, fetchFeatures, previewMode, previewInstitution, exitPreview } = useInstitutionStore();
  const instInfo = instFromStore || user?.institution || null;

  const isFullPage = ['/management'].includes(location.pathname);
  const isMobileAllowedPath = (pathname: string) =>
    pathname === '/' ||
    pathname === '/articles' ||
    pathname.startsWith('/article/') ||
    pathname === '/qa' ||
    pathname.startsWith('/qa/') ||
    pathname === '/study' ||
    pathname === '/ai' ||
    pathname === '/knowledge-map' ||
    pathname.startsWith('/knowledge-map/') ||
    pathname === '/tests' ||
    pathname.startsWith('/tests/') ||
    pathname === '/settings' ||
    pathname === '/courses' ||
    pathname.startsWith('/course/');
  const isMobileStudyPage = isMobile && location.pathname === '/study';
  const isMobileImmersivePage = isMobile && location.pathname.startsWith('/tests/session');
  const isMobileVideoPage = isMobile && location.pathname.startsWith('/course/');
  const hideMobileBottomNav = isMobile && location.pathname.startsWith('/tests/session');

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
    if (typeof window === 'undefined') return;
    const media = window.matchMedia('(max-width: 767px)');
    const sync = () => setIsMobile(media.matches);
    sync();
    media.addEventListener('change', sync);
    return () => media.removeEventListener('change', sync);
  }, []);

  useEffect(() => {
    if (!isMobile) return;
    if (!isMobileAllowedPath(location.pathname)) {
      navigate('/qa', { replace: true });
    }
  }, [isMobile, location.pathname, navigate]);


  const handleActivate = async () => {
    if (!activationCode.trim()) return toast.error(t('layout:activation.enterCodePrompt'));
    setIsActivating(true);
    try {
      const res = await api.post('/users/me/activate/', { code: activationCode });
      updateUser(res.data.user);
      toast.success(t('layout:activation.success'));
      setShowActivateDialog(false);
      setActivationCode('');
    } catch (e: any) {
      toast.error(e.response?.data?.error || t('layout:activation.failed'));
    } finally {
      setIsActivating(false);
    }
  };

  // ── 身份与方案层级 ──
  const isSuperAdmin = user?.role === 'admin' && !instInfo;
  const isInstStudent = Boolean(instInfo) && user?.institution_role === 'student';
  const instPlan = instInfo?.plan || 'free';
  const planLevel = (p: string) => ({ free: 1, solo: 2, plus: 3, pro: 4 })[p] || 1;
  const myPlanLevel = Math.max(planLevel(user?.membership_tier || 'free'), planLevel(instPlan));
  const atLeast = (lvl: number) => myPlanLevel >= lvl;

  type NavItem = { to: string; icon: any; label: string; minPlan?: number; section?: string };

  // ── 超级管理员 —— 只看机构管理 + 邀请码 ──
  const navItems: NavItem[] = isSuperAdmin
    ? [
        { to: '/institution/admin', icon: Building2, label: t('layout:nav.institutionAdmin') },
        { to: '/invite-codes', icon: Sparkles, label: t('layout:nav.inviteCodes') },
        { to: '/prompt-templates', icon: FileText, label: t('layout:nav.promptTemplates') },
      ]
    : [
        { to: '/courses', icon: BookOpen, label: t('layout:nav.courses') },
        { to: '/tests', icon: Trophy, label: t('layout:nav.tests') },
        { to: '/knowledge-map', icon: BrainCircuit, label: t('layout:nav.knowledgeMap'), minPlan: 2 },
        { to: '/articles', icon: FileText, label: t('layout:nav.articles') },
        { to: '/qa', icon: MessageCircleQuestion, label: t('layout:nav.qa'), minPlan: 3 },
        { to: '/ai', icon: Sparkles, label: t('layout:nav.aiLab'), minPlan: 2 },
        { to: '/study', icon: Clock, label: t('layout:nav.studyRoom'), minPlan: 3 },
        { to: '/interviews', icon: Mic, label: t('layout:nav.interviews'), minPlan: 3 },
        { to: '/mock-exam', icon: FileText, label: t('layout:nav.mockExams'), minPlan: 3 },
      ];

  // ── 机构管理菜单 ──
  if (!isSuperAdmin && instInfo) {
    if (user?.is_institution_admin) {
      navItems.push({ to: '/institution/students', icon: Users, label: '成员管理', section: 'institution' });
      navItems.push({ to: '/management', icon: Wrench, label: t('layout:nav.maintenance'), section: 'institution' });
    }
  }

  // 学生不看到锁定的功能入口——方案升级是教师/机构的事
  const visibleNavItems = isInstStudent
    ? navItems.filter(item => !item.minPlan || atLeast(item.minPlan))
    : navItems;

  const mobileNavItems: NavItem[] = isSuperAdmin
    ? [
        { to: '/institution', icon: Building2, label: t('layout:nav.institutionShort') },
        { to: '/invite-codes', icon: Sparkles, label: t('layout:nav.inviteShort') },
        { to: '/prompt-templates', icon: FileText, label: t('layout:nav.promptShort') },
      ]
    : [
        { to: '/courses', icon: BookOpen, label: t('layout:nav.coursesShort') },
        { to: '/tests', icon: Trophy, label: t('layout:nav.testsShort') },
        { to: '/knowledge-map', icon: BrainCircuit, label: t('layout:nav.knowledgeShort'), minPlan: 2 },
        { to: '/articles', icon: FileText, label: t('layout:nav.articlesShort') },
        { to: '/qa', icon: MessageCircleQuestion, label: t('layout:nav.qaShort'), minPlan: 3 },
      ];

  const visibleMobileNavItems = isInstStudent
    ? mobileNavItems.filter(item => !item.minPlan || atLeast(item.minPlan))
    : mobileNavItems;

  // Sidebar onRestrictedClick: show upgrade modal with appropriate feature
  const PATH_FEATURE_MAP: Record<string, string> = {
    '/knowledge-map': 'knowledge.graph',
    '/ai': 'ai.assistant',
    '/qa': 'faq.system',
    '/study': 'study.room',
    '/interviews': 'interview.mock',
    '/mock-exam': 'pdf.mock',
  };
  const handleRestrictedClick = (item: NavItem) => {
    setRestrictedFeature(PATH_FEATURE_MAP[item.to]);
    setShowUpgradeModal(true);
  };

  return (
    <TooltipProvider delayDuration={0}>
      <div className="flex h-screen bg-background text-foreground overflow-hidden font-sans selection:bg-primary selection:text-primary-foreground">
        <aside className={cn(
          "relative border-r border-border flex-col p-2 bg-card/70 backdrop-blur-2xl transition-all duration-500 ease-in-out z-30 shrink-0 hidden md:flex",
          collapsed ? "w-16 min-w-16 max-w-16" : "w-48 min-w-48 max-w-48"
        )}>
          {/* Header Section */}
          <div className={cn("mb-6 mt-2 flex items-center transition-all", collapsed ? "flex-col gap-2 justify-center" : "justify-between px-2")}>
            <div className={cn("shrink-0 overflow-hidden", collapsed ? "w-10 h-10 rounded-xl" : "w-32 h-8")}>
              <img src={UnimindLogo} alt="Unimind.ai" className="w-full h-full object-contain brand-logo-invert" />
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setCollapsed(!collapsed)}
              className={cn(
                "text-muted-foreground hover:bg-muted rounded-full",
                collapsed ? "h-8 w-8" : "h-6 w-6"
              )}
            >
              {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
            </Button>
          </div>

          <nav className="flex-1 space-y-0.5">
            {visibleNavItems.map(item => (
              <SidebarItem
                key={item.to}
                {...item}
                active={location.pathname === item.to}
                collapsed={collapsed}
                restricted={Boolean((item as any).minPlan && !atLeast((item as any).minPlan))}
                onRestrictedClick={() => handleRestrictedClick(item)}
              />
            ))}

          </nav>

          <div className="mt-auto">
            {user ? (
              <DropdownMenu modal={false}>
                <DropdownMenuTrigger asChild>
                  <div className={cn("group flex items-center gap-2.5 p-2 rounded-xl cursor-pointer transition-all duration-300 hover:bg-muted border border-transparent hover:border-border", collapsed && "justify-center")}>
                    <Avatar className={cn("h-8 w-8 border border-border shadow-sm group-hover:scale-105 transition-transform")}>
                      <AvatarImage src={user?.avatar_url} />
                      <AvatarFallback className="bg-muted text-[11px] font-bold">{user?.username?.[0]}</AvatarFallback>
                    </Avatar>
                    {!collapsed && (
                      <div className="flex-1 min-w-0 animate-in fade-in">
                        <div className="flex items-center gap-1.5">
                          <p className="text-[12px] font-bold truncate">{user?.nickname || user?.username}</p>
                          {user.is_member && <ShieldCheck className="h-3 w-3 text-amber-500" />}
                        </div>
                        <p className="text-[11px] font-bold text-muted-foreground uppercase tracking-tight">{instInfo ? `${instInfo.name} · ${instInfo.plan_label || instInfo.plan}` : isSuperAdmin ? t('layout:userStatus.superAdmin') : (user.is_member ? t('layout:userMenu.proMember') : t('layout:userMenu.freeScholar'))}</p>
                      </div>
                    )}
                  </div>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" side={collapsed ? "right" : "top"} className="w-52 rounded-2xl p-2 bg-card/95 backdrop-blur-xl border-border shadow-lg">
                  <DropdownMenuLabel className="px-3 py-2 text-[11px] font-bold text-muted-foreground uppercase tracking-wider">{t('layout:userMenu.accountPreferences')}</DropdownMenuLabel>
                  {user && !user.is_member && !isInstStudent && (
                    <DropdownMenuItem onClick={() => setShowActivateDialog(true)} className="rounded-xl px-3 py-2 gap-3 cursor-pointer bg-amber-50 text-amber-700 focus:bg-amber-100 focus:text-amber-800 transition-colors">
                      <Sparkles className="h-3.5 w-3.5" />
                      <span className="font-bold text-xs">{t('layout:userMenu.activateMember')}</span>
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuItem onClick={() => navigate('/settings')} className="rounded-xl px-3 py-2 gap-3 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                    <UserIcon className="h-3.5 w-3.5" />
                    <span className="font-bold text-xs">{t('layout:userMenu.personalSettings')}</span>
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
                  <DropdownMenuSeparator className="my-2 bg-border" />
                  <DropdownMenuItem onClick={() => setShowLogoutAlert(true)} className="rounded-xl px-3 py-2 gap-3 cursor-pointer text-destructive focus:bg-destructive focus:text-destructive-foreground transition-colors">
                    <LogOut className="h-3.5 w-3.5" />
                    <span className="font-bold text-xs">{t('layout:userMenu.logout')}</span>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : (
              <Link to="/login">
                <Button variant="outline" className={cn("w-full gap-2", collapsed ? "px-0 justify-center" : "justify-start")}>
                  <LogOut className="h-4 w-4" />
                  {!collapsed && <span>{t('common:login')}</span>}
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
            <header className="sticky top-0 h-14 shrink-0 border-b border-border bg-background/80 backdrop-blur-xl z-20 px-10 items-center justify-between transition-all hidden md:flex">
               <div className="flex flex-col justify-center min-w-0">
                  {pageTitle && (
                    <div className="flex flex-col md:flex-row md:items-baseline md:gap-3 animate-in fade-in slide-in-from-top-1 duration-300">
                      <h2 className="text-sm font-black tracking-tight text-foreground uppercase">{pageTitle}</h2>
                      <span className="text-[12px] font-bold text-muted-foreground/60 uppercase tracking-widest truncate max-w-[400px]">
                        {pageSubtitle}
                      </span>
                    </div>
                  )}
               </div>
               <div className="flex items-center gap-3">
                  {/* Clickable ELO */}
                  {user && <EloPopover />}
                  {/* Invite students — institution admin (owner / teacher) */}
                  {!isSuperAdmin && instInfo && user?.is_institution_admin && (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="sm" className="h-8 rounded-full px-3 text-[11px] font-bold">
                          <UserPlus className="h-3.5 w-3.5 mr-1" />
                          {t('layout:invite.trigger')}
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end" className="w-80 rounded-2xl p-3 bg-card/95 backdrop-blur-xl border-border shadow-lg">
                        <DropdownMenuLabel className="text-xs font-bold uppercase tracking-wider text-muted-foreground px-1">
                          {t('layout:invite.title', { name: instInfo.name })}
                        </DropdownMenuLabel>
                        <DropdownMenuSeparator />
                        <div className="space-y-3 px-1 py-1">
                          {/* Role selector */}
                          <div className="space-y-1.5">
                            <Label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">邀请角色</Label>
                            <div className="flex gap-1.5">
                              <Button
                                variant={inviteRole === 'student' ? 'default' : 'outline'}
                                size="sm"
                                className="flex-1 h-8 rounded-lg text-[11px] font-bold"
                                onClick={() => setInviteRole('student')}
                              >
                                <GraduationCap className="h-3 w-3 mr-1" />
                                学员
                              </Button>
                              <Button
                                variant={inviteRole === 'teacher' ? 'default' : 'outline'}
                                size="sm"
                                className="flex-1 h-8 rounded-lg text-[11px] font-bold"
                                onClick={() => setInviteRole('teacher')}
                              >
                                <UserPlus className="h-3 w-3 mr-1" />
                                教师
                              </Button>
                            </div>
                          </div>
                          <div className="space-y-1.5">
                            <Label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider">{t('layout:invite.linkLabel')}</Label>
                            <div className="flex items-center gap-2">
                              <code className="flex-1 bg-muted px-3 py-2 rounded-lg text-[11px] font-mono font-bold truncate select-all">
                                {window.location.origin}/api/users/join/{instInfo.invite_slug}/{inviteRole === 'teacher' ? '?role=teacher' : ''}
                              </code>
                              <Button
                                variant="outline"
                                size="icon"
                                className="h-8 w-8 shrink-0"
                                onClick={() => {
                                  const suffix = inviteRole === 'teacher' ? '?role=teacher' : '';
                                  navigator.clipboard.writeText(`${window.location.origin}/api/users/join/${instInfo.invite_slug}/${suffix}`);
                                  toast.success(t('layout:invite.copied'));
                                }}
                              >
                                <Copy className="h-3.5 w-3.5" />
                              </Button>
                            </div>
                          </div>
                          <p className="text-[11px] text-muted-foreground leading-relaxed">
                            {inviteRole === 'teacher' ? '通过此链接注册的用户将自动成为教师角色。' : t('layout:invite.description')}
                          </p>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="w-full text-[11px] font-bold text-muted-foreground"
                            onClick={async () => {
                              try {
                                await api.post('/users/institution/me/regenerate-invite-slug/');
                                toast.success(t('layout:invite.regenerated'));
                                fetchFeatures();
                              } catch {
                                toast.error(t('layout:invite.regenerateFailed'));
                              }
                            }}
                          >
                            <RefreshCw className="h-3 w-3 mr-1" />
                            {t('layout:invite.regenerate')}
                          </Button>
                        </div>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )}
                  {/* Upgrade plan button — hidden for institution students, plus & pro */}
                  {!isInstStudent && myPlanLevel < 3 && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8 rounded-full px-3 text-[11px] font-bold bg-amber-50 border-amber-200 text-amber-700 hover:bg-amber-100 hover:border-amber-300 transition-all"
                      onClick={() => {
                        setRestrictedFeature(undefined);
                        setShowUpgradeModal(true);
                      }}
                    >
                      <Sparkles className="h-3 w-3 mr-1 text-amber-500" />
                      {t('layout:upgradePlan')}
                    </Button>
                  )}
                  <LanguageSwitcher variant="compact" />
                  <div className="h-6 w-px bg-border mx-1" />
                  {user && <NotificationBell />}
                  <Avatar className={cn("h-8 w-8 border border-border shadow-sm")}>
                     <AvatarImage src={user?.avatar_url} />
                     <AvatarFallback className="text-xs font-bold">{user?.username?.[0]}</AvatarFallback>
                  </Avatar>
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
                    {user && !user.is_member && !isInstStudent && (
                      <DropdownMenuItem onClick={() => setShowActivateDialog(true)} className="rounded-xl px-3 py-2 gap-2 cursor-pointer bg-amber-50 text-amber-700 focus:bg-amber-100 focus:text-amber-800 transition-colors">
                        <Sparkles className="h-3.5 w-3.5" />
                        <span className="font-bold text-xs">{t('layout:userMenu.activateMember')}</span>
                      </DropdownMenuItem>
                    )}
                    <DropdownMenuItem onClick={() => navigate('/settings')} className="rounded-xl px-3 py-2 gap-2 cursor-pointer focus:bg-primary focus:text-primary-foreground transition-colors">
                      <UserIcon className="h-3.5 w-3.5" />
                      <span className="font-bold text-xs">{t('layout:userMenu.personalSettings')}</span>
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
          <div className={cn(
            "flex-1 w-full relative",
            (isMobileImmersivePage || isMobileStudyPage)
              ? "px-0 py-0 h-full overflow-hidden"
              : isMobileVideoPage
                ? "px-0 py-4"
                : !isFullPage && "px-4 py-4 md:px-8 md:py-6"
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
          <div className="grid grid-cols-5 gap-1 px-2 py-2">
            {visibleMobileNavItems.map((item) => {
              const active =
                item.to === '/articles'
                  ? location.pathname === '/articles' || location.pathname.startsWith('/article/')
                  : location.pathname === item.to || location.pathname.startsWith(`${item.to}/`);
              const restricted = Boolean((item as any).minPlan && !atLeast((item as any).minPlan));
              return (
                <button
                  key={item.to}
                  onClick={() => {
                    if (restricted) {
                      handleRestrictedClick(item);
                      return;
                    }
                    navigate(item.to);
                  }}
                  className={cn(
                    "h-14 rounded-xl flex flex-col items-center justify-center gap-1 transition-colors",
                    active ? "bg-white shadow-sm border border-border text-foreground" : "text-muted-foreground"
                  )}
                >
                  <item.icon className="h-4 w-4" />
                  <span className="text-[10px] font-bold">{item.label}</span>
                </button>
              );
            })}
          </div>
        </nav>

        {/* 激活会员弹窗 */}
        <Dialog open={showActivateDialog} onOpenChange={setShowActivateDialog}>
          <DialogContent className="sm:max-w-[450px] rounded-[2.5rem] border-none shadow-2xl bg-card p-10">
            <DialogHeader className="space-y-3">
              <div className="h-12 w-12 rounded-2xl bg-amber-50 text-amber-600 flex items-center justify-center mb-2 shadow-inner">
                <Sparkles className="h-6 w-6" />
              </div>
              <DialogTitle className="text-2xl font-black tracking-tight uppercase">{t('layout:activation.title')}</DialogTitle>
              <DialogDescription className="font-medium text-muted-foreground leading-relaxed">
                {t('layout:activation.description')}
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-6 pt-6">
              <div className="space-y-2">
                <Label className="text-[10px] font-black uppercase tracking-widest text-muted-foreground ml-1">{t('layout:activation.codeLabel')}</Label>
                <Input
                  value={activationCode}
                  onChange={(e) => setActivationCode(e.target.value)}
                  placeholder={t('layout:activation.codePlaceholder')}
                  className="h-14 rounded-2xl bg-muted/50 border-none font-mono font-bold text-center text-lg tracking-wider focus-visible:ring-amber-500/20"
                />
              </div>
              <Button
                onClick={handleActivate}
                disabled={isActivating}
                className="w-full h-14 rounded-2xl bg-black text-white font-black shadow hover:opacity-90 active:scale-[0.98] transition-all uppercase tracking-widest text-xs"
              >
                {isActivating ? <Loader2 className="h-4 w-4 animate-spin" /> : t('layout:activation.activateButton')}
              </Button>
              <p className="text-center text-[10px] font-bold text-muted-foreground uppercase opacity-40">
                {t('layout:activation.footer')}
              </p>
            </div>
          </DialogContent>
        </Dialog>

        {!isInstStudent && (
          <UpgradeModal
            open={showUpgradeModal}
            onOpenChange={setShowUpgradeModal}
            feature={restrictedFeature}
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
              <AlertDialogAction onClick={() => { logout(); navigate('/login'); }} className="rounded-xl bg-primary text-primary-foreground font-bold hover:opacity-90">{t('layout:logout.confirm')}</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        <OnboardingDialog />
        <PersistentUploadToast />
      </div>
    </TooltipProvider>
  );
};
