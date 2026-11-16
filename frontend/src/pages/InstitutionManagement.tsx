import { useEffect, useState } from 'react';
import { Link, Navigate, useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, ArrowUpRight, Buildings, CheckCircle, Copy, FileVideo, FolderSimple, Key, MagnifyingGlass, Plus, UploadSimple, Users, ChartBar, TreeStructure } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { WorkspacePreviewNotice } from '@/components/settings/InstitutionServices';
import api from '@/lib/api';
import { useSystemStore } from '@/store/useSystemStore';
import { formatApiErrorToast } from '@/lib/apiError';
import { useWorkspace, workspacePath, serviceDate, type WorkspaceCourse } from '@/lib/workspace';
import { toast } from 'sonner';
import '@/styles/institution-workspace.css';

const tabs = [
  { id: 'courses', name: '课程与资料', icon: FolderSimple },
  { id: 'knowledge', name: '知识结构', icon: TreeStructure },
  { id: 'members', name: '学生', icon: Users },
  { id: 'invites', name: '邀请码', icon: Key },
  { id: 'usage', name: '服务用量', icon: ChartBar },
] as const;
const statusNames = { published: '已发布', draft: '待发布', processing: '处理中', failed: '处理失败' };

export default function InstitutionManagement() {
  const setPageHeader = useSystemStore(state => state.setPageHeader);
  useEffect(() => { setPageHeader('机构管理', ''); return () => setPageHeader('', ''); }, [setPageHeader]);
  const { data, isPending, isError, refetch } = useWorkspace();
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const tab = tabs.find(item => item.id === params.get('tab')) || tabs[0];
  const [search, setSearch] = useState('');
  const [dialog, setDialog] = useState<'upload' | 'invite' | null>(null);
  const [selected, setSelected] = useState<WorkspaceCourse | null>(null);
  const [busy, setBusy] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [moduleName, setModuleName] = useState('');
  const [inviteName, setInviteName] = useState('');
  const [courseIds, setCourseIds] = useState<number[]>([]);
  const [maxUses, setMaxUses] = useState(50);
  const [expiry, setExpiry] = useState('');
  const [serviceEnd, setServiceEnd] = useState('');
  const [error, setError] = useState('');
  const [memberAction, setMemberAction] = useState<{ id: number; name: string; active: boolean } | null>(null);
  async function mutate(path: string, body: unknown, method: 'post' | 'patch' = 'post') {
    if (busy) return false;
    setBusy(true); setError('');
    try { await api[method](`${workspacePath}${path}`, body); await client.invalidateQueries({ queryKey: ['workspace'] }); return true; }
    catch (err) { const message = formatApiErrorToast(err, '操作失败，请重试。'); setError(message); toast.error(message); return false; }
    finally { setBusy(false); }
  }
  async function upload(event: React.FormEvent) {
    event.preventDefault();
    if (files.reduce((sum, file) => sum + file.size, 0) > 200 * 1024 ** 2) { setError('每批视频总大小不能超过 200 MB，请分批上传。'); return; }
    const form = new FormData();
    form.append('module', moduleName.trim()); files.forEach(file => form.append('videos', file));
    if (await mutate('courses/', form)) { setDialog(null); setFiles([]); setModuleName(''); toast.success('已添加课程，等待内容处理'); }
  }
  async function createInvite(event: React.FormEvent) {
    event.preventDefault();
    if (await mutate('invites/', { name: inviteName.trim(), courses: courseIds, max_uses: maxUses, expires_at: expiry, service_ends_at: serviceEnd })) {
      setDialog(null); setInviteName(''); setCourseIds([]); setExpiry(''); setServiceEnd(''); toast.success('邀请码已创建');
    }
  }
  const openDialog = (value: 'upload' | 'invite') => { setError(''); setDialog(value); };
  if (isPending) return <div className="iw-loading" role="status">正在读取机构管理…</div>;
  if (isError) return <div className="iw-loading"><p>暂时无法读取机构信息。</p><Button variant="outline" onClick={() => void refetch()}>重试</Button></div>;
  if (!data?.workspace || data.role !== 'admin' || data.workspace.service_active === false) return <Navigate to="/settings?section=institution" replace />;
  const courses = data.courses.filter(course => `${course.title} ${course.module}`.includes(search.trim()));
  const members = data.members.filter(member => member.name.includes(search.trim()));
  const published = data.courses.filter(course => course.status === 'published');
  const processed = data.courses.filter(course => ['published', 'draft'].includes(course.status));
  async function showCourse(course: WorkspaceCourse) {
    try { setSelected((await api.get(`${workspacePath}courses/${course.id}/`)).data); }
    catch (err) { toast.error(formatApiErrorToast(err, '读取课程失败，请重试。')); }
  }
  return <div className="iw-management">
    <header className="iw-topbar"><Link to="/settings?section=institution"><ArrowLeft size={17} />返回设置</Link><span>机构与学习服务<span>/</span>机构管理</span><span className="iw-tag">管理员</span></header>
    <div className="iw-management-body"><WorkspacePreviewNotice />
      <section className="iw-management-heading"><div><span className="iw-eyebrow">机构管理</span><h1>{data.workspace.name}</h1><p>管理课程内容、学生与学习服务。</p></div><span className="iw-monogram"><Buildings size={31} weight="duotone" /></span></section>
      <div className="iw-stats"><div><span>课程内容</span><strong>{data.courses.length}<small>节</small></strong><p>{published.length} 节已发布</p></div><div><span>已加入学生</span><strong>{data.members.length}<small>人</small></strong><p>{data.members.filter(member => member.active).length} 人服务有效</p></div><div><span>知识结构</span><strong>{data.courses.flatMap(course => course.knowledge).length}<small>个主题</small></strong><p>关联课程与讲稿</p></div><div><span>服务期限</span><strong className="iw-stat-date">{serviceDate(data.workspace.service_ends_at)}</strong><p>当前机构服务</p></div></div>
      <nav className="iw-tabs" aria-label="机构管理分类">{tabs.map(item => <button key={item.id} aria-current={item.id === tab.id ? 'page' : undefined} onClick={() => { setParams({ tab: item.id }, { replace: true }); setSearch(''); }}><item.icon size={18} />{item.name}</button>)}</nav>
      <section className="iw-panel" aria-label={tab.name}>
        <div className="iw-panel-heading"><div><h2>{tab.name}</h2><p>{({ courses: '上传视频与资料，检查处理结果后发布给学生。', knowledge: '从课程内容中提取知识，并保留对应的讲稿依据。', members: '管理通过邀请码加入的学生及其学习服务。', invites: '统一通知学生，自行注册后输入邀请码加入。', usage: '查看课程处理与学生使用的服务额度。' })[tab.id]}</p></div>
          {tab.id === 'courses' && <Button onClick={() => openDialog('upload')}><UploadSimple size={17} />上传课程</Button>}
          {tab.id === 'invites' && <Button onClick={() => openDialog('invite')}><Plus size={17} />创建邀请码</Button>}
        </div>
        {(tab.id === 'courses' || tab.id === 'members') && <div className="iw-search"><MagnifyingGlass size={17} /><input aria-label={tab.id === 'courses' ? '搜索课程' : '搜索学生'} value={search} onChange={e => setSearch(e.target.value)} placeholder={tab.id === 'courses' ? '搜索课程或模块' : '搜索学生姓名'} /></div>}
        {tab.id === 'courses' && <div className="iw-table-wrap"><table><thead><tr><th>课程</th><th>所属模块</th><th>内容处理</th><th>发布状态</th><th><span className="sr-only">操作</span></th></tr></thead><tbody>{courses.map(course => <tr key={course.id}><td><div className="iw-title-cell"><span className="iw-file-icon"><FileVideo size={21} /></span><div><strong>{course.title}</strong><small>{course.duration} · {course.filename}</small></div></div></td><td>{course.module}</td><td><span className={course.status === 'processing' ? 'iw-muted' : 'iw-ready'}>{course.status === 'failed' ? course.error_message || '处理失败，请重试' : course.status === 'processing' ? '等待 ASR 与结构构建' : <><CheckCircle size={15} />讲稿与知识结构就绪</>}</span></td><td><span className={`iw-status iw-status-${course.status}`}>{statusNames[course.status]}</span></td><td><div className="iw-row-actions"><button onClick={() => void showCourse(course)} aria-label={`查看${course.title}`}>查看</button>{course.status === 'failed' && <button disabled={busy} onClick={() => void mutate(`courses/${course.id}/`, { retry: true }, 'patch')}>重试</button>}{['published', 'draft'].includes(course.status) && <button disabled={busy} onClick={() => void mutate(`courses/${course.id}/`, { status: course.status === 'published' ? 'draft' : 'published' }, 'patch')}>{course.status === 'published' ? '下架' : '发布'}</button>}</div></td></tr>)}</tbody></table>{!courses.length && <p className="iw-empty">{search ? '没有找到匹配的课程。' : '上传第一节课程，开始构建学习内容。'}</p>}</div>}
        {tab.id === 'knowledge' && <div className="iw-knowledge-list">{processed.length ? processed.map(course => <details key={course.id} open><summary><span><TreeStructure size={19} /><strong>{course.title}</strong></span><small>{course.knowledge.length} 个主题</small></summary><div className="iw-knowledge-branches">{course.knowledge.map(node => <div key={node.name}><h3>{node.name}</h3><ul>{node.children.map(child => <li key={child}>{child}</li>)}</ul></div>)}</div><button className="iw-source-link" onClick={() => void showCourse(course)}>查看来源讲稿<ArrowUpRight size={15} /></button></details>) : <p className="iw-empty">课程处理完成后，知识结构会显示在这里。</p>}</div>}
        {tab.id === 'members' && <div className="iw-table-wrap"><table><thead><tr><th>学生</th><th>加入时间</th><th>课程权限</th><th>服务状态</th><th><span className="sr-only">操作</span></th></tr></thead><tbody>{members.map(member => <tr key={member.id}><td><div className="iw-person"><span>{member.name.slice(-2, -1)}</span><strong>{member.name}</strong></div></td><td>{serviceDate(member.joined_at)}</td><td><span>{member.courses.length} 节课程</span><small>至 {serviceDate(member.service_ends_at)}</small></td><td><span className={`iw-status ${member.active ? 'iw-status-published' : 'iw-status-draft'}`}>{member.active ? '服务有效' : '已暂停'}</span></td><td><button className="iw-text-button" disabled={busy} onClick={() => setMemberAction(member)}>{member.active ? '暂停服务' : '恢复服务'}</button></td></tr>)}</tbody></table>{!members.length && <p className="iw-empty">{search ? '没有找到匹配的学生。' : '分享邀请码后，已加入的学生会出现在这里。'}</p>}</div>}
        {tab.id === 'invites' && <div className="iw-invite-list">{data.invites.map(invite => <article key={invite.id}><div className="iw-invite-top"><div><h3>{invite.name}</h3><p>{invite.courses.map(id => data.courses.find(course => course.id === id)?.title).filter(Boolean).join('、')}</p></div><span className={`iw-status ${invite.active ? 'iw-status-published' : 'iw-status-draft'}`}>{invite.state_label || (invite.active ? '可领取' : '已停用')}</span></div><div className="iw-code-row"><code>{invite.code}</code><Button variant="outline" size="sm" onClick={async () => { try { await navigator.clipboard.writeText(`请下载标准 UniMind.ai，注册或登录后，在「设置 → 机构与学习服务」输入邀请码 ${invite.code}，加入${data.workspace!.name}。`); toast.success('开通通知已复制'); } catch { toast.error('复制失败，请手动复制邀请码'); } }}><Copy size={15} />复制通知</Button></div><footer><span>已领取 {invite.used_count} / {invite.max_uses} 人</span><span>领取截止 {serviceDate(invite.expires_at)}</span><span>服务至 {serviceDate(invite.service_ends_at)}</span><button disabled={busy} onClick={() => void mutate(`invites/${invite.id}/`, { active: !(invite.enabled ?? invite.active) }, 'patch')}>{(invite.enabled ?? invite.active) ? '停用邀请码' : '启用邀请码'}</button></footer></article>)}{!data.invites.length && <p className="iw-empty">创建邀请码，向学生开放已配置的课程服务。</p>}<p className="iw-note">停用邀请码只停止新领取，已加入学生的服务期限保持不变。</p></div>}
        {tab.id === 'usage' && <div className="iw-usage-list">{data.usage.map(item => <article key={item.label}><div><h3>{item.label}</h3><span><strong>{item.used.toLocaleString()}</strong> {item.limit !== null ? ` / ${item.limit.toLocaleString()}` : ''} {item.unit}</span></div>{item.limit !== null ? <><progress value={item.used} max={item.limit} aria-label={item.label} /><p>剩余 {Math.max(0, item.limit - item.used).toLocaleString()} {item.unit}</p></> : <p>累计用量</p>}</article>)}<p className="iw-note">课程处理与学生使用分别统计。同一课程可供获授权的学生共同学习。</p></div>}
      </section>
    </div>
    <Dialog open={dialog !== null} onOpenChange={open => { if (!busy && !open) { setDialog(null); setError(''); } }}><DialogContent className="iw-dialog"><DialogHeader><DialogTitle>{dialog === 'upload' ? '上传课程' : '创建邀请码'}</DialogTitle><DialogDescription>{dialog === 'upload' ? '上传视频后，平台将进行 ASR 和知识结构构建。检查处理结果后再发布。' : '学生自行注册后，输入同一个邀请码领取课程服务。'}</DialogDescription></DialogHeader>
      {dialog === 'upload' ? <form onSubmit={e => void upload(e)}><label>所属模块<Input value={moduleName} onChange={e => setModuleName(e.target.value)} placeholder="例如：货币金融学" required maxLength={100} /></label><label className="iw-upload-zone"><UploadSimple size={30} /><strong>选择课程视频</strong><span>支持 MP4，可多选，每批总计不超过 200 MB</span><input type="file" aria-label="选择课程视频" accept="video/mp4,.mp4" multiple required onChange={e => setFiles(Array.from(e.target.files || []))} /></label>{files.map(file => <p className="iw-file-selection" key={`${file.name}-${file.size}`}>{file.name}<span>{(file.size / 1024 / 1024).toFixed(1)} MB</span></p>)}{data.demo && <p className="iw-note">本次为上传交互预览，不会上传文件或触发真实 ASR。</p>}<footer><Button variant="outline" type="button" disabled={busy} onClick={() => setDialog(null)}>取消</Button><Button disabled={busy || !files.length || !moduleName.trim()} type="submit">{busy ? '正在提交…' : '添加课程'}</Button></footer></form> : <form onSubmit={e => void createInvite(e)}><label>学习服务名称<Input value={inviteName} onChange={e => setInviteName(e.target.value)} required placeholder="例如：2027 金融基础班" maxLength={100} /></label><fieldset><legend>开通课程</legend>{published.length ? published.map(course => <label className="iw-course-check" key={course.id}><input type="checkbox" checked={courseIds.includes(course.id)} onChange={e => setCourseIds(ids => e.target.checked ? [...ids, course.id] : ids.filter(id => id !== course.id))} />{course.title}</label>) : <p>请先发布课程。</p>}</fieldset><div className="iw-form-grid"><label>最多领取人数<Input type="number" value={maxUses} min={1} max={10000} onChange={e => setMaxUses(Number(e.target.value))} required /></label><label>领取截止日期<Input type="date" value={expiry} onChange={e => setExpiry(e.target.value)} required /></label></div><label>学习服务结束日期<Input type="date" value={serviceEnd} min={expiry} onChange={e => setServiceEnd(e.target.value)} required /></label><footer><Button variant="outline" type="button" disabled={busy} onClick={() => setDialog(null)}>取消</Button><Button disabled={busy || !courseIds.length} type="submit">{busy ? '正在创建…' : '创建邀请码'}</Button></footer></form>}{error && <p className="iw-error" role="alert">{error}</p>}
    </DialogContent></Dialog>
    <Dialog open={!!selected} onOpenChange={open => { if (!open) setSelected(null); }}><DialogContent className="iw-dialog iw-course-detail"><DialogHeader><DialogTitle>{selected?.title}</DialogTitle><DialogDescription>{selected?.module} · {selected ? statusNames[selected.status] : ''}</DialogDescription></DialogHeader>{selected?.status === 'processing' || selected?.status === 'failed' ? <p>{selected.status === 'failed' ? selected.error_message || '内容处理失败，请重试。' : '课程已添加，等待 ASR 与知识结构构建完成。'}</p> : <><h3>课程讲稿</h3><p className="iw-transcript">{selected?.transcript}</p><h3>知识结构</h3>{selected?.knowledge.map(node => <div key={node.name}><strong>{node.name}</strong><p className="iw-note">{node.children.join(' · ')}</p></div>)}</>}{data.demo && <p className="iw-note">讲稿与结构为预览样例，未执行真实转写。</p>}</DialogContent></Dialog>
    <Dialog open={!!memberAction} onOpenChange={open => { if (!busy && !open) setMemberAction(null); }}><DialogContent><DialogHeader><DialogTitle>{memberAction?.active ? '暂停' : '恢复'}学生服务？</DialogTitle><DialogDescription>{memberAction?.name}{memberAction?.active ? '将暂停访问机构课程，账号与已有学习记录保留。' : '将恢复原有课程权限，服务期限保持不变。'}</DialogDescription></DialogHeader><div className="iw-dialog-actions"><Button variant="outline" disabled={busy} onClick={() => setMemberAction(null)}>取消</Button><Button disabled={busy} onClick={async () => { if (memberAction && await mutate(`members/${memberAction.id}/`, { active: !memberAction.active }, 'patch')) setMemberAction(null); }}>确认{memberAction?.active ? '暂停' : '恢复'}</Button></div></DialogContent></Dialog>
  </div>;
}
