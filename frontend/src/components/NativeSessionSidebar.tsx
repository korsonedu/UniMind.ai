import { useId, useState } from 'react';
import { MagnifyingGlass, Plus, Trash, CaretRight, Folder, DotsThree, PencilSimple, PushPin, X } from '@phosphor-icons/react';
import { Collapse } from './ui/collapse';
import * as Dialog from '@radix-ui/react-dialog';
import * as AlertDialog from '@radix-ui/react-alert-dialog';
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuSub, DropdownMenuSubTrigger, DropdownMenuSubContent } from './ui/dropdown-menu';
import type { SessionSidebarProps } from './SessionSidebar';
import type { ConversationPatch, ConversationSession } from '@/hooks/useAgentConversation';
import type { ConversationProjectControls } from '@/hooks/useConversationProjects';

interface Props extends SessionSidebarProps {
  projectControls: ConversationProjectControls;
  onNewInProject: (id: number) => void;
  onUpdate: (session: ConversationSession, patch: ConversationPatch) => Promise<boolean>;
}

export default function NativeSessionSidebar({ sessions, activeSessionId, thinkingIds, unreadIds, onSelect, onDelete, onNew, projectControls: controls, onNewInProject, onUpdate }: Props) {
  const [query, setQuery] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const [editing, setEditing] = useState<{ id?: number; name: string; instructions: string } | null>(null);
  const [deleting, setDeleting] = useState<{ projectId: number; name: string } | { session: ConversationSession; name: string } | null>(null);
  const [deletingPending, setDeletingPending] = useState(false);
  const [closedProjects, setClosedProjects] = useState<number[]>([]);
  const [renaming, setRenaming] = useState<{ session: ConversationSession; name: string } | null>(null);
  const [updating, setUpdating] = useState(false);
  const projectsId = useId();
  const ordered = [...sessions].reverse().sort((a, b) => Number(!!b.isPinned) - Number(!!a.isPinned));
  const filtered = ordered.filter(session => [session.title, session.label, ...session.messages.map(message => message.content)].join(' ').toLowerCase().includes(query.trim().toLowerCase()));
  const uncategorized = ordered.filter(session => !controls.projects.some(project => project.id === session.projectId));
  const select = (session: ConversationSession) => { onSelect(session); setSearchOpen(false); };
  const update = async (session: ConversationSession, patch: ConversationPatch) => {
    if (updating) return false;
    setUpdating(true);
    try { return await onUpdate(session, patch); }
    finally { setUpdating(false); }
  };
  const renderSession = (session: ConversationSession, search = false) => {
    const thinking = session.conversationId ? thinkingIds?.includes(session.conversationId) : false;
    const unread = session.conversationId ? unreadIds?.has(session.conversationId) : false;
    return <li key={session.id} data-active={session.id === activeSessionId}>
    <button data-session-select aria-current={session.id === activeSessionId ? 'page' : undefined} onClick={() => select(session)} title={`${session.title || session.label} · ${session.messages.length} 条`}>
      <span className="um-agent-session-title">{session.isPinned && <PushPin size={12} className="inline-block mr-1" aria-label="已置顶" />}<span className="um-agent-session-name">{session.title || session.label}</span>{thinking ? <span className="um-agent-session-thinking" role="status" aria-label="正在思考" title="正在思考" /> : unread ? <span className="um-agent-unread-dot" role="status" aria-label="有新回复" title="有新回复" /> : null}</span>{search && <span className="um-agent-session-meta">{controls.projects.find(project => project.id === session.projectId)?.name || '未分类'} · {session.lastTime ? new Date(session.lastTime).toLocaleDateString('zh-CN') : ''}</span>}
    </button>
    <DropdownMenu><DropdownMenuTrigger asChild><button className="um-agent-session-menu um-agent-icon-button" aria-label={`对话菜单：${session.title || session.label}`}><DotsThree size={18} /></button></DropdownMenuTrigger>
      <DropdownMenuContent className="um-native-menu" align="start" onCloseAutoFocus={event => { if (renaming) event.preventDefault(); }}>
        <DropdownMenuItem disabled={updating || !session.conversationId} onSelect={() => { setSearchOpen(false); setRenaming({ session, name: session.title || session.label }); }}><PencilSimple size={15} />重命名</DropdownMenuItem>
        <DropdownMenuItem disabled={updating || !session.conversationId} onSelect={() => void update(session, { is_pinned: !session.isPinned })}><PushPin size={15} />{session.isPinned ? '取消置顶' : '置顶'}</DropdownMenuItem>
        <DropdownMenuSub><DropdownMenuSubTrigger disabled={updating || controls.error || !session.conversationId}><Folder size={15} className="mr-2" />移动到项目</DropdownMenuSubTrigger><DropdownMenuSubContent className="um-native-menu">
          <DropdownMenuItem disabled={!session.projectId} onSelect={() => void update(session, { project_id: null })}>未分类</DropdownMenuItem>
          {controls.projects.map(project => <DropdownMenuItem key={project.id} disabled={session.projectId === project.id} onSelect={() => { setClosedProjects(previous => previous.filter(id => id !== project.id)); void update(session, { project_id: project.id }); }}>{project.name}</DropdownMenuItem>)}
        </DropdownMenuSubContent></DropdownMenuSub>
        {onDelete && <><DropdownMenuSeparator /><DropdownMenuItem className="um-agent-menu-danger" onSelect={() => setDeleting({ session, name: session.title || session.label })}><Trash size={15} />删除对话</DropdownMenuItem></>}
      </DropdownMenuContent>
    </DropdownMenu>
  </li>;
  };
  return <aside className="um-agent-sessions" aria-label="历史对话">
    <header><h2>对话</h2></header>
    <div className="um-agent-session-actions">
      <button className="um-agent-icon-button" data-session-new onClick={onNew} aria-label="开始新对话" title="新对话"><Plus size={18} /></button>
      <Dialog.Root open={searchOpen} onOpenChange={open => { setSearchOpen(open); if (!open) setQuery(''); }}>
        <Dialog.Trigger asChild><button className="um-agent-icon-button" aria-label="搜索对话" title="搜索对话"><MagnifyingGlass size={18} /></button></Dialog.Trigger>
        <Dialog.Portal><Dialog.Overlay className="um-agent-search-overlay" /><Dialog.Content className="um-native-agent um-agent-search-dialog">
          <Dialog.Title className="sr-only">搜索对话</Dialog.Title><Dialog.Description className="sr-only">按标题或对话内容搜索所有项目。</Dialog.Description>
          <label className="um-agent-search"><MagnifyingGlass size={18} /><input autoFocus value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索标题或对话内容…" aria-label="搜索标题或对话内容" /><Dialog.Close asChild><button className="um-agent-icon-button" aria-label="关闭搜索"><X size={16} /></button></Dialog.Close></label>
          <nav aria-label="搜索结果"><ul>{filtered.map(session => renderSession(session, true))}</ul>{!filtered.length && <p className="um-agent-empty">没有匹配的对话</p>}</nav>
        </Dialog.Content></Dialog.Portal>
      </Dialog.Root>
    </div>
    <nav aria-label="会话列表">
      <>
        <div className="um-agent-section-label"><span>项目</span><button className="um-agent-icon-button" aria-label="创建项目" title="创建项目" disabled={controls.error} onClick={() => setEditing({ name: '', instructions: '' })}><Plus size={15} /></button></div>
        {controls.error && <button className="um-agent-project-retry" onClick={controls.reload}>项目未加载，重试</button>}
        {controls.projects.map(project => {
          const closed = closedProjects.includes(project.id);
          const projectSessions = ordered.filter(session => session.projectId === project.id);
          return <section key={project.id} className="um-agent-project" aria-label={`项目：${project.name}`}>
            <div className="um-agent-project-heading group/project" data-current={controls.projectId === project.id}>
              <button aria-expanded={!closed} aria-controls={`${projectsId}-${project.id}`} onClick={() => setClosedProjects(previous => closed ? previous.filter(id => id !== project.id) : [...previous, project.id])}><CaretRight size={12} className="um-disclosure-chevron" /><Folder size={16} /><span>{project.name}</span></button>
              <button className="um-agent-icon-button opacity-0 group-hover/project:opacity-100 group-focus-within/project:opacity-100 [@media(hover:none)]:opacity-100" data-session-new aria-label={`在项目「${project.name}」中新建对话`} title="新建对话" onClick={() => { setClosedProjects(previous => previous.filter(id => id !== project.id)); onNewInProject(project.id); }}><Plus size={17} /></button>
              <DropdownMenu><DropdownMenuTrigger asChild><button className="um-agent-icon-button" aria-label={`项目菜单：${project.name}`}><DotsThree size={18} /></button></DropdownMenuTrigger><DropdownMenuContent className="um-native-menu" align="start" onCloseAutoFocus={event => { if (editing) event.preventDefault(); }}>
                <DropdownMenuItem data-session-new onSelect={() => { setClosedProjects(previous => previous.filter(id => id !== project.id)); onNewInProject(project.id); }}><Plus size={15} />在项目中新建对话</DropdownMenuItem>
                <DropdownMenuItem onSelect={() => setEditing({ id: project.id, name: project.name, instructions: project.instructions || '' })}><PencilSimple size={15} />项目设置</DropdownMenuItem>
                <DropdownMenuSeparator /><DropdownMenuItem className="um-agent-menu-danger" disabled={controls.pending} onSelect={() => setDeleting({ projectId: project.id, name: project.name })}><Trash size={15} />删除项目</DropdownMenuItem>
              </DropdownMenuContent></DropdownMenu>
            </div>
            <Collapse open={!closed} id={`${projectsId}-${project.id}`}><ul className="um-agent-project-sessions">{projectSessions.map(session => renderSession(session))}{!projectSessions.length && <li className="um-agent-project-empty"><button data-session-new onClick={() => onNewInProject(project.id)}>开始对话</button></li>}</ul></Collapse>
          </section>;
        })}
        {!controls.projects.length && !controls.error && !editing && <p className="um-agent-project-hint">设置学习目标，让小宇持续跟进</p>}
        <div className="um-agent-section-label"><span>未分类</span></div>
      </>
      <ul>{uncategorized.map(session => renderSession(session))}</ul>
      {!uncategorized.length && <p className="um-agent-project-hint">暂无对话</p>}
    </nav>
    <Dialog.Root open={renaming !== null} onOpenChange={open => { if (!open && !updating) setRenaming(null); }}>
      <Dialog.Portal><Dialog.Overlay className="um-agent-project-overlay" /><Dialog.Content className="um-native-agent um-agent-project-dialog">
        <Dialog.Title>重命名对话</Dialog.Title><Dialog.Description className="sr-only">为此对话设置一个便于查找的名称。</Dialog.Description>
        {renaming && <form onSubmit={async event => { event.preventDefault(); if (await update(renaming.session, { title: renaming.name.trim() })) setRenaming(null); }}>
          <label>对话名称<input autoFocus required maxLength={120} value={renaming.name} disabled={updating} onChange={event => setRenaming({ ...renaming, name: event.target.value })} /></label>
          <footer><button className="um-agent-button" type="button" disabled={updating} onClick={() => setRenaming(null)}>取消</button><button className="um-agent-button um-agent-button-primary" disabled={updating || !renaming.name.trim()} type="submit">{updating ? '保存中…' : '保存'}</button></footer>
        </form>}
      </Dialog.Content></Dialog.Portal>
    </Dialog.Root>
    <Dialog.Root open={editing !== null} onOpenChange={open => { if (!open && !controls.pending) setEditing(null); }}>
      <Dialog.Portal><Dialog.Overlay className="um-agent-project-overlay" /><Dialog.Content className="um-native-agent um-agent-project-dialog">
        <Dialog.Title>{editing?.id === undefined ? '新建项目' : '项目设置'}</Dialog.Title>
        <Dialog.Description>项目内的对话共享你填写的学习目标与要求。</Dialog.Description>
        {editing && <form onSubmit={async event => {
          event.preventDefault();
          const saved = editing.id === undefined ? await controls.create(editing.name, editing.instructions) : await controls.update(editing.id, editing.name, editing.instructions);
          if (saved) setEditing(null);
        }}>
          <label>项目名称<input autoFocus required aria-label="项目名称" placeholder="例如：金融学考研复习" maxLength={60} value={editing.name} disabled={controls.pending} onChange={event => setEditing({ ...editing, name: event.target.value })} /></label>
          <label>学习目标、背景与要求<textarea required aria-label="学习目标、背景与要求" placeholder="告诉小宇你的目标、目前的基础和期望的帮助。例如：12 月参加考试，利率理论比较薄弱，希望先讲解再用题目检验。" maxLength={4000} rows={5} value={editing.instructions} disabled={controls.pending} onChange={event => setEditing({ ...editing, instructions: event.target.value })} /></label>
          <footer><button className="um-agent-button" type="button" onClick={() => setEditing(null)} disabled={controls.pending}>取消</button><button className="um-agent-button um-agent-button-primary" type="submit" disabled={controls.pending || !editing.name.trim() || !editing.instructions.trim()}>{controls.pending ? '保存中…' : editing.id === undefined ? '创建项目' : '保存'}</button></footer>
        </form>}
      </Dialog.Content></Dialog.Portal>
    </Dialog.Root>
    <AlertDialog.Root open={deleting !== null} onOpenChange={open => { if (!open && !deletingPending) setDeleting(null); }}>
      <AlertDialog.Portal><AlertDialog.Overlay className="um-agent-project-overlay" /><AlertDialog.Content className="um-native-agent um-agent-project-dialog">
        <AlertDialog.Title>{deleting && 'projectId' in deleting ? '删除项目？' : '删除对话？'}</AlertDialog.Title>
        <AlertDialog.Description>{deleting && 'projectId' in deleting ? `「${deleting.name}」及其中的全部会话和消息将一起删除，无法恢复。` : `「${deleting?.name}」的全部消息将删除，无法恢复。`}</AlertDialog.Description>
        <footer><AlertDialog.Cancel asChild><button className="um-agent-button" disabled={deletingPending}>取消</button></AlertDialog.Cancel><AlertDialog.Action asChild><button className="um-agent-button um-agent-button-danger" disabled={deletingPending} onClick={async event => {
          event.preventDefault();
          if (!deleting || deletingPending) return;
          setDeletingPending(true);
          try {
            if ('projectId' in deleting) { if (await controls.remove(deleting.projectId)) setDeleting(null); }
            else { await onDelete?.(deleting.session); setDeleting(null); }
          } finally { setDeletingPending(false); }
        }}>{deletingPending ? '删除中…' : '删除'}</button></AlertDialog.Action></footer>
      </AlertDialog.Content></AlertDialog.Portal>
    </AlertDialog.Root>
  </aside>;
}
