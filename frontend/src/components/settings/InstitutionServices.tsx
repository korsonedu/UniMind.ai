import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Buildings, ArrowRight, CheckCircle, Key, SpinnerGap } from '@phosphor-icons/react';
import { useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import api from '@/lib/api';
import { formatApiErrorToast } from '@/lib/apiError';
import { useWorkspace, workspacePath, serviceDate, type InvitePreview } from '@/lib/workspace';
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
  const [joined, setJoined] = useState(false);
  async function submit(confirm: boolean) {
    if (busy || !code.trim()) return;
    setBusy(true); setError('');
    try {
      const result = await api.post(`${workspacePath}${confirm ? 'join' : 'invite-preview'}/`, { code: code.trim() });
      if (confirm) { await client.invalidateQueries({ queryKey: ['workspace'] }); setInvite(null); setJoined(true); }
      else setInvite(result.data);
    } catch (err) { setError(formatApiErrorToast(err, '邀请码暂时无法使用，请核对后重试。')); }
    finally { setBusy(false); }
  }
  if (isPending) return <p className="iw-feedback" role="status"><SpinnerGap className="iw-spin" />正在读取机构与学习服务…</p>;
  if (isError || !data) return <div className="iw-feedback" role="alert"><p>暂时无法读取机构信息。</p><Button variant="outline" onClick={() => void refetch()}>重新加载</Button></div>;
  return <div className="iw-settings"><WorkspacePreviewNotice />
    {data.workspace ? <>
      {joined && <p className="iw-success" role="status"><CheckCircle size={18} weight="fill" />已加入，课程与学习服务已开通。</p>}
      <section className="iw-identity"><span className="iw-monogram">{data.workspace.name.slice(0, 1)}</span><div><span className="iw-eyebrow">当前机构</span><h3>{data.workspace.name}</h3><p>{data.workspace.description}</p></div><span className="iw-tag">{data.role === 'admin' ? '管理员' : '已加入'}</span></section>
      <h3 className="um-settings-group-title">学习服务</h3><section className="um-settings-group"><div className="um-settings-row"><span>服务期限</span><span className="um-settings-value">至 {serviceDate(data.workspace.service_ends_at)}</span></div><div className="um-settings-row"><span>加入时间</span><span className="um-settings-value">{serviceDate(data.workspace.joined_at)}</span></div><div className="um-settings-row"><span>已开通课程</span><span className="um-settings-value">{data.courses.filter(c => c.status === 'published').length} 节</span></div></section>
      <div className="iw-enrolled-courses"><h3 className="um-settings-group-title">你的课程</h3>{data.courses.filter(c => c.status === 'published').map(course => <div className="iw-course-line" key={course.id}><span>{course.title}</span><span>{course.module} · {course.duration}</span></div>)}</div>
      {data.role === 'admin' && <section className="iw-manage-entry"><Buildings size={24} /><div><h3>机构管理</h3><p>管理课程与知识结构、学生、邀请码和服务用量。</p></div><Button asChild><Link to="/settings/institution">管理机构<ArrowRight size={16} /></Link></Button></section>}
    </> : <>
      <section className="iw-join-intro"><span className="iw-join-icon"><Buildings size={30} weight="duotone" /></span><h3>连接你的机构学习服务</h3><p>使用机构提供的邀请码，开通课程和小宇伴学。<br />继续使用当前账号，已有学习记录会保留。</p></section>
      {!data.available ? <p className="iw-feedback" role="status">机构学习服务尚未开放，开放后可在这里输入邀请码加入。</p> : <form className="iw-join-form" onSubmit={e => { e.preventDefault(); void submit(false); }}><label htmlFor="institution-invite">机构邀请码</label><div><Input id="institution-invite" value={code} onChange={e => { setCode(e.target.value); setInvite(null); setError(''); }} placeholder="输入机构提供的邀请码" autoComplete="off" maxLength={80} disabled={busy} /><Button disabled={busy || !code.trim()} type="submit"><Key size={16} />{busy ? '正在验证…' : '验证邀请码'}</Button></div><p>加入前，你可以确认机构、课程和服务期限。</p>{data.demo && <small>预览邀请码：LEARN2027</small>}</form>}
      {invite && <section className="iw-invite-confirm" aria-label="确认加入机构"><span className="iw-eyebrow">请确认学习服务</span><h3>{invite.name}</h3><p>{invite.service}</p><ul>{invite.courses.map(title => <li key={title}><CheckCircle size={16} />{title}</li>)}</ul><p>服务至 {serviceDate(invite.service_ends_at)}</p><div><Button variant="outline" disabled={busy} onClick={() => setInvite(null)}>取消</Button><Button disabled={busy} onClick={() => void submit(true)}>{busy ? '正在加入…' : '确认加入'}</Button></div></section>}
      {error && <p className="iw-error" role="alert">{error}</p>}
    </>}
  </div>;
}
