import { useContext, useLayoutEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, ArrowUpRight, BookOpenText, Cards, ClipboardText, Copy, FileText, NotePencil, Plus, Sparkle, Trash } from '@phosphor-icons/react';
import { toast } from 'sonner';
import { t } from '@/i18n';
import { MarkdownContent } from '@/components/MarkdownContent';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { normalizeApiError } from '@/lib/apiError';
import { useWorkbenchNotes, useWorkbenchStudio } from '@/lib/workbenchStudioApi';
import type { ProjectNote, ProjectSourceSummary, StudioKind } from '@/types/workbench';
import { FlashcardDeckView } from './FlashcardDeckView';
import { StudioQuizView } from './StudioQuizView';
import { WorkbenchCitationContext, workbenchCitationMarkdown } from './workbenchCitations';

const creationCards = [
  { kind: 'study_guide', icon: BookOpenText, title: '资料导读', description: '提炼主线问题、概念词典与阅读脉络' },
  { kind: 'briefing', icon: FileText, title: '精华简报', description: '合并课件与讲稿，去重后生成考前串讲讲义' },
  { kind: 'flashcards', icon: Cards, title: '记忆闪卡', description: '翻转问答闪卡，标记掌握情况' },
  { kind: 'quiz', icon: ClipboardText, title: '出题自测', description: '围绕已选资料出题，提交后查看判分和解析' },
] as const;
const studioKindTitle = (kind: StudioKind) => kind === 'faq' ? '核心问答' : creationCards.find(card => card.kind === kind)!.title;

type StudioView = { artifactId: string } | { note: ProjectNote | null };

function StudioNoteEditor({ note, saving, onSave, onBack }: {
  note: ProjectNote | null;
  saving: boolean;
  onSave: (draft: Pick<ProjectNote, 'title' | 'content'>) => void;
  onBack: () => void;
}) {
  const [title, setTitle] = useState(note?.title ?? '');
  const [content, setContent] = useState(note?.content ?? '');
  const dirty = title !== (note?.title ?? '') || content !== (note?.content ?? '');
  return <form className="um-wb-note-editor" onSubmit={event => {
    event.preventDefault();
    if (dirty && !saving) onSave({ title: title.trim(), content });
  }}>
    <label>{t('标题')}<input className="um-wb-studio-input" maxLength={300} value={title}
      onChange={event => setTitle(event.target.value)} disabled={saving} /></label>
    <label>Markdown<textarea className="um-wb-studio-input" rows={10} value={content}
      onChange={event => setContent(event.target.value)} disabled={saving} /></label>
    <div className="um-wb-studio-tools">
      <button type="submit" className="um-agent-button um-agent-button-primary" disabled={saving || !dirty}>
        {saving ? t('正在保存…') : t('保存笔记')}
      </button>
      <button type="button" className="um-agent-button" disabled={saving} onClick={onBack}>{t('取消')}</button>
      {note && <Link className="um-agent-button" to={`/notes/${note.id}`}>{t('打开个人笔记')}<ArrowUpRight size={14} /></Link>}
    </div>
  </form>;
}

export function WorkbenchStudioPane({ projectId, selected }: {
  projectId: number;
  selected: ProjectSourceSummary[];
}) {
  const studio = useWorkbenchStudio(projectId);
  const notes = useWorkbenchNotes(projectId);
  const citationContext = useContext(WorkbenchCitationContext);
  if (!citationContext) throw new Error('WorkbenchStudioPane requires WorkbenchCitationContext.');
  const [view, navigate] = useState<StudioView | null>(null);
  const scroll = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => { if (scroll.current) scroll.current.scrollTop = 0; }, [view]);
  const artifact = view && 'artifactId' in view ? studio.list.data?.find(row => row.id === view.artifactId) : undefined;
  const noteView = view && 'note' in view ? view : null;
  const generateHint = selected.length ? undefined : t('请在资料源中勾选至少一份已就绪的资料。');
  const error = (cause: unknown, fallback: string) => toast.error(normalizeApiError(cause, fallback).message);
  const generate = (kind: StudioKind) => {
    if (generateHint || studio.generate.isPending) return;
    studio.generate.mutate({ kind, sourceIds: selected.map(source => source.id) }, {
      onSuccess: row => navigate(current => current === view ? { artifactId: row.id } : current),
      onError: cause => error(cause, '生成失败，请重试。'),
    });
  };
  const copy = async (content: string) => {
    try {
      await navigator.clipboard.writeText(content);
      toast.success(t('已复制 Markdown'));
    } catch {
      toast.error(t('复制失败，请选择正文手动复制。'));
    }
  };
  const removeArtifact = (id: string) => studio.remove.mutate(id, {
    onSuccess: () => navigate(null),
    onError: cause => error(cause, '删除失败，请重试。'),
  });
  const busy = studio.remove.isPending || studio.rate.isPending || studio.submitQuiz.isPending || studio.saveNote.isPending;
  const linkedNote = notes.list.data?.find(row => row.id === artifact?.linked_note);
  const artifactTitle = artifact && (artifact.kind === 'quiz' && artifact.title === '靶向自测' ? t('出题自测') : artifact.title);

  return <>
    <header className="um-wb-pane-header">
      {view ? <button type="button" className="um-agent-button" disabled={notes.save.isPending || busy} onClick={() => navigate(null)}>
        <ArrowLeft size={16} />{t('返回 Studio')}
      </button> : <>
        <h2>Studio</h2>
        <button type="button" className="um-agent-button um-wb-add" onClick={() => navigate({ note: null })}><Plus size={15} />{t('新建笔记')}</button>
      </>}
    </header>
    <div className="um-wb-studio-body" ref={scroll}>
      {studio.generate.isPending && <p role="status" className="um-wb-studio-status">
        <Sparkle size={15} />{t('正在生成{0}…', { 0: t(studioKindTitle(studio.generate.variables.kind)) })}
      </p>}
      {artifact ? <>
        <div className="um-wb-artifact-heading"><h3>{artifactTitle}</h3>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <button type="button" className="um-agent-icon-button" disabled={busy || artifact.status === 'generating'}
                title={t('删除产物')} aria-label={t('删除产物')}><Trash size={17} /></button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader><AlertDialogTitle>{t('删除这份 Studio 产物？')}</AlertDialogTitle>
                <AlertDialogDescription>{artifactTitle}</AlertDialogDescription></AlertDialogHeader>
              <AlertDialogFooter><AlertDialogCancel>{t('取消')}</AlertDialogCancel>
                <AlertDialogAction onClick={() => removeArtifact(artifact.id)}>{t('删除')}</AlertDialogAction></AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
        {artifact.status === 'generating' ? <p role="status" className="um-wb-muted">{t('正在生成…')}</p>
          : artifact.status === 'failed' ? <div className="um-wb-note-editor">
            <p className="um-wb-error" role="alert">{artifact.error_message}</p>
            <span title={generateHint}><button type="button" className="um-agent-button" disabled={!!generateHint || studio.generate.isPending}
              onClick={() => generate(artifact.kind)}>{t('重新生成')}</button></span>
          </div> : artifact.kind === 'flashcards' ? <FlashcardDeckView key={artifact.id}
            cards={artifact.structured_payload.cards} citations={artifact.citations} {...citationContext} saving={busy}
            onRate={(cardId, mastery) => studio.rate.mutate({ id: artifact.id, cardId, mastery }, {
              onError: cause => error(cause, '掌握状态未保存，请重试。'),
            })} /> : artifact.kind === 'quiz' ? <StudioQuizView key={artifact.id}
            questions={artifact.structured_payload.questions} attempt={artifact.structured_payload.latest_attempt}
            submitting={busy} generating={studio.generate.isPending} generateHint={generateHint} {...citationContext}
            onSubmit={async answers => {
              try {
                await studio.submitQuiz.mutateAsync({ id: artifact.id, answers });
                if (scroll.current) scroll.current.scrollTop = 0;
                return true;
              } catch (cause) {
                error(cause, '自测提交失败，请重试。');
                return false;
              }
            }} onGenerate={() => generate('quiz')} /> : <>
            <div className="um-wb-studio-tools">
              {linkedNote ? <Link to={`/notes/${linkedNote.id}`} className="um-agent-button">{t('打开个人笔记')}<ArrowUpRight size={14} /></Link>
                : <button type="button" className="um-agent-button" disabled={busy} onClick={() => studio.saveNote.mutate(artifact.id, {
                  onSuccess: () => toast.success(t('已保存到个人笔记')),
                  onError: cause => error(cause, '笔记保存失败，请重试。'),
                })}><NotePencil size={15} />{t('保存为个人笔记')}</button>}
              <button type="button" className="um-agent-button" onClick={() => void copy(artifact.content_markdown)}><Copy size={15} />{t('复制 Markdown')}</button>
            </div>
            <MarkdownContent className="um-wb-artifact-markdown" content={artifact.content_markdown}
              {...workbenchCitationMarkdown(artifact.citations, citationContext)} />
          </>}
      </> : noteView ? <>
        <h3>{noteView.note ? t('编辑笔记') : t('新建笔记')}</h3>
        <StudioNoteEditor key={noteView.note?.id ?? 'new'} note={noteView.note} saving={notes.save.isPending} onBack={() => navigate(null)}
          onSave={draft => notes.save.mutate({ note: noteView.note, draft }, {
            onSuccess: note => { navigate({ note }); toast.success(t('笔记已保存')); },
            onError: cause => error(cause, '笔记保存失败，请重试。'),
          })} />
      </> : <>
        <div className="um-wb-studio-grid">
          {creationCards.map(({ kind, title, description, icon: Icon }) => <div key={kind} title={generateHint} className="um-wb-studio-action">
            <button type="button" disabled={!!generateHint || studio.generate.isPending} aria-describedby={generateHint ? 'wb-studio-source-hint' : undefined}
              onClick={() => generate(kind)} data-kind={kind}>
              <Icon size={20} weight="duotone" /><strong>{t(title)}</strong><small>{t(description)}</small>
            </button>
          </div>)}
        </div>
        {generateHint && <p id="wb-studio-source-hint" className="um-wb-muted">{generateHint}</p>}
        <section className="um-wb-studio-section">
          <h3>{t('生成记录')}</h3>
          {studio.list.isPending ? <p role="status" className="um-wb-muted">{t('正在读取生成记录…')}</p>
            : studio.list.isError ? <button type="button" className="um-agent-button" onClick={() => void studio.list.refetch()}>{t('生成记录读取失败，重试')}</button>
            : !studio.list.data.length ? <p className="um-wb-muted">{t('暂无生成记录')}</p>
            : <ul className="um-wb-studio-list">{studio.list.data.map(row => <li key={row.id}><button type="button" onClick={() => navigate({ artifactId: row.id })}>
              <Sparkle size={15} /><span>{row.kind === 'quiz' && row.title === '靶向自测' ? t('出题自测') : row.title}
                <small>{t(studioKindTitle(row.kind))}{row.status === 'generating' ? ` · ${t('生成中')}` : row.status === 'failed' ? ` · ${t('生成失败')}` : ''}</small></span><ArrowUpRight size={14} />
            </button></li>)}</ul>}
        </section>
        <section className="um-wb-studio-section">
          <h3>{t('项目笔记')}</h3>
          {notes.list.isPending ? <p role="status" className="um-wb-muted">{t('正在读取项目笔记…')}</p>
            : notes.list.isError ? <button type="button" className="um-agent-button" onClick={() => void notes.list.refetch()}>{t('项目笔记读取失败，重试')}</button>
            : !notes.list.data.length ? <p className="um-wb-muted">{t('暂无项目笔记')}</p>
            : <ul className="um-wb-studio-list">{notes.list.data.map(note => <li key={note.id}><button type="button" onClick={() => navigate({ note })}>
              <NotePencil size={15} /><span>{note.title || t('未命名笔记')}</span><ArrowUpRight size={14} />
            </button></li>)}</ul>}
        </section>
      </>}
    </div>
  </>;
}
