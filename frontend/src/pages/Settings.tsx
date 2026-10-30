import { DesktopSettings } from '@/components/DesktopSettings';
import NoteAISettings from './notes/NoteAISettings';
import { formatApiErrorToast } from '@/lib/apiError';
import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { useAuthStore } from '@/store/useAuthStore';
import { useSystemStore } from '@/store/useSystemStore';
import { ArrowCounterClockwise, FloppyDisk, CreditCard, ArrowRight, MagnifyingGlass, UserCircle, Palette, Notebook, ShieldCheck, Database, DownloadSimple, Desktop } from '@phosphor-icons/react';
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel } from '@/components/ui/alert-dialog';
import api from '@/lib/api';
import { queryClient } from '@/lib/queryClient';
import { Link, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import '@/styles/settings.css';

const SECTIONS = [
  { id: 'desktop', label: '桌面应用', icon: Desktop, keywords: '通知 后台 托盘 离线 下载 快捷键 更新 版本' },
  { id: 'profile', label: '个人资料', icon: UserCircle, keywords: '昵称 简介 头像 风格 账号' },
  { id: 'appearance', label: '外观', icon: Palette, keywords: '主题 浅色 深色 界面' },
  { id: 'notes', label: '笔记与小宇', icon: Notebook, keywords: 'AI 阅读 笔记 了解' },
  { id: 'security', label: '账户安全', icon: ShieldCheck, keywords: '邮箱 密码 修改' },
  { id: 'data', label: '数据管理', icon: Database, keywords: '导出 下载 注销 删除 隐私 协议' },
] as const;
const AVATAR_STYLES: Record<string, string> = {
  avataaars: '简约角色', bottts: '机器人', 'pixel-art': '像素艺术', adventurer: '冒险家',
  'big-smile': '大笑脸', micah: '扁平化', lorelei: '手绘风格', notionists: '极简主义',
};

export const Settings: React.FC = () => {
  const theme = useSystemStore(state => state.theme);
  const setTheme = useSystemStore(state => state.setTheme);
  const setPageHeader = useSystemStore(state => state.setPageHeader);
  const user = useAuthStore(state => state.user);
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
  const filtered = SECTIONS.filter(item => item.id !== 'desktop' || !!window.unimindDesktop).filter(item => `${item.label} ${item.keywords}`.includes(query.trim()));
  const current = filtered.find(item => item.id === section) || filtered[0];
  const previewUrl = `https://api.dicebear.com/7.x/${avatar.style}/svg?seed=${encodeURIComponent(avatar.seed)}`;

  useEffect(() => { setPageHeader('设置', ''); return () => setPageHeader('', ''); }, [setPageHeader]);
  useEffect(() => { contentRef.current?.scrollTo({ top: 0 }); }, [current?.id]);

  const handleSaveProfile = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setBusy('profile');
    try {
      const { data } = await api.patch('/users/me/update/', { ...profile, avatar_style: avatar.style, avatar_seed: avatar.seed });
      updateUser(data); toast.success('个人资料已保存');
    } catch (error) { toast.error(formatApiErrorToast(error, '个人资料保存失败，请重试。')); }
    finally { setBusy(null); }
  };
  const handleUpdateEmail = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy || !email.trim()) return;
    setBusy('email');
    try {
      const { data } = await api.patch('/users/me/email/', { email: email.trim() });
      updateUser(data); toast.success('邮箱已更新'); setEmail('');
    } catch (error) { toast.error(formatApiErrorToast(error, '邮箱更新失败，请重试。')); }
    finally { setBusy(null); }
  };
  const handleUpdatePassword = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setBusy('password');
    try {
      await api.patch('/users/me/password/', { old_password: passwords.old, new_password: passwords.new });
      toast.success('密码已更新'); setPasswords({ old: '', new: '' });
    } catch (error) { toast.error(formatApiErrorToast(error, '密码更新失败，请核对后重试。')); }
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
      toast.success('数据已导出');
    } catch (error) { toast.error(formatApiErrorToast(error, '导出失败，请重试。')); }
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
    } catch (error) { toast.error(formatApiErrorToast(error, '注销失败，请核对密码后重试。')); }
    finally { setBusy(null); }
  };

  return <div className="um-settings-workspace">
    <aside className="um-settings-sidebar" aria-label="设置目录">
      <h1>设置</h1>
      <label className="um-settings-search"><MagnifyingGlass size={17} aria-hidden="true" /><input aria-label="搜索设置" placeholder="搜索设置" value={query} onChange={event => setQuery(event.target.value)} /></label>
      <p className="um-settings-nav-label">个人</p>
      <nav aria-label="个人设置分类">{filtered.map(item => <button key={item.id} type="button" aria-current={current?.id === item.id ? 'page' : undefined} aria-controls="settings-content" onClick={() => setSection(item.id)}><item.icon size={19} aria-hidden="true" />{item.label}</button>)}</nav>
      <Link to="/billing" className="um-settings-service"><CreditCard size={19} aria-hidden="true" /><span>我的服务</span><ArrowRight size={15} aria-hidden="true" /></Link>
    </aside>
    <main ref={contentRef} className="um-settings-content" id="settings-content" aria-labelledby="settings-section-title">
      <div className="um-settings-reading">
        <header className="um-settings-heading"><h2 id="settings-section-title">{current?.label || '搜索设置'}</h2></header>
        {!current && <div className="um-settings-empty"><p>没有找到匹配的设置。</p><button type="button" onClick={() => setQuery('')}>清除搜索</button></div>}
        {current?.id === 'desktop' && <DesktopSettings />}
        {current?.id === 'profile' && <form onSubmit={event => void handleSaveProfile(event)}>
          <h3 className="um-settings-group-title">个人信息</h3>
          <section className="um-settings-group" aria-label="个人信息">
            <div className="um-settings-row um-settings-profile-summary"><Avatar className="h-14 w-14"><AvatarImage src={previewUrl} alt="头像预览" /><AvatarFallback>{(profile.nickname || user?.username || '?')[0]}</AvatarFallback></Avatar><div><strong>{user?.nickname || user?.username}</strong><p>ELO {user?.elo_score ?? 0}</p></div></div>
            <div className="um-settings-row"><div><label htmlFor="settings-nickname">昵称</label><p>在个人资料和交流中公开显示。</p></div><Input id="settings-nickname" value={profile.nickname} onChange={event => setProfile({ ...profile, nickname: event.target.value })} autoComplete="nickname" /></div>
            <div className="um-settings-row"><div><span>登录账号</span><p>当前账号名称不可修改。</p></div><span className="um-settings-value">{user?.username}</span></div>
            <div className="um-settings-row um-settings-row-top"><div><label htmlFor="settings-bio">个人简介</label><p>介绍自己，或记录正在学习的方向。</p></div><textarea id="settings-bio" value={profile.bio} onChange={event => setProfile({ ...profile, bio: event.target.value })} rows={4} placeholder="写下你的学习目标与兴趣…" /></div>
          </section>
          <h3 className="um-settings-group-title">头像</h3>
          <section className="um-settings-group" aria-label="头像设置">
            <div className="um-settings-row"><label htmlFor="settings-avatar-style">头像风格</label><select id="settings-avatar-style" value={avatar.style} onChange={event => setAvatar({ ...avatar, style: event.target.value })}>{Object.entries(AVATAR_STYLES).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select></div>
            <div className="um-settings-row"><div><label htmlFor="settings-avatar-seed">头像特征</label><p>修改文字或随机生成一个新头像。</p></div><div className="um-settings-control"><Input id="settings-avatar-seed" value={avatar.seed} onChange={event => setAvatar({ ...avatar, seed: event.target.value })} /><button type="button" className="um-settings-icon-button" aria-label="随机生成头像" onClick={() => setAvatar({ ...avatar, seed: Math.random().toString(36).substring(7) })}><ArrowCounterClockwise size={17} /></button></div></div>
          </section>
          <footer className="um-settings-footer"><Button type="submit" disabled={!!busy}><FloppyDisk size={16} />{busy === 'profile' ? '保存中…' : '保存个人资料'}</Button></footer>
        </form>}
        {current?.id === 'appearance' && <>
          <h3 className="um-settings-group-title">界面</h3>
          <section className="um-settings-group"><div className="um-settings-row"><div><label htmlFor="settings-appearance">界面外观</label><p>为当前客户端选择浅色或深色界面。</p></div><select id="settings-appearance" value={theme} onChange={event => setTheme(event.target.value as 'light' | 'dark')}><option value="light">浅色</option><option value="dark">深色</option></select></div></section>
        </>}
        {current?.id === 'notes' && <>
          <h3 className="um-settings-group-title">笔记参考</h3>
          <section className="um-settings-group"><div className="um-settings-note-intro"><p>开启后，小宇会了解你保存的笔记，用于你与小宇的交流。笔记仍由你编辑，小宇不会修改笔记。</p></div><div className="um-settings-note-ai"><NoteAISettings /></div></section>
        </>}
        {current?.id === 'security' && <>
          <form onSubmit={event => void handleUpdateEmail(event)}><h3 className="um-settings-group-title">邮箱</h3><section className="um-settings-group"><div className="um-settings-row"><div><label htmlFor="settings-email">修改邮箱</label><p>输入你要使用的新邮箱地址。</p></div><Input id="settings-email" type="email" value={email} required onChange={event => setEmail(event.target.value)} placeholder="新邮箱地址" autoComplete="email" spellCheck={false} /></div></section><footer className="um-settings-footer"><Button type="submit" variant="outline" disabled={!!busy || !email.trim()}>{busy === 'email' ? '更新中…' : '更新邮箱'}</Button></footer></form>
          <form onSubmit={event => void handleUpdatePassword(event)}><h3 className="um-settings-group-title">密码</h3><section className="um-settings-group"><div className="um-settings-row"><label htmlFor="settings-old-password">当前密码</label><Input id="settings-old-password" type="password" value={passwords.old} onChange={event => setPasswords({ ...passwords, old: event.target.value })} required autoComplete="current-password" /></div><div className="um-settings-row"><div><label htmlFor="settings-new-password">新密码</label><p>至少 6 个字符。</p></div><Input id="settings-new-password" type="password" value={passwords.new} onChange={event => setPasswords({ ...passwords, new: event.target.value })} required minLength={6} autoComplete="new-password" /></div></section><footer className="um-settings-footer"><Button type="submit" variant="outline" disabled={!!busy || !passwords.old || passwords.new.length < 6}>{busy === 'password' ? '更新中…' : '更新密码'}</Button></footer></form>
        </>}
        {current?.id === 'data' && <>
          <h3 className="um-settings-group-title">导出与保留</h3><section className="um-settings-group"><div className="um-settings-row"><div><span>导出个人数据</span><p>下载学习记录、答题历史等个人数据，格式为 JSON。</p></div><Button type="button" variant="outline" disabled={!!busy} onClick={() => void exportData()}><DownloadSimple size={16} />{busy === 'export' ? '导出中…' : '下载我的数据'}</Button></div></section>
          <h3 className="um-settings-group-title">账户注销</h3><section className="um-settings-group"><div className="um-settings-row"><div><span>注销账户</span><p>注销后无法恢复，请先导出需要保留的数据。</p></div><Button type="button" variant="outline" className="um-settings-danger" ref={deleteTriggerRef} disabled={!!busy} onClick={() => setDeleteOpen(true)}>注销账户</Button></div></section>
          <div className="um-settings-legal"><Link to="/privacy">隐私政策</Link><Link to="/terms">用户协议</Link></div>
        </>}
      </div>
    </main>
    <AlertDialog open={deleteOpen} onOpenChange={open => { if (busy === 'delete') return; setDeleteOpen(open); if (!open) setDeletePassword(''); }}><AlertDialogContent onCloseAutoFocus={event => { event.preventDefault(); deleteTriggerRef.current?.focus(); }}><form onSubmit={event => void deleteAccount(event)}><AlertDialogHeader><AlertDialogTitle>确认注销账户？</AlertDialogTitle><AlertDialogDescription>账户和数据删除后无法恢复。请先导出需要保留的数据，再输入当前密码确认。</AlertDialogDescription></AlertDialogHeader><label className="um-settings-delete-password" htmlFor="settings-delete-password">当前密码<Input id="settings-delete-password" type="password" value={deletePassword} onChange={event => setDeletePassword(event.target.value)} required autoComplete="current-password" /></label><AlertDialogFooter><AlertDialogCancel type="button" disabled={busy === 'delete'}>取消</AlertDialogCancel><Button type="submit" variant="destructive" disabled={!!busy || !deletePassword}>{busy === 'delete' ? '正在注销…' : '确认注销账户'}</Button></AlertDialogFooter></form></AlertDialogContent></AlertDialog>
  </div>;
};
