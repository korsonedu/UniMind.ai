import { t, useLocale } from '@/i18n';
import React, { useEffect, useCallback, useRef } from 'react';
import { Spinner } from '@phosphor-icons/react';
import { activeTranscriptSegment, useCourseAIStore } from '@/store/useCourseAIStore';
import { formatDuration } from '@/lib/utils';

interface OutlinePanelProps {
  courseId: number;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  enabled?: boolean;
  currentTime?: number;
  visible?: boolean;
  onSeek?: (seconds: number) => void;
}

export const OutlinePanel: React.FC<OutlinePanelProps> = ({ courseId, videoRef, enabled = true, currentTime, visible, onSeek }) => {
  useLocale();
  const { outlineStatus, outlineItems, fetchOutline, clearCourseTimers, transcriptCourseId, transcriptSegments } = useCourseAIStore();

  useEffect(() => {
    if (!enabled) return;
    fetchOutline(courseId);
    return () => { clearCourseTimers(courseId); };
  }, [courseId, enabled, fetchOutline, clearCourseTimers]);

  const handleSeek = useCallback(
    (seconds: number) => {
      if (onSeek) onSeek(seconds);
      else if (videoRef.current) {
        videoRef.current.currentTime = seconds;
        videoRef.current.play().catch(() => {});
      }
    },
    [onSeek, videoRef],
  );

  const segments = currentTime !== undefined && transcriptCourseId === courseId ? transcriptSegments : [];
  const activeSegment = currentTime === undefined ? undefined : activeTranscriptSegment(segments, currentTime)?.index;
  const activeChapter = enabled && outlineStatus === 'available' && currentTime !== undefined
    ? [...outlineItems].reverse().find(item => item.timestamp <= currentTime)?.index : undefined;
  const activeCaptionRef = useRef<HTMLButtonElement>(null);
  const activeChapterRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (visible) (activeCaptionRef.current ?? activeChapterRef.current)?.scrollIntoView({ block: 'nearest' });
  }, [visible, activeSegment, activeChapter]);

  const loading = enabled && (outlineStatus === 'idle' || outlineStatus === 'loading') && (
    <div className="um-lesson-outline-status" role="status">
      <Spinner size={16} className="animate-spin" />
      <span>{t('正在整理课程大纲…')}</span>
    </div>
  );
  if (loading && !segments.length) return loading;
  if (enabled && !segments.length && (outlineStatus === 'unavailable' || outlineItems.length === 0)) {
    return <p className="um-lesson-empty">{t('暂无课程大纲')}</p>;
  }

  return <div className="um-lesson-outline">
    {loading}
    {enabled && outlineStatus === 'available' && outlineItems.length > 0 && <>
      <p className="um-lesson-outline-count">{outlineItems.length} {t('个章节')}</p>
      <ol className="um-lesson-outline-items">
        {outlineItems.map(item => (
          <li key={item.index}><button ref={item.index === activeChapter ? activeChapterRef : undefined}
            aria-current={item.index === activeChapter ? 'true' : undefined}
            onClick={() => handleSeek(item.timestamp)} aria-label={`${formatDuration(item.timestamp)} ${item.title}`}>
            <time>{formatDuration(item.timestamp)}</time><span>{item.title}</span>
            {item.description && <small>{item.description}</small>}
          </button></li>
        ))}
      </ol>
    </>}
    {!enabled && segments.length === 0 && <p className="um-lesson-empty">{t('本课程暂无大纲')}</p>}
    {segments.length > 0 && <>
      <h3 className="um-lesson-outline-count">{t('字幕')}</h3>
      <ol className="um-lesson-outline-items um-lesson-transcript">
        {segments.map(segment => <li key={segment.index}><button ref={segment.index === activeSegment ? activeCaptionRef : undefined}
          aria-current={segment.index === activeSegment ? 'true' : undefined} onClick={() => handleSeek(segment.start)}>
          <time>{formatDuration(segment.start)}</time><span>{segment.text}</span>
        </button></li>)}
      </ol>
    </>}
  </div>;
};
