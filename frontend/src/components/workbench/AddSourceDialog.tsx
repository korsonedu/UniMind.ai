import { useRef, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import * as Tabs from '@radix-ui/react-tabs';
import { ArrowUpRight, BookOpen, LinkSimple, MagnifyingGlass, UploadSimple, X } from '@phosphor-icons/react';
import { t } from '@/i18n';
import { useWorkbenchCourses } from '@/lib/workbenchApi';

const extensions = ['.pdf', '.pptx', '.docx', '.md', '.txt', '.mp4', '.mov', '.webm', '.mp3', '.m4a', '.wav'];
const acceptedSourceFiles = extensions.join(',');

export function AddSourceDialog({ projectId, open, setOpen, pending, uploading, error, courseIds, onUpload, onUrl, onCourse }: {
  projectId: number;
  open: boolean;
  setOpen: (open: boolean) => void;
  pending: boolean;
  uploading: number | null;
  error: string;
  courseIds: Set<number | null>;
  onUpload: (files: File[]) => void;
  onUrl: (url: string) => void;
  onCourse: (id: number) => void;
}) {
  return <Dialog.Root open={open} onOpenChange={next => { if (!pending) setOpen(next); }}>
    <Dialog.Portal>
      <Dialog.Overlay className="um-agent-project-overlay" />
      <Dialog.Content className="um-native-agent um-agent-project-dialog um-wb-dialog">
        <div className="um-wb-dialog-title">
          <Dialog.Title>{t('添加资料')}</Dialog.Title>
          <Dialog.Close asChild><button className="um-agent-icon-button" aria-label={t('关闭')} disabled={pending}><X size={17} /></button></Dialog.Close>
        </div>
        <Dialog.Description>{t('选择课件、音视频、网页或站内课程。')}</Dialog.Description>
        <SourcePicker projectId={projectId} pending={pending} courseIds={courseIds} onUpload={onUpload} onUrl={onUrl} onCourse={onCourse} />
        {uploading !== null && <div className="um-wb-progress" role="status">
          <progress value={uploading} max={100} aria-label={t('上传进度')} />
          <span>{uploading === 100 ? t('已上传，等待服务器处理…') : t('正在上传 {0}%', { 0: uploading })}</span>
        </div>}
        {error && <p className="um-wb-error" role="alert">{error}</p>}
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}

function SourcePicker({ projectId, pending, courseIds, onUpload, onUrl, onCourse }: {
  projectId: number;
  pending: boolean;
  courseIds: Set<number | null>;
  onUpload: (files: File[]) => void;
  onUrl: (url: string) => void;
  onCourse: (id: number) => void;
}) {
  const [tab, setTab] = useState('file');
  const [url, setUrl] = useState('');
  const [search, setSearch] = useState('');
  const [inputError, setInputError] = useState('');
  const input = useRef<HTMLInputElement>(null);
  const courses = useWorkbenchCourses(projectId, search.trim(), tab === 'course');
  const rows = courses.data?.pages.flatMap(page => page.items) ?? [];

  return <Tabs.Root value={tab} onValueChange={value => { setTab(value); setInputError(''); }}>
    <Tabs.List className="um-wb-segments" aria-label={t('添加方式')}>
      <Tabs.Trigger value="file" disabled={pending}><UploadSimple size={16} />{t('本地上传')}</Tabs.Trigger>
      <Tabs.Trigger value="url" disabled={pending}><LinkSimple size={16} />{t('网页链接')}</Tabs.Trigger>
      <Tabs.Trigger value="course" disabled={pending}><BookOpen size={16} />{t('站内课程')}</Tabs.Trigger>
    </Tabs.List>
    <Tabs.Content value="file" className="um-wb-picker">
      <button type="button" className="um-wb-dropzone" disabled={pending} onClick={() => input.current?.click()}
        onDragOver={event => event.preventDefault()}
        onDrop={event => { event.preventDefault(); if (!pending && event.dataTransfer.files.length) onUpload(Array.from(event.dataTransfer.files)); }}>
        <UploadSimple size={23} />
        <strong>{t('选择文件或拖到这里')}</strong>
        <span>PDF、PPTX、DOCX、MD、TXT、MP4、MOV、WEBM、MP3、M4A、WAV</span>
      </button>
      <input ref={input} type="file" hidden multiple accept={acceptedSourceFiles} onChange={event => {
        if (event.target.files?.length) onUpload(Array.from(event.target.files));
        event.target.value = '';
      }} />
    </Tabs.Content>
    <Tabs.Content value="url" className="um-wb-picker">
      <form onSubmit={event => {
        event.preventDefault();
        const link = URL.canParse(url.trim()) ? new URL(url.trim()) : null;
        if (link?.protocol !== 'https:' || link.username || link.password) {
          setInputError(t('请输入公开的 HTTPS 链接。'));
          return;
        }
        setInputError('');
        onUrl(link.href);
      }}>
        <label>{t('公开网页地址')}<input type="url" required maxLength={3000} placeholder="https://example.com/article"
          value={url} disabled={pending} onChange={event => { setUrl(event.target.value); setInputError(''); }} /></label>
        {inputError && <p className="um-wb-error" role="alert">{inputError}</p>}
        <button type="submit" className="um-agent-button um-agent-button-primary" disabled={pending || !url.trim()}>{t('导入网页')}</button>
      </form>
    </Tabs.Content>
    <Tabs.Content value="course" className="um-wb-picker">
      <label className="um-wb-course-search"><MagnifyingGlass size={17} /><input type="search" aria-label={t('搜索站内课程')}
        placeholder={t('按课程名称搜索')} value={search} onChange={event => setSearch(event.target.value)} /></label>
      {courses.isPending && <p role="status" className="um-wb-muted">{t('正在加载课程…')}</p>}
      {courses.isError && <button className="um-agent-button" onClick={() => void courses.refetch()}>{t('课程加载失败，重试')}</button>}
      {courses.isSuccess && !rows.length && <p className="um-wb-muted">{t('没有匹配的课程')}</p>}
      <ul className="um-wb-course-list">{rows.map(course => <li key={course.id}>
        <button type="button" disabled={pending || courseIds.has(course.id)} onClick={() => onCourse(course.id)}>
          <BookOpen size={17} /><span>{course.title}</span>
          {courseIds.has(course.id) ? <small>{t('已导入')}</small> : <ArrowUpRight size={15} />}
        </button>
      </li>)}</ul>
      {courses.hasNextPage && <button className="um-agent-button" disabled={courses.isFetchingNextPage} onClick={() => void courses.fetchNextPage()}>{t('加载更多课程')}</button>}
    </Tabs.Content>
  </Tabs.Root>;
}
