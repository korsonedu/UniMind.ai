import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Buildings, ArrowRight, CheckCircle, Key, SpinnerGap } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel } from '@/components/ui/alert-dialog';
import api from '@/lib/api';
import { formatApiErrorToast } from '@/lib/apiError';
import { useWorkspace, syncWorkspace, workspacePath, serviceDate, type InvitePreview, type JoinedWorkspace } from '@/lib/workspace';
import { activeWorkspace, setActiveWorkspace } from '@/lib/activeWorkspace';
import '@/styles/institution-workspace.css';

export function WorkspacePreviewNotice() {
  if (!import.meta.env.DEV || sessionStorage.getItem('unimind-design-preview') !== '1') return null;
  return <div className="iw-preview"><span>交互预览 · 样例数据，未连接真实机构服务</span><div>{[['unjoined', '未加入'], ['student', '学生'], ['admin', '管理员']].map(([mode, label]) => <a key={mode} href={`/settings?section=institution&preview=1&workspace=${mode}`}>{label}</a>)}</div></div>;
}

export function InstitutionServices() {
  const { data, isPending, isError, refetch } = useWorkspace();
  const client = useQueryClient();
  const [code, setCode] = useState('');
  const [invite, setInvite] = useState<InvitePreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [leaving, setLeaving] = useState<JoinedWorkspace | null>(null);
  const [creating, setCreating] = useState(false);
  const [institutionName, setInstitutionName] = useState('');
  async function createInstitution(event: React.FormEvent) {
    event.preventDefault();
    if (busy || !institutionName.trim()) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await api.post(workspacePath, { name: institutionName.trim() });
      client.setQueriesData({ queryKey: ['workspace'] }, result.data);
      await client.invalidateQueries({ queryKey: ['workspace'] });
      setCreating(false); setInstitutionName(''); setNotice('机构已创建，你已成为该机构管理员。');
    } catch (err) { setError(formatApiErrorToast(err, '暂时无法创建机构，请稍后重试。')); }
    finally { setBusy(false); }
  }
  async function manageInstitution(id: number) {
    if (busy) return;
    setBusy(true); setError('');
    try {
      await api.post(`${workspacePath}select/`, { workspace_id: id });
      setActiveWorkspace(id);
      window.location.assign('/settings/institution');
    } catch (err) { setError(formatApiErrorToast(err, '暂时无法打开机构管理，请稍后重试。')); setBusy(false); }
  }
  async function changeWorkspace(action: 'switch' | 'leave', workspaceId: number) {
    if (busy) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await api.post(`${workspacePath}${action}/`, { workspace_id: workspaceId });
      await syncWorkspace(result.data);
      setLeaving(null); setInvite(null);
      setNotice(action === 'leave' ? '已退出机构，个人笔记和聊天记录已保留。' : '已切换机构，课程与学习服务已更新。');
    } catch (err) { setError(formatApiErrorToast(err, action === 'leave' ? '暂时无法退出机构，请稍后重试。' : '暂时无法切换机构，请稍后重试。')); setLeaving(null); }
    finally { setBusy(false); }
  }
  async function submit(confirm: boolean) {
    if (busy || !code.trim()) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const result = await api.post(`${workspacePath}${confirm ? 'join' : 'invite-preview'}/`, { code: code.trim() });
      if (confirm) { await syncWorkspace(result.data); setInvite(null); setCode(''); setNotice('已加入，课程与学习服务已开通。'); }
      else setInvite(result.data);
    } catch (err) { setError(formatApiErrorToast(err, '邀请码暂时无法使用，请核对后重试。')); }
    finally { setBusy(false); }
  }
  if (isPending) return <p className="iw-feedback" role="status"><SpinnerGap className="iw-spin" />正在读取机构与学习服务…</p>;
  if (isError || !data) return <div className="iw-feedback" role="alert"><p>暂时无法读取机构信息。</p><Button variant="outline" onClick={() => void refetch()}>重新加载</Button></div>;
  return <div className="iw-settings"><WorkspacePreviewNotice />
    {notice && <p className="iw-success" role="status"><CheckCircle size={18} weight="fill" />{notice}</p>}
    {data.enterprise && <section className="iw-joined-row"><Buildings size={22} /><div><h3>企业版</h3><p>{data.enterprise.can_create ? `服务至 ${serviceDate(data.enterprise.service_ends_at)} · 每家机构 ${data.enterprise.max_students} 个学生名额` : '企业服务已到期或暂停'}</p></div>{data.enterprise.can_create && <Button disabled={busy} onClick={() => { setError(''); setCreating(true); }}>创建机构</Button>}</section>}
    {[{ title: '我管理的机构', role: 'admin' }, { title: '已加入的机构', role: 'student' }].map(group => {
      const items = data.workspaces?.filter(item => item.role === group.role) || [];
      return !!items.length && <section className="iw-joined" key={group.role}><h3 className="um-settings-group-title">{group.title}</h3>{items.map(item => <div className="iw-joined-row" key={item.id}>
      <Buildings size={22} /><div><h3>{item.name}</h3><p>{item.role === 'admin' ? '管理员' : '学生'} · {item.service_active ? `服务至 ${serviceDate(item.service_ends_at)}` : '服务已暂停或到期'}</p></div>
      {activeWorkspace() === String(item.id) ? <span className="iw-tag">当前机构</span> : <Button size="sm" variant="outline" disabled={busy || !item.service_active} onClick={() => void changeWorkspace('switch', item.id)}>切换到此机构</Button>}
      {item.role === 'admin' && <Button size="sm" disabled={busy || !item.service_active} onClick={() => void manageInstitution(item.id)}>管理机构<ArrowRight size={16} /></Button>}
      <Button size="sm" variant="ghost" disabled={busy} onClick={() => setLeaving(item)} aria-label={`退出${item.name}`}>退出机构</Button>
    </div>)}</section>;
    })}
    {data.workspace ? <>
      <section className="iw-identity"><span className="iw-monogram">{data.workspace.name.slice(0, 1)}</span><div><span className="iw-eyebrow">当前机构</span><h3>{data.workspace.name}</h3><p>{data.workspace.description}</p></div><span className="iw-tag">{data.workspace.service_active === false ? '服务已暂停或到期' : data.role === 'admin' ? '管理员' : '已加入'}</span></section>
      <h3 className="um-settings-group-title">学习服务</h3><section className="um-settings-group"><div className="um-settings-row"><span>服务期限</span><span className="um-settings-value">至 {serviceDate(data.workspace.service_ends_at)}</span></div><div className="um-settings-row"><span>加入时间</span><span className="um-settings-value">{serviceDate(data.workspace.joined_at)}</span></div><div className="um-settings-row"><span>已开通课程</span><span className="um-settings-value">{data.courses.filter(c => c.status === 'published').length} 节</span></div></section>
      <div className="iw-enrolled-courses"><h3 className="um-settings-group-title">你的课程</h3>{data.courses.filter(c => c.status === 'published').map(course => <div className="iw-course-line" key={course.id}><span>{course.title}</span><span>{course.module} · {course.duration}</span></div>)}</div>
    </> : <>
      <section className="iw-join-intro"><span className="iw-join-icon"><Buildings size={30} weight="duotone" /></span><h3>连接你的机构学习服务</h3><p>使用机构提供的邀请码，开通课程和小宇伴学。<br />继续使用当前账号，已有学习记录会保留。</p></section>
    </>}
      {data.workspace && <h3 className="um-settings-group-title iw-add-title">加入其他机构</h3>}
      {!data.available ? <p className="iw-feedback" role="status">机构学习服务尚未开放，开放后可在这里输入邀请码加入。</p> : <form className="iw-join-form" onSubmit={e => { e.preventDefault(); void submit(false); }}><label htmlFor="institution-invite">机构邀请码</label><div><Input id="institution-invite" value={code} onChange={e => { setCode(e.target.value); setInvite(null); setError(''); }} placeholder="输入机构提供的邀请码" autoComplete="off" maxLength={80} disabled={busy} /><Button disabled={busy || !code.trim()} type="submit"><Key size={16} />{busy ? '正在验证…' : '验证邀请码'}</Button></div><p>加入前，你可以确认机构、课程和服务期限。</p>{data.demo && <small>预览邀请码：LEARN2027</small>}</form>}
      {invite && <section className="iw-invite-confirm" aria-label="确认加入机构"><span className="iw-eyebrow">请确认学习服务</span><h3>{invite.name}</h3><p>{invite.service}</p><ul>{invite.courses.map(title => <li key={title}><CheckCircle size={16} />{title}</li>)}</ul><p>服务至 {serviceDate(invite.service_ends_at)}</p><div><Button variant="outline" disabled={busy} onClick={() => setInvite(null)}>取消</Button><Button disabled={busy} onClick={() => void submit(true)}>{busy ? '正在加入…' : '确认加入'}</Button></div></section>}
      {error && <p className="iw-error" role="alert">{error}</p>}
      <Dialog open={creating} onOpenChange={open => { if (!busy) setCreating(open); }}><DialogContent><DialogHeader><DialogTitle>创建机构</DialogTitle><DialogDescription>创建后你将成为机构管理员，可以设置空间名称、上传课程并邀请学生加入。</DialogDescription></DialogHeader><form onSubmit={e => void createInstitution(e)}><label htmlFor="new-institution-name">机构名称</label><Input id="new-institution-name" value={institutionName} onChange={e => setInstitutionName(e.target.value)} maxLength={100} required disabled={busy} /><div className="iw-dialog-actions"><Button type="button" variant="outline" disabled={busy} onClick={() => setCreating(false)}>取消</Button><Button type="submit" disabled={busy || !institutionName.trim()}>{busy ? '正在创建…' : '确认创建'}</Button></div>{error && <p className="iw-error" role="alert">{error}</p>}</form></DialogContent></Dialog>
      <AlertDialog open={!!leaving} onOpenChange={open => { if (!open && !busy) setLeaving(null); }}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>退出{leaving?.name}？</AlertDialogTitle><AlertDialogDescription>退出后将失去这家机构的课程和学习服务，个人笔记与聊天记录会保留。重新加入需要有效邀请码，并重新领取课程授权。</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel disabled={busy}>取消</AlertDialogCancel><Button disabled={busy} onClick={() => leaving && void changeWorkspace('leave', leaving.id)}>{busy ? '正在退出…' : '确认退出'}</Button></AlertDialogFooter></AlertDialogContent></AlertDialog>
  </div>;
}
