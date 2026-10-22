import { useEffect, useRef, useState } from 'react';
import { EditorContent, useEditor } from '@tiptap/react';
import type { Editor } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import Placeholder from '@tiptap/extension-placeholder';
import { Markdown } from 'tiptap-markdown';
import { NoteMath } from './NoteMath';
import { MarkdownContent } from '@/components/MarkdownContent';
import { notebookPath, notesApi, type Note, type NoteDraft, type Notebook } from '@/lib/notes';

interface Props {
  note: Note; notebooks: Notebook[]; onChange: (patch: Partial<NoteDraft>) => void;
  onOpen: (id: number) => void; onSelection: (text: string) => void;
}
export default function NoteEditor({ note, notebooks, onChange, onOpen, onSelection }: Props) {
  const [mode, setMode] = useState<'rich' | 'markdown' | 'preview'>('rich');
  const [linkQuery, setLinkQuery] = useState<{ from: number; to: number; query: string } | null>(null);
  const [tagInput, setTagInput] = useState(note.tags.join(', '));
  const [matches, setMatches] = useState<Note[]>([]);
  const [searchFailed, setSearchFailed] = useState(false);
  const changeRef = useRef(onChange);
  const selectionRef = useRef(onSelection);
  changeRef.current = onChange; selectionRef.current = onSelection;
  const editor = useEditor({
    extensions: [NoteMath, StarterKit.configure({ heading: { levels: [1, 2, 3] }, link: { openOnClick: false } }), Markdown.configure({ html: false }), Placeholder.configure({ placeholder: '记下你的理解，输入 [[ 链接另一篇笔记…' })],
    content: note.content,
    editable: !note.deleted_at,
    editorProps: { attributes: { class: 'notes-prose', 'aria-label': '笔记正文' } },
    onUpdate: ({ editor: instance }) => {
      changeRef.current({ content: (instance.storage as Editor['storage'] & { markdown: { getMarkdown: () => string } }).markdown.getMarkdown() });
      const { $from, from } = instance.state.selection;
      const match = $from.parent.textBetween(0, $from.parentOffset).match(/\[\[([^\]]*)$/);
      setLinkQuery(match ? { from: from - match[0].length, to: from, query: match[1] } : null);
    },
    onSelectionUpdate: ({ editor: instance }) => {
      const { from, to } = instance.state.selection;
      if (from !== to) selectionRef.current(instance.state.doc.textBetween(from, to, '\n').slice(0, 3000));
    },
  });
  useEffect(() => {
    if (editor && mode !== 'rich') editor.commands.setContent(note.content, { emitUpdate: false });
  }, [editor, mode, note.content]);
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
    if (mode === 'markdown') {
      const label = (target.title || '未命名笔记').replace(/[\[\]\\]/g, '\\$&');
      onChange({ content: note.content.slice(0, linkQuery.from) + `[${label}](/notes/${target.id})` + note.content.slice(linkQuery.to) });
      setLinkQuery(null); return;
    }
    editor.chain().focus().insertContentAt({ from: linkQuery.from, to: linkQuery.to }, [{ type: 'text', text: target.title || '未命名笔记', marks: [{ type: 'link', attrs: { href: `/notes/${target.id}` } }] }]).run();
    setLinkQuery(null);
  };
  const toolbar = (label: string, action: () => void, active = false) => <button type="button" aria-pressed={active} onMouseDown={e => e.preventDefault()} onClick={action}>{label}</button>;
  return <>
    <div className="notes-editor-meta">
      <select aria-label="所属笔记本" value={note.notebook ?? ''} disabled={!!note.deleted_at} onChange={e => onChange({ notebook: e.target.value ? Number(e.target.value) : null })}>
        <option value="">未分类</option>{notebooks.map(book => <option key={book.id} value={book.id}>{notebookPath(book.id, notebooks)}</option>)}
      </select>
      <button type="button" aria-pressed={note.is_favorite} disabled={!!note.deleted_at} onClick={() => onChange({ is_favorite: !note.is_favorite })}>{note.is_favorite ? '★ 已收藏' : '☆ 收藏'}</button>
    </div>
    <input className="notes-title" aria-label="笔记标题" placeholder="未命名笔记" value={note.title} readOnly={!!note.deleted_at} onChange={e => onChange({ title: e.target.value })} />
    <label className="notes-tags">标签<input aria-label="笔记标签，逗号分隔" placeholder="添加标签，用逗号分隔" value={tagInput} disabled={!!note.deleted_at} onChange={e => { setTagInput(e.target.value); onChange({ tags: [...new Set(e.target.value.split(/[,，]/).map(t => t.trim()).filter(Boolean))] }); }} /></label>
    <div className="notes-editor-toolbar">
      <div role="group" aria-label="编辑模式">{(['rich', 'markdown', 'preview'] as const).map(value => <button type="button" key={value} aria-pressed={mode === value} onClick={() => { setMode(value); setLinkQuery(null); }}>{({ rich: '编辑', markdown: 'Markdown', preview: '预览' })[value]}</button>)}</div>
      {mode === 'rich' && editor && !note.deleted_at && <div role="group" aria-label="文字格式">
        {toolbar('粗体', () => { editor.chain().focus().toggleBold().run(); }, editor.isActive('bold'))}
        {toolbar('斜体', () => { editor.chain().focus().toggleItalic().run(); }, editor.isActive('italic'))}
        {toolbar('标题', () => { editor.chain().focus().toggleHeading({ level: 2 }).run(); }, editor.isActive('heading'))}
        {toolbar('列表', () => { editor.chain().focus().toggleBulletList().run(); })}
        {toolbar('编号', () => { editor.chain().focus().toggleOrderedList().run(); })}
        {toolbar('引用', () => { editor.chain().focus().toggleBlockquote().run(); })}
        {toolbar('代码', () => { editor.chain().focus().toggleCodeBlock().run(); })}
        {toolbar('链接', () => { const href = window.prompt('链接地址（内部链接可输入 /notes/笔记ID）', editor.getAttributes('link').href || 'https://'); if (href) editor.chain().focus().extendMarkRange('link').setLink({ href }).run(); })}
        {toolbar('公式', () => { const latex = window.prompt('输入 LaTeX 公式（也可在 Markdown 模式编辑 $…$ 或 $$…$$）', editor.getAttributes('noteMath').latex || 'x^2'); if (latex) editor.chain().focus().insertContent({ type: 'noteMath', attrs: { latex, delimiter: '$' } }).run(); })}
        {toolbar('撤销', () => { editor.chain().focus().undo().run(); })}
      </div>}
    </div>
    <div className="notes-editor-body" onClick={event => {
      const anchor = (event.target as HTMLElement).closest('a');
      const match = anchor?.getAttribute('href')?.match(/^\/notes\/(\d+)$/);
      if (match) { event.preventDefault(); if (mode === 'preview' || event.metaKey || event.ctrlKey) onOpen(Number(match[1])); }
    }}>
      {mode === 'rich' && <EditorContent editor={editor} />}
      {mode === 'markdown' && <textarea className="notes-markdown" aria-label="Markdown 正文" value={note.content} readOnly={!!note.deleted_at} onChange={e => { onChange({ content: e.target.value }); const to = e.target.selectionStart; const match = e.target.value.slice(0, to).match(/\[\[([^\]]*)$/); setLinkQuery(match ? { from: to - match[0].length, to, query: match[1] } : null); }} onSelect={e => { const input = e.currentTarget; if (input.selectionEnd > input.selectionStart) onSelection(input.value.slice(input.selectionStart, input.selectionEnd).slice(0, 3000)); }} />}
      {mode === 'preview' && <MarkdownContent content={note.content || '还没有正文。'} className="notes-prose" />}
      {mode !== 'preview' && linkQuery && <div className="notes-link-picker" role="dialog" aria-label="链接笔记">
        <div className="notes-row"><strong>链接到笔记</strong><button onClick={() => setLinkQuery(null)}>关闭</button></div>
        <input autoFocus aria-label="搜索链接笔记" placeholder="搜索标题或正文" value={linkQuery.query} onChange={e => setLinkQuery({ ...linkQuery, query: e.target.value })} />
        {matches.slice(0, 12).map(target => <button key={target.id} onClick={() => insertLink(target)}><span>{target.title || '未命名笔记'}</span><small>{notebookPath(target.notebook, notebooks)}</small></button>)}
        {!matches.length && <p>{searchFailed ? '搜索失败，请重试。' : '没有匹配的笔记。'}</p>}
      </div>}
    </div>
    <div className="notes-backlinks"><span>反向链接 · {note.backlinks.length}</span>{note.backlinks.map(link => <button key={link.id} onClick={() => onOpen(link.id)}>{link.title || '未命名笔记'}</button>)}</div>
  </>;
}
