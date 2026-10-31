import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { EditorContent, useEditor } from '@tiptap/react';
import type { Editor } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import Placeholder from '@tiptap/extension-placeholder';
import { Markdown } from 'tiptap-markdown';
import { ArrowUUpLeft, CodeBlock, Function as FunctionIcon, Link as LinkIcon, ListBullets, ListNumbers, Quotes, Star, Tag, TextB, TextH, TextItalic, X } from '@phosphor-icons/react';
import { NoteMath } from './NoteMath';
import NoteDialog, { type NoteDialogOptions } from './NoteDialog';
import { notebookPath, notesApi, type Note, type NoteDraft, type Notebook } from '@/lib/notes';

interface Props {
  note: Note; notebooks: Notebook[]; onChange: (patch: Partial<NoteDraft>) => void;
  onOpen: (id: number) => void;
}
export default function NoteEditor({ note, notebooks, onChange, onOpen }: Props) {
  const [dialog, setDialog] = useState<NoteDialogOptions | null>(null);
  const [linkQuery, setLinkQuery] = useState<{ from: number; to: number; query: string } | null>(null);
  const [tagInput, setTagInput] = useState(note.tags.join(', '));
  const [matches, setMatches] = useState<Note[]>([]);
  const [searchFailed, setSearchFailed] = useState(false);
  const changeRef = useRef(onChange);
  useLayoutEffect(() => { changeRef.current = onChange; }, [onChange]);
  const editor = useEditor({
    extensions: [NoteMath, StarterKit.configure({ heading: { levels: [1, 2, 3] }, link: { openOnClick: false } }), Markdown.configure({ html: false }), Placeholder.configure({ placeholder: '开始书写…' })],
    content: note.content,
    editable: !note.deleted_at,
    editorProps: { attributes: { class: 'notes-prose', 'aria-label': '笔记正文' } },
    onUpdate: ({ editor: instance }) => {
      changeRef.current({ content: (instance.storage as Editor['storage'] & { markdown: { getMarkdown: () => string } }).markdown.getMarkdown() });
      const { $from, from } = instance.state.selection;
      const match = $from.parent.textBetween(0, $from.parentOffset).match(/\[\[([^\]]*)$/);
      setLinkQuery(match ? { from: from - match[0].length, to: from, query: match[1] } : null);
    },
  });
  useEffect(() => {
    if (!linkQuery) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setSearchFailed(false);
      void notesApi.list({ q: linkQuery.query }, controller.signal).then(setMatches).catch(() => { if (!controller.signal.aborted) { setMatches([]); setSearchFailed(true); } });
    }, 180);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [linkQuery]);
  const insertLink = (target: Note) => {
    if (!editor || !linkQuery) return;
    editor.chain().focus().insertContentAt({ from: linkQuery.from, to: linkQuery.to }, [{ type: 'text', text: target.title || '未命名笔记', marks: [{ type: 'link', attrs: { href: `/notes/${target.id}` } }] }]).run();
    setLinkQuery(null);
  };
  const toolbar = (label: string, icon: React.ReactNode, action: () => void, active = false) => <button type="button" className="notes-icon-button" aria-label={label} title={label} aria-pressed={active} onMouseDown={e => e.preventDefault()} onClick={action}>{icon}</button>;
  return <>
    <div className="notes-editor-meta">
      <select aria-label="所属笔记本" value={note.notebook ?? ''} disabled={!!note.deleted_at} onChange={e => onChange({ notebook: e.target.value ? Number(e.target.value) : null })}>
        <option value="">未分类</option>{notebooks.map(book => <option key={book.id} value={book.id}>{notebookPath(book.id, notebooks)}</option>)}
      </select>
      <button type="button" className="notes-icon-button" aria-label={note.is_favorite ? '取消收藏' : '收藏'} title={note.is_favorite ? '取消收藏' : '收藏'} aria-pressed={note.is_favorite} disabled={!!note.deleted_at} onClick={() => onChange({ is_favorite: !note.is_favorite })}><Star size={18} weight={note.is_favorite ? 'fill' : 'regular'} /></button>
    </div>
    <input className="notes-title" aria-label="笔记标题" placeholder="未命名笔记" value={note.title} readOnly={!!note.deleted_at} onChange={e => onChange({ title: e.target.value })} />
    <label className="notes-tags"><Tag size={16} /><input aria-label="笔记标签，逗号分隔" placeholder="标签" value={tagInput} disabled={!!note.deleted_at} onChange={e => { setTagInput(e.target.value); onChange({ tags: [...new Set(e.target.value.split(/[,，]/).map(t => t.trim()).filter(Boolean))] }); }} /></label>
    <div className="notes-editor-toolbar">
      {editor && !note.deleted_at && <div role="group" aria-label="文字格式">
        {toolbar('粗体', <TextB size={18} />, () => { editor.chain().focus().toggleBold().run(); }, editor.isActive('bold'))}
        {toolbar('斜体', <TextItalic size={18} />, () => { editor.chain().focus().toggleItalic().run(); }, editor.isActive('italic'))}
        {toolbar('标题', <TextH size={18} />, () => { editor.chain().focus().toggleHeading({ level: 2 }).run(); }, editor.isActive('heading'))}
        {toolbar('列表', <ListBullets size={18} />, () => { editor.chain().focus().toggleBulletList().run(); }, editor.isActive('bulletList'))}
        {toolbar('编号', <ListNumbers size={18} />, () => { editor.chain().focus().toggleOrderedList().run(); }, editor.isActive('orderedList'))}
        {toolbar('引用', <Quotes size={18} />, () => { editor.chain().focus().toggleBlockquote().run(); }, editor.isActive('blockquote'))}
        {toolbar('代码', <CodeBlock size={18} />, () => { editor.chain().focus().toggleCodeBlock().run(); }, editor.isActive('codeBlock'))}
        {toolbar('链接', <LinkIcon size={18} />, () => setDialog({ title: '链接地址', initialValue: editor.getAttributes('link').href || 'https://', onConfirm: href => { editor.chain().focus().extendMarkRange('link').setLink({ href }).run(); } }))}
        {toolbar('公式', <FunctionIcon size={18} />, () => setDialog({ title: 'LaTeX 公式', initialValue: editor.getAttributes('noteMath').latex || 'x^2', onConfirm: latex => { editor.chain().focus().insertContent({ type: 'noteMath', attrs: { latex, delimiter: '$' } }).run(); } }))}
        {toolbar('撤销', <ArrowUUpLeft size={18} />, () => { editor.chain().focus().undo().run(); })}
      </div>}
    </div>
    <div className="notes-editor-body" onClick={event => {
      const anchor = (event.target as HTMLElement).closest('a');
      const match = anchor?.getAttribute('href')?.match(/^\/notes\/(\d+)$/);
      if (match) { event.preventDefault(); if (event.metaKey || event.ctrlKey) onOpen(Number(match[1])); }
    }}>
      <EditorContent editor={editor} />
      {linkQuery && <div className="notes-link-picker" role="dialog" aria-label="链接笔记">
        <div className="notes-row"><strong>链接到笔记</strong><button aria-label="关闭链接搜索" title="关闭" onClick={() => setLinkQuery(null)}><X size={16} /></button></div>
        <input autoFocus aria-label="搜索链接笔记" placeholder="搜索标题或正文" value={linkQuery.query} onChange={e => setLinkQuery({ ...linkQuery, query: e.target.value })} />
        {matches.slice(0, 12).map(target => <button key={target.id} onClick={() => insertLink(target)}><span>{target.title || '未命名笔记'}</span><small>{notebookPath(target.notebook, notebooks)}</small></button>)}
        {!matches.length && <p>{searchFailed ? '搜索失败，请重试。' : '没有匹配的笔记。'}</p>}
      </div>}
    </div>
    <div className="notes-backlinks"><span>反向链接 · {note.backlinks.length}</span>{note.backlinks.map(link => <button key={link.id} onClick={() => onOpen(link.id)}>{link.title || '未命名笔记'}</button>)}</div>
    {dialog && <NoteDialog {...dialog} onClose={() => setDialog(null)} />}
  </>;
}
