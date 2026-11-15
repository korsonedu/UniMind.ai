import { t, useLocale } from '@/i18n';
import { Link } from 'react-router-dom';
import { FileText } from '@phosphor-icons/react';

export function NoteAttachments({ attachments }: { attachments: unknown }) {
  useLocale();
  if (!Array.isArray(attachments)) return null;
  const notes = attachments.filter((item): item is { note_id: number; title: string; version: number } => !!item && Number.isInteger(item.note_id) && typeof item.title === 'string' && Number.isInteger(item.version));
  return !notes.length ? null : <div className="note-mention-chips note-message-attachments">{notes.map(note => <Link className="note-mention-chip" key={note.note_id} to={`/notes/${note.note_id}`} title={t('发送时版本 v{0}', { 0: note.version })}><FileText size={14} />{note.title || t('未命名笔记')}</Link>)}</div>;
}
