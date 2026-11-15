import { LanguageSelect } from '@/components/LanguageSelect';
import { t, useLocale } from '@/i18n';
import { SelectField, SelectOption } from '@/components/ui/select';
import { DesktopSettings } from '@/components/DesktopSettings';
import { ThemeSceneSwitch } from '@/components/settings/ThemeSceneSwitch';
import { APP_VERSION, APP_BUILD } from '@/constants/version';
import { useDesktopStore } from '@/lib/desktop';
import NoteAISettings from './notes/NoteAISettings';
import { formatApiErrorToast } from '@/lib/apiError';
import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { useAuthStore } from '@/store/useAuthStore';
import { useSystemStore, DEFAULT_EXPERIENCE, type ExperiencePreferences } from '@/store/useSystemStore';
import { ArrowCounterClockwise, FloppyDisk, CreditCard, ArrowRight, MagnifyingGlass, UserCircle, Palette, Notebook, ShieldCheck, Database, DownloadSimple, Desktop, ChatCircle, GraduationCap } from '@phosphor-icons/react';
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel } from '@/components/ui/alert-dialog';
import api from '@/lib/api';
import { queryClient } from '@/lib/queryClient';
import { Link, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import '@/styles/settings.css';

const SECTIONS = [
  { id: 'desktop', label: '桌面应用', icon: Desktop, keywords: '通知 后台 托盘 离线 下载 快捷键 更新 版本' },
  { id: 'profile', label: '个人资料', icon: UserCircle, keywords: '昵称 简介 头像 风格 账号' },
  { id: 'appearance', label: '外观与阅读', icon: Palette, keywords: '主题 浅色 深色 系统 界面 字号 密度 动效 语言' },
  { id: 'chat', label: '对话与操作', icon: ChatCircle, keywords: '发送 Enter 快捷键 工具 过程 折叠 展开' },
  { id: 'learning', label: '学习与播放', icon: GraduationCap, keywords: '练习 题量 新题 复习 课程 倍速 字幕' },
  { id: 'notes', label: '笔记与小宇', icon: Notebook, keywords: 'AI 阅读 笔记 了解' },
  { id: 'security', label: '账户安全', icon: ShieldCheck, keywords: '邮箱 密码 修改' },
  { id: 'data', label: '数据管理', icon: Database, keywords: '导出 下载 注销 删除 隐私 协议' },
  { id: 'about', label: '关于 UniMind', icon: ChatCircle, keywords: '产品 客户端 版本 构建 关于' },
] as const;
const AVATAR_STYLES: Record<string, string> = {
  avataaars: '简约角色', bottts: '机器人', 'pixel-art': '像素艺术', adventurer: '冒险家',
  'big-smile': '大笑脸', micah: '扁平化', lorelei: '手绘风格', notionists: '极简主义',
};

export const Settings: React.FC = () => {
  useLocale();
  const locale = useLocale();
  const { theme, setTheme, setPageHeader, readingSize, density, reduceMotion, sendShortcut, toolDetails, practiceCount, practicePreference, videoSpeed, videoSubtitles, setExperience } = useSystemStore();
  const user = useAuthStore(state => state.user);
  const desktopState = useDesktopStore(state => state.state);
  const updateUser = useAuthStore(state => state.updateUser);
  const [params, setParams] = useSearchParams();
  const section = params.get('section') || 'profile';
  const setSection = (value: string) => setParams({ section: value }, { replace: true });
  const [query, setQuery] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [profile, setProfile] = useState({ nickname: user?.nickname || user?.username || '', bio: user?.bio || '' });
  const [avatar, setAvatar] = useState({ style: user?.avatar_style || 'avataaars', seed: user?.avatar_seed || user?.username || '' });
  const [email, setEmail] = useState('');
  const [passwords, setPasswords] = useState({ old: '', new: '' });
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deletePassword, setDeletePassword] = useState('');
  const contentRef = useRef<HTMLElement>(null);
  const deleteTriggerRef = useRef<HTMLButtonElement>(null);
  const filtered = SECTIONS.filter(item => item.id !== 'desktop' || !!window.unimindDesktop).filter(item => `${t(item.label)} ${t(item.keywords)} ${item.keywords}`.toLowerCase().includes(query.trim().toLowerCase()));
  const current = filtered.find(item => item.id === section) || filtered[0];
  const previewUrl = `https://api.dicebear.com/7.x/${avatar.style}/svg?seed=${encodeURIComponent(avatar.seed)}`;

  useEffect(() => { setPageHeader(t('设置'), ''); return () => setPageHeader('', ''); }, [setPageHeader, locale]);
  useEffect(() => { contentRef.current?.scrollTo({ top: 0 }); }, [current?.id]);

  const handleSaveProfile = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setBusy('profile');
    try {
      const { data } = await api.patch('/users/me/update/', { ...profile, avatar_style: avatar.style, avatar_seed: avatar.seed });
      updateUser(data); toast.success(t('个人资料已保存'));
    } catch (error) { toast.error(formatApiErrorToast(error, t('个人资料保存失败，请重试。'))); }
    finally { setBusy(null); }
  };
  const handleUpdateEmail = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy || !email.trim()) return;
    setBusy('email');
    try {
      const { data } = await api.patch('/users/me/email/', { email: email.trim() });
      updateUser(data); toast.success(t('邮箱已更新')); setEmail('');
    } catch (error) { toast.error(formatApiErrorToast(error, t('邮箱更新失败，请重试。'))); }
    finally { setBusy(null); }
  };
  const handleUpdatePassword = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setBusy('password');
    try {
      await api.patch('/users/me/password/', { old_password: passwords.old, new_password: passwords.new });
      toast.success(t('密码已更新')); setPasswords({ old: '', new: '' });
    } catch (error) { toast.error(formatApiErrorToast(error, t('密码更新失败，请核对后重试。'))); }
    finally { setBusy(null); }
  };
  const exportData = async () => {
    if (busy) return;
    setBusy('export');
    try {
      const { data } = await api.get('/users/me/data-export/', { responseType: 'blob' });
      const url = URL.createObjectURL(data);
      const link = document.createElement('a'); link.href = url; link.download = 'unimind_data_export.json'; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 0);
      toast.success(t('数据已导出'));
    } catch (error) { toast.error(formatApiErrorToast(error, t('导出失败，请重试。'))); }
    finally { setBusy(null); }
  };
  const deleteAccount = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy || !deletePassword) return;
    setBusy('delete');
    try {
      await api.post('/users/me/delete/', { password: deletePassword });
      await queryClient.cancelQueries(); queryClient.clear(); useAuthStore.getState().logout();
      window.location.href = '/';
    } catch (error) { toast.error(formatApiErrorToast(error, t('注销失败，请核对密码后重试。'))); }
    finally { setBusy(null); }
  };

  return <div className="um-settings-workspace">
    <aside className="um-settings-sidebar" aria-label={t('设置目录')}>
      <h1>{t('设置')}</h1>
      <label className="um-settings-search"><MagnifyingGlass size={17} aria-hidden="true" /><input aria-label={t('搜索设置')} placeholder={t('搜索设置')} value={query} onChange={event => setQuery(event.target.value)} /></label>
      <p className="um-settings-nav-label">{t('个人')}</p>
      <nav aria-label={t('个人设置分类')}>{filtered.map(item => <button key={item.id} type="button" aria-current={current?.id === item.id ? 'page' : undefined} aria-controls="settings-content" onClick={() => setSection(item.id)}><item.icon size={19} aria-hidden="true" />{t(item.label)}</button>)}</nav>
      <Link to="/billing" className="um-settings-service"><CreditCard size={19} aria-hidden="true" /><span>{t('我的服务')}</span><ArrowRight size={15} aria-hidden="true" /></Link>
    </aside>
    <main ref={contentRef} className="um-settings-content" id="settings-content" aria-labelledby="settings-section-title">
      <div className="um-settings-reading">
        <header className="um-settings-heading"><h2 id="settings-section-title">{t(current?.label || "搜索设置")}</h2></header>
        {!current && <div className="um-settings-empty"><p>{t('没有找到匹配的设置。')}</p><button type="button" onClick={() => setQuery('')}>{t('清除搜索')}</button></div>}
        {current?.id === 'desktop' && <DesktopSettings />}
        {current?.id === 'profile' && <form onSubmit={event => void handleSaveProfile(event)}>
          <h3 className="um-settings-group-title">{t('个人信息')}</h3>
          <section className="um-settings-group" aria-label={t('个人信息')}>
            <div className="um-settings-row um-settings-profile-summary"><Avatar className="h-14 w-14"><AvatarImage src={previewUrl} alt={t('头像预览')} /><AvatarFallback>{(profile.nickname || user?.username || '?')[0]}</AvatarFallback></Avatar><div><strong>{user?.nickname || user?.username}</strong><p>ELO {user?.elo_score ?? 0}</p></div></div>
            <div className="um-settings-row"><div><label htmlFor="settings-nickname">{t('昵称')}</label></div><Input id="settings-nickname" value={profile.nickname} onChange={event => setProfile({ ...profile, nickname: event.target.value })} autoComplete="nickname" /></div>
            <div className="um-settings-row"><div><span>{t('登录账号')}</span></div><span className="um-settings-value">{user?.username}</span></div>
            <div className="um-settings-row um-settings-row-top"><div><label htmlFor="settings-bio">{t('个人简介')}</label></div><textarea id="settings-bio" value={profile.bio} onChange={event => setProfile({ ...profile, bio: event.target.value })} rows={4} placeholder={t('写下你的学习目标与兴趣…')} /></div>
          </section>
          <h3 className="um-settings-group-title">{t('头像')}</h3>
          <section className="um-settings-group" aria-label={t('头像设置')}>
            <div className="um-settings-row"><label htmlFor="settings-avatar-style">{t('头像风格')}</label><SelectField id="settings-avatar-style" value={avatar.style} onValueChange={value => setAvatar({ ...avatar, style: value })}>{Object.entries(AVATAR_STYLES).map(([id, label]) => <SelectOption key={id} value={id}>{label}</SelectOption>)}</SelectField></div>
            <div className="um-settings-row"><div><label htmlFor="settings-avatar-seed">{t('头像特征')}</label></div><div className="um-settings-control"><Input id="settings-avatar-seed" value={avatar.seed} onChange={event => setAvatar({ ...avatar, seed: event.target.value })} /><button type="button" className="um-settings-icon-button" aria-label={t('随机生成头像')} onClick={() => setAvatar({ ...avatar, seed: Math.random().toString(36).substring(7) })}><ArrowCounterClockwise size={17} /></button></div></div>
          </section>
          <footer className="um-settings-footer"><Button type="submit" disabled={!!busy}><FloppyDisk size={16} />{busy === 'profile' ? t('保存中…') : t('保存个人资料')}</Button></footer>
        </form>}
        {current?.id === 'appearance' && <>
          <section className="um-settings-group"><div className="um-settings-row"><LanguageSelect /></div></section>
          <section className="um-settings-appearance" aria-labelledby="settings-appearance">
            <div><h3 id="settings-appearance">{t('界面外观')}</h3></div>
            <ThemeSceneSwitch value={theme} onChange={setTheme} reduceMotion={reduceMotion} />
          </section>
          <h3 className="um-settings-group-title">{t('阅读与显示')}</h3>
          <section className="um-settings-group">
            <div className="um-settings-row"><div><label htmlFor="settings-reading-size">{t('阅读字号')}</label></div><SelectField id="settings-reading-size" value={readingSize} onValueChange={value => setExperience({ readingSize: value as ExperiencePreferences['readingSize'] })}><SelectOption value="standard">{t('标准')}</SelectOption><SelectOption value="large">{t('较大')}</SelectOption><SelectOption value="larger">{t('更大')}</SelectOption></SelectField></div>
            <div className="um-settings-row"><div><label htmlFor="settings-density">{t('列表密度')}</label></div><SelectField id="settings-density" value={density} onValueChange={value => setExperience({ density: value as ExperiencePreferences['density'] })}><SelectOption value="standard">{t('标准')}</SelectOption><SelectOption value="compact">{t('紧凑')}</SelectOption></SelectField></div>
            <div className="um-settings-row"><div><label htmlFor="settings-reduce-motion">{t('减少界面动效')}</label></div><Switch id="settings-reduce-motion" checked={reduceMotion} onCheckedChange={value => setExperience({ reduceMotion: value })} /></div>
          </section>
          <footer className="um-settings-footer"><Button type="button" variant="outline" onClick={() => { setTheme('system'); setExperience({ readingSize: DEFAULT_EXPERIENCE.readingSize, density: DEFAULT_EXPERIENCE.density, reduceMotion: DEFAULT_EXPERIENCE.reduceMotion }); toast.success(t('已恢复外观默认设置')); }}><ArrowCounterClockwise size={16} />{t('恢复外观默认')}</Button></footer>
        </>}
        {current?.id === 'chat' && <>
          <h3 className="um-settings-group-title">{t('输入与过程')}</h3>
          <section className="um-settings-group">
            <div className="um-settings-row"><div><label htmlFor="settings-send-shortcut">{t('发送消息')}</label></div><SelectField id="settings-send-shortcut" value={sendShortcut} onValueChange={value => setExperience({ sendShortcut: value as ExperiencePreferences['sendShortcut'] })}><SelectOption value="enter">{t('Enter 发送')}</SelectOption><SelectOption value="modifier-enter">{t('⌘ / Ctrl+Enter 发送')}</SelectOption></SelectField></div>
            <div className="um-settings-row"><div><label htmlFor="settings-tool-details">{t('工具过程')}</label></div><SelectField id="settings-tool-details" value={toolDetails} onValueChange={value => setExperience({ toolDetails: value as ExperiencePreferences['toolDetails'] })}><SelectOption value="auto">{t('完成后自动折叠')}</SelectOption><SelectOption value="expanded">{t('默认保持展开')}</SelectOption></SelectField></div>
          </section>
          <footer className="um-settings-footer"><Button type="button" variant="outline" onClick={() => { setExperience({ sendShortcut: DEFAULT_EXPERIENCE.sendShortcut, toolDetails: DEFAULT_EXPERIENCE.toolDetails }); toast.success(t('已恢复对话默认设置')); }}><ArrowCounterClockwise size={16} />{t('恢复对话默认')}</Button></footer>
        </>}
        {current?.id === 'learning' && <>
          <h3 className="um-settings-group-title">{t('练习')}</h3>
          <section className="um-settings-group">
            <div className="um-settings-row"><div><label htmlFor="settings-practice-count">{t('默认题量')}</label></div><SelectField id="settings-practice-count" value={practiceCount} onValueChange={value => setExperience({ practiceCount: value as ExperiencePreferences['practiceCount'] })}><SelectOption value="recommended">{t('按学习情况推荐')}</SelectOption><SelectOption value="5">{t('5 题')}</SelectOption><SelectOption value="10">{t('10 题')}</SelectOption><SelectOption value="20">{t('20 题')}</SelectOption></SelectField></div>
            <div className="um-settings-row"><div><label htmlFor="settings-practice-preference">{t('选题偏好')}</label></div><SelectField id="settings-practice-preference" value={practicePreference} onValueChange={value => setExperience({ practicePreference: value as ExperiencePreferences['practicePreference'] })}><SelectOption value="balanced">{t('均衡')}</SelectOption><SelectOption value="new_first">{t('偏新题')}</SelectOption><SelectOption value="review_first">{t('偏复习')}</SelectOption></SelectField></div>
          </section>
          <h3 className="um-settings-group-title">{t('在线课程播放')}</h3>
          <section className="um-settings-group">
            <div className="um-settings-row"><div><label htmlFor="settings-video-speed">{t('默认倍速')}</label></div><SelectField id="settings-video-speed" value={videoSpeed} onValueChange={value => setExperience({ videoSpeed: Number(value) as ExperiencePreferences['videoSpeed'] })}><SelectOption value="1">1x</SelectOption><SelectOption value="1.25">1.25x</SelectOption><SelectOption value="1.5">1.5x</SelectOption><SelectOption value="2">2x</SelectOption></SelectField></div>
            <div className="um-settings-row"><div><label htmlFor="settings-video-subtitles">{t('默认显示字幕')}</label></div><Switch id="settings-video-subtitles" checked={videoSubtitles} onCheckedChange={value => setExperience({ videoSubtitles: value })} /></div>
          </section>
          <footer className="um-settings-footer"><Button type="button" variant="outline" onClick={() => { setExperience({ practiceCount: DEFAULT_EXPERIENCE.practiceCount, practicePreference: DEFAULT_EXPERIENCE.practicePreference, videoSpeed: DEFAULT_EXPERIENCE.videoSpeed, videoSubtitles: DEFAULT_EXPERIENCE.videoSubtitles }); toast.success(t('已恢复学习默认设置')); }}><ArrowCounterClockwise size={16} />{t('恢复学习默认')}</Button></footer>
        </>}
        {current?.id === 'notes' && <>
          <h3 className="um-settings-group-title">{t('笔记参考')}</h3>
          <section className="um-settings-group"><div className="um-settings-note-ai"><NoteAISettings /></div></section>
        </>}
        {current?.id === 'security' && <>
          <form onSubmit={event => void handleUpdateEmail(event)}><h3 className="um-settings-group-title">{t('邮箱')}</h3><section className="um-settings-group"><div className="um-settings-row"><div><label htmlFor="settings-email">{t('修改邮箱')}</label></div><Input id="settings-email" type="email" value={email} required onChange={event => setEmail(event.target.value)} placeholder={t('新邮箱地址')} autoComplete="email" spellCheck={false} /></div></section><footer className="um-settings-footer"><Button type="submit" variant="outline" disabled={!!busy || !email.trim()}>{busy === 'email' ? t('更新中…') : t('更新邮箱')}</Button></footer></form>
          <form onSubmit={event => void handleUpdatePassword(event)}><h3 className="um-settings-group-title">{t('密码')}</h3><section className="um-settings-group"><div className="um-settings-row"><label htmlFor="settings-old-password">{t('当前密码')}</label><Input id="settings-old-password" type="password" value={passwords.old} onChange={event => setPasswords({ ...passwords, old: event.target.value })} required autoComplete="current-password" /></div><div className="um-settings-row"><div><label htmlFor="settings-new-password">{t('新密码')}</label></div><Input id="settings-new-password" type="password" value={passwords.new} onChange={event => setPasswords({ ...passwords, new: event.target.value })} required minLength={6} autoComplete="new-password" /></div></section><footer className="um-settings-footer"><Button type="submit" variant="outline" disabled={!!busy || !passwords.old || passwords.new.length < 6}>{busy === 'password' ? t('更新中…') : t('更新密码')}</Button></footer></form>
        </>}
        {current?.id === 'about' && <>
          <h3 className="um-settings-group-title">{t('版本信息')}</h3>
          <section className="um-settings-group" aria-label={t('版本信息')}>
            <div className="um-settings-row"><span>{t('产品版本')}</span><span className="um-settings-value">{APP_VERSION}</span></div>
            {!!window.unimindDesktop && <div className="um-settings-row"><div><span>{t('客户端版本')}</span></div><span className="um-settings-value">{desktopState?.version || t('正在读取…')}</span></div>}
            <div className="um-settings-row"><details><summary>{t('技术详情')}</summary><p>{t('产品构建：')}{APP_BUILD}</p></details></div>
          </section>
        </>}
        {current?.id === 'data' && <>
          <h3 className="um-settings-group-title">{t('导出与保留')}</h3><section className="um-settings-group"><div className="um-settings-row"><div><span>{t('导出个人数据')}</span></div><Button type="button" variant="outline" disabled={!!busy} onClick={() => void exportData()}><DownloadSimple size={16} />{busy === 'export' ? t('导出中…') : t('下载我的数据')}</Button></div></section>
          <h3 className="um-settings-group-title">{t('账户注销')}</h3><section className="um-settings-group"><div className="um-settings-row"><div><span>{t('注销账户')}</span></div><Button type="button" variant="outline" className="um-settings-danger" ref={deleteTriggerRef} disabled={!!busy} onClick={() => setDeleteOpen(true)}>{t('注销账户')}</Button></div></section>
          <div className="um-settings-legal"><Link to="/privacy">{t('隐私政策')}</Link><Link to="/terms">{t('用户协议')}</Link></div>
        </>}
      </div>
    </main>
    <AlertDialog open={deleteOpen} onOpenChange={open => { if (busy === 'delete') return; setDeleteOpen(open); if (!open) setDeletePassword(''); }}><AlertDialogContent onCloseAutoFocus={event => { event.preventDefault(); deleteTriggerRef.current?.focus(); }}><form onSubmit={event => void deleteAccount(event)}><AlertDialogHeader><AlertDialogTitle>{t('确认注销账户？')}</AlertDialogTitle><AlertDialogDescription>{t('账户和数据删除后无法恢复。请先导出需要保留的数据，再输入当前密码确认。')}</AlertDialogDescription></AlertDialogHeader><label className="um-settings-delete-password" htmlFor="settings-delete-password">{t('当前密码')}<Input id="settings-delete-password" type="password" value={deletePassword} onChange={event => setDeletePassword(event.target.value)} required autoComplete="current-password" /></label><AlertDialogFooter><AlertDialogCancel type="button" disabled={busy === 'delete'}>{t('取消')}</AlertDialogCancel><Button type="submit" variant="destructive" disabled={!!busy || !deletePassword}>{busy === 'delete' ? t('正在注销…') : t('确认注销账户')}</Button></AlertDialogFooter></form></AlertDialogContent></AlertDialog>
  </div>;
};
