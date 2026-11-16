import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Buildings, ArrowRight, CheckCircle, Key, SpinnerGap } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel } from '@/components/ui/alert-dialog';
import api from '@/lib/api';
import { formatApiErrorToast } from '@/lib/apiError';
import { useWorkspace, syncWorkspace, workspacePath, serviceDate, type InvitePreview, type JoinedWorkspace } from '@/lib/workspace';
import '@/styles/institution-workspace.css';

export function WorkspacePreviewNotice() {
  if (!import.meta.env.DEV || sessionStorage.getItem('unimind-design-preview') !== '1') return null;
  return <div className="iw-preview"><span>交互预览 · 样例数据，未连接真实机构服务</span><div>{[['unjoined', '未加入'], ['student', '学生'], ['admin', '管理员']].map(([mode, label]) => <a key={mode} href={`/settings?section=institution&preview=1&workspace=${mode}`}>{label}</a>)}</div></div>;
}

export function InstitutionServices() {
  const { data, isPending, isError, refetch } = useWorkspace();
  const [code, setCode] = useState('');
  const [invite, setInvite] = useState<InvitePreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [leaving, setLeaving] = useState<JoinedWorkspace | null>(null);
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
    {!!data.workspaces?.length && <section className="iw-joined"><h3 className="um-settings-group-title">已加入的机构</h3>{data.workspaces.map(item => <div className="iw-joined-row" key={item.id}>
      <Buildings size={22} /><div><h3>{item.name}</h3><p>{item.role === 'admin' ? '管理员' : '学生'} · {item.service_active ? `服务至 ${serviceDate(item.service_ends_at)}` : '服务已暂停或到期'}</p></div>
      {item.is_current ? <span className="iw-tag">当前机构</span> : <Button size="sm" variant="outline" disabled={busy} onClick={() => void changeWorkspace('switch', item.id)}>切换到此机构</Button>}
      <Button size="sm" variant="ghost" disabled={busy} onClick={() => setLeaving(item)} aria-label={`退出${item.name}`}>退出机构</Button>
    </div>)}</section>}
    {data.workspace ? <>
      <section className="iw-identity"><span className="iw-monogram">{data.workspace.name.slice(0, 1)}</span><div><span className="iw-eyebrow">当前机构</span><h3>{data.workspace.name}</h3><p>{data.workspace.description}</p></div><span className="iw-tag">{data.workspace.service_active === false ? '服务已暂停或到期' : data.role === 'admin' ? '管理员' : '已加入'}</span></section>
      <h3 className="um-settings-group-title">学习服务</h3><section className="um-settings-group"><div className="um-settings-row"><span>服务期限</span><span className="um-settings-value">至 {serviceDate(data.workspace.service_ends_at)}</span></div><div className="um-settings-row"><span>加入时间</span><span className="um-settings-value">{serviceDate(data.workspace.joined_at)}</span></div><div className="um-settings-row"><span>已开通课程</span><span className="um-settings-value">{data.courses.filter(c => c.status === 'published').length} 节</span></div></section>
      <div className="iw-enrolled-courses"><h3 className="um-settings-group-title">你的课程</h3>{data.courses.filter(c => c.status === 'published').map(course => <div className="iw-course-line" key={course.id}><span>{course.title}</span><span>{course.module} · {course.duration}</span></div>)}</div>
      {data.role === 'admin' && data.workspace.service_active !== false && <section className="iw-manage-entry"><Buildings size={24} /><div><h3>机构管理</h3><p>管理课程与知识结构、学生、邀请码和服务用量。</p></div><Button asChild><Link to="/settings/institution">管理机构<ArrowRight size={16} /></Link></Button></section>}
    </> : <>
      <section className="iw-join-intro"><span className="iw-join-icon"><Buildings size={30} weight="duotone" /></span><h3>连接你的机构学习服务</h3><p>使用机构提供的邀请码，开通课程和小宇伴学。<br />继续使用当前账号，已有学习记录会保留。</p></section>
    </>}
      {data.workspace && <h3 className="um-settings-group-title iw-add-title">加入其他机构</h3>}
      {!data.available ? <p className="iw-feedback" role="status">机构学习服务尚未开放，开放后可在这里输入邀请码加入。</p> : <form className="iw-join-form" onSubmit={e => { e.preventDefault(); void submit(false); }}><label htmlFor="institution-invite">机构邀请码</label><div><Input id="institution-invite" value={code} onChange={e => { setCode(e.target.value); setInvite(null); setError(''); }} placeholder="输入机构提供的邀请码" autoComplete="off" maxLength={80} disabled={busy} /><Button disabled={busy || !code.trim()} type="submit"><Key size={16} />{busy ? '正在验证…' : '验证邀请码'}</Button></div><p>加入前，你可以确认机构、课程和服务期限。</p>{data.demo && <small>预览邀请码：LEARN2027</small>}</form>}
      {invite && <section className="iw-invite-confirm" aria-label="确认加入机构"><span className="iw-eyebrow">请确认学习服务</span><h3>{invite.name}</h3><p>{invite.service}</p><ul>{invite.courses.map(title => <li key={title}><CheckCircle size={16} />{title}</li>)}</ul><p>服务至 {serviceDate(invite.service_ends_at)}</p><div><Button variant="outline" disabled={busy} onClick={() => setInvite(null)}>取消</Button><Button disabled={busy} onClick={() => void submit(true)}>{busy ? '正在加入…' : '确认加入'}</Button></div></section>}
      {error && <p className="iw-error" role="alert">{error}</p>}
      <AlertDialog open={!!leaving} onOpenChange={open => { if (!open && !busy) setLeaving(null); }}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>退出{leaving?.name}？</AlertDialogTitle><AlertDialogDescription>退出后将失去这家机构的课程和学习服务，个人笔记与聊天记录会保留。重新加入需要有效邀请码，并重新领取课程授权。</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel disabled={busy}>取消</AlertDialogCancel><Button disabled={busy} onClick={() => leaving && void changeWorkspace('leave', leaving.id)}>{busy ? '正在退出…' : '确认退出'}</Button></AlertDialogFooter></AlertDialogContent></AlertDialog>
  </div>;
}
