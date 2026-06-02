import { useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { useAuthStore } from '@/store/useAuthStore';
import {
  RefreshCcw, Save, Camera, CreditCard, ArrowRight
} from 'lucide-react';
import api from '@/lib/api';
import { Link } from 'react-router-dom';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Label } from "@/components/ui/label";
import { PageWrapper } from '@/components/PageWrapper';
import { toast } from "sonner";
import { useTranslation } from 'react-i18next';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const AVATAR_STYLE_IDS = ['avataaars', 'bottts', 'pixel-art', 'adventurer', 'big-smile', 'micah', 'lorelei', 'notionists'];

export const Settings: React.FC = () => {
  const { t } = useTranslation(['settings', 'common']);
  const { user, updateUser } = useAuthStore();
  const [loading, setLoading] = useState(false);

  // Profile
  const [profile, setProfile] = useState({
    nickname: user?.nickname || user?.username || '',
    bio: user?.bio || '',
  });

  // Avatar
  const [avatar, setAvatar] = useState({
    style: user?.avatar_style || 'avataaars',
    seed: user?.avatar_seed || user?.username || '',
  });

  // Security
  const [email, setEmail] = useState('');
  const [passwords, setPasswords] = useState({ old: '', new: '' });

  const previewUrl = `https://api.dicebear.com/7.x/${avatar.style}/svg?seed=${avatar.seed}`;

  const handleSaveProfile = async () => {
    setLoading(true);
    try {
      const res = await api.patch('/users/me/update/', {
        nickname: profile.nickname,
        bio: profile.bio,
        avatar_style: avatar.style,
        avatar_seed: avatar.seed
      });
      updateUser(res.data);
      toast.success(t('profile.saved'));
    } catch (err) { toast.error(t('common:failed')); }
    finally { setLoading(false); }
  };

  const handleUpdateEmail = async () => {
    if (!email) return toast.error(t('security.emailEmpty'));
    try {
      const res = await api.patch('/users/me/email/', { email });
      updateUser(res.data);
      toast.success(t('security.emailSaved'));
      setEmail('');
    } catch (e) { toast.error(t('common:failed')); }
  };

  const handleUpdatePassword = async () => {
    if (!passwords.old || !passwords.new) return toast.error(t('security.passwordEmpty'));
    if (passwords.new.length < 6) return toast.error(t('security.passwordTooShort', '密码至少需要 6 个字符'));
    try {
      await api.patch('/users/me/password/', { old_password: passwords.old, new_password: passwords.new });
      toast.success(t('security.passwordSaved'));
      setPasswords({ old: '', new: '' });
    } catch (e) { toast.error(t('security.passwordError')); }
  };

  return (
    <PageWrapper title={t('pageTitle')} subtitle={t('pageSubtitle')}>
      <div className="max-w-5xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-8 text-left animate-in fade-in duration-700">
        <div className="lg:col-span-4 space-y-6">
          <Card className="border-none shadow-sm rounded-3xl bg-white p-8 flex flex-col items-center text-center border border-black/[0.03]">
            <div className="relative group">
              <Avatar className="h-32 w-32 border-4 border-white shadow-lg ring-1 ring-black/5">
                <AvatarImage src={previewUrl} />
                <AvatarFallback className="text-4xl font-bold">{(profile.nickname || user?.username || "?")[0]}</AvatarFallback>
              </Avatar>
              <Sheet>
                <SheetTrigger asChild><button aria-label="Change avatar" className="absolute bottom-0 right-0 bg-black text-white p-2.5 rounded-full shadow-sm border-4 border-white transition-transform hover:scale-110"><Camera className="h-4 w-4" /></button></SheetTrigger>
                <SheetContent side="right" className="rounded-l-[2.5rem] border-none bg-white/95 backdrop-blur-2xl shadow-2xl w-[450px]">
                  <SheetHeader className="p-8 border-b border-black/[0.03]"><SheetTitle className="text-2xl font-bold text-left">{t('avatar.lab')}</SheetTitle></SheetHeader>
                  <div className="p-8 space-y-10">
                    <div className="flex justify-center py-10 bg-slate-50 rounded-[2rem]"><Avatar className="h-44 w-44 border-8 border-white shadow-lg"><AvatarImage src={previewUrl} /></Avatar></div>
                    <div className="space-y-6 text-left">
                      <div className="space-y-3"><Label className="text-xs font-bold uppercase tracking-widest opacity-40 ml-1">{t('avatar.styleLabel')}</Label>
                        <Select value={avatar.style} onValueChange={(v) => setAvatar({...avatar, style: v})}>
                          <SelectTrigger className="h-12 rounded-2xl bg-slate-50 border-none font-bold"><SelectValue /></SelectTrigger>
                          <SelectContent className="rounded-2xl border-none shadow-lg">
                            {AVATAR_STYLE_IDS.map(id => <SelectItem key={id} value={id} className="rounded-xl py-3 px-4"><div className="flex items-center gap-3 font-bold">{t(`avatar.styles.${id}` as any)}</div></SelectItem>)}
                          </SelectContent>
                        </Select></div>
                      <div className="space-y-3"><Label className="text-xs font-bold uppercase tracking-widest opacity-40 ml-1">{t('avatar.seedLabel')}</Label>
                        <div className="flex gap-3"><Input value={avatar.seed} onChange={e => setAvatar({ ...avatar, seed: e.target.value })} className="bg-slate-50 border-none h-12 rounded-2xl font-bold" /><Button variant="outline" onClick={() => setAvatar({...avatar, seed: Math.random().toString(36).substring(7)})} className="rounded-2xl h-12 w-12 border-black/5"><RefreshCcw className="h-4 w-4" /></Button></div></div>
                    </div>
                  </div>
                </SheetContent>
              </Sheet>
            </div>
            <h3 className="mt-6 text-xl font-bold text-foreground">{user?.nickname || user?.username}</h3>
            <p className="text-xs text-muted-foreground font-bold mt-1 uppercase tracking-widest leading-none text-emerald-600">{t('profile.eloRank', { score: user?.elo_score })}</p>
          </Card>

          <Card className="border-none shadow-sm rounded-3xl bg-white p-8 space-y-6 border border-black/[0.03]">
             <div className="space-y-6 text-left">
                <h4 className="text-[10px] font-bold uppercase tracking-widest opacity-40 ml-1">{t('security.title')}</h4>
                <div className="space-y-4">
                   <div className="space-y-2"><Label className="text-[10px] font-bold opacity-40 ml-1 uppercase">{t('security.emailLabel')}</Label><div className="flex gap-2"><Input value={email} onChange={e => setEmail(e.target.value)} placeholder={t('security.emailPlaceholder')} autoComplete="email" spellCheck={false} className="bg-unimind-bg-secondary border-none h-10 rounded-xl text-xs font-bold px-4" /><Button onClick={handleUpdateEmail} className="rounded-xl bg-black text-white h-10 px-4 text-[10px] font-bold uppercase tracking-widest">{t('security.emailUpdate')}</Button></div></div>
                   <div className="space-y-2 pt-2"><Label className="text-[10px] font-bold opacity-40 ml-1 uppercase">{t('security.passwordLabel')}</Label><Input type="password" value={passwords.old} onChange={e => setPasswords({...passwords, old: e.target.value})} placeholder={t('security.oldPassword')} autoComplete="current-password" spellCheck={false} className="bg-unimind-bg-secondary border-none h-10 rounded-xl text-xs font-bold px-4 mb-2" /><div className="flex gap-2"><Input type="password" value={passwords.new} onChange={e => setPasswords({...passwords, new: e.target.value})} placeholder={t('security.newPassword')} autoComplete="new-password" spellCheck={false} className="bg-unimind-bg-secondary border-none h-10 rounded-xl text-xs font-bold px-4 flex-1" /><Button onClick={handleUpdatePassword} className="rounded-xl bg-black text-white h-10 px-4 text-[10px] font-bold uppercase tracking-widest">{t('security.passwordReset')}</Button></div></div>
                </div>
             </div>
          </Card>

          <Link to="/billing" className="block">
            <Card className="border-none shadow-sm rounded-3xl bg-white p-8 border border-black/[0.03] text-left cursor-pointer hover:shadow-md motion-safe:transition-shadow">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-2xl bg-primary/10 flex items-center justify-center">
                    <CreditCard className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-foreground">方案与账单</h4>
                    <p className="text-[11px] text-muted-foreground font-medium">
                      {user?.is_member ? `当前方案：${user?.membership_tier || 'Free'}` : '升级解锁完整功能'}
                    </p>
                  </div>
                </div>
                <ArrowRight className="h-4 w-4 text-muted-foreground/40" />
              </div>
            </Card>
          </Link>

        </div>

        <div className="lg:col-span-8 space-y-8">
          <Card className="border-none shadow-sm rounded-3xl bg-white overflow-hidden p-10 border border-black/[0.03]">
             <div className="space-y-8 text-left">
               <div className="space-y-3">
                 <Label className="text-xs font-bold uppercase tracking-widest opacity-40 ml-1">{t('profile.nicknameLabel')}</Label>
                 <Input value={profile.nickname} onChange={e => setProfile({...profile, nickname: e.target.value})} className="bg-unimind-bg-secondary border-none h-12 rounded-2xl font-bold px-5" />
                 <p className="text-[10px] text-muted-foreground font-bold ml-1 uppercase">{t('profile.usernameNote', { username: user?.username })}</p>
               </div>
               <div className="space-y-3">
                 <Label className="text-xs font-bold uppercase tracking-widest opacity-40 ml-1">{t('profile.bioLabel')}</Label>
                 <textarea value={profile.bio} onChange={e => setProfile({...profile, bio: e.target.value})} className="w-full bg-unimind-bg-secondary border-none rounded-2xl p-6 min-h-[250px] focus:outline-none focus:ring-1 focus:ring-black/10 font-bold text-sm leading-relaxed" placeholder={t('profile.bioPlaceholder')} />
               </div>
               <Button onClick={handleSaveProfile} disabled={loading} className="w-full h-14 bg-black text-white rounded-2xl font-bold shadow transition-all hover:scale-[1.01]"><Save className="mr-2 h-4 w-4" /> {t('profile.saveProfile')}</Button>
             </div>
          </Card>

          {/* 数据导出 */}
          <Card className="border-none shadow-sm rounded-3xl bg-white p-8 border border-black/[0.03]">
            <div className="text-left space-y-3">
              <h4 className="text-xs font-bold uppercase tracking-widest opacity-40 ml-1">数据导出</h4>
              <p className="text-xs text-muted-foreground ml-1">导出您的所有个人数据（JSON 格式），包括学习记录、答题历史等。</p>
              <Button
                variant="outline"
                className="rounded-xl h-10 text-xs font-bold"
                onClick={async () => {
                  try {
                    const resp = await api.get('/users/me/data-export/', { responseType: 'blob' });
                    const url = URL.createObjectURL(resp.data);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `unimind_data_export.json`;
                    a.click();
                    URL.revokeObjectURL(url);
                    toast.success('数据导出成功');
                  } catch { toast.error('导出失败'); }
                }}
              >
                下载我的数据
              </Button>
            </div>
          </Card>

          {/* 账户注销 */}
          <Card className="border-none shadow-sm rounded-3xl bg-white p-8 border border-red-100">
            <div className="text-left space-y-3">
              <h4 className="text-xs font-bold uppercase tracking-widest text-red-500 ml-1">危险区域</h4>
              <p className="text-xs text-muted-foreground ml-1">注销账户将永久删除您的所有数据，此操作不可撤销。</p>
              <Button
                variant="destructive"
                className="rounded-xl h-10 text-xs font-bold"
                onClick={() => {
                  const pwd = prompt('请输入密码以确认注销：');
                  if (!pwd) return;
                  if (!confirm('确认注销账户？所有数据将被永久删除，此操作不可撤销。')) return;
                  api.post('/users/me/delete/', { password: pwd })
                    .then(() => { toast.success('账户已注销'); window.location.href = '/'; })
                    .catch(e => toast.error(e.response?.data?.error || '注销失败'));
                }}
              >
                注销账户
              </Button>
            </div>
          </Card>

          {/* 法律文档链接 */}
          <div className="flex gap-4 text-xs text-muted-foreground ml-1">
            <a href="/privacy" className="hover:text-foreground underline underline-offset-2">隐私政策</a>
            <a href="/terms" className="hover:text-foreground underline underline-offset-2">用户协议</a>
          </div>
        </div>
      </div>
    </PageWrapper>
  );
};
