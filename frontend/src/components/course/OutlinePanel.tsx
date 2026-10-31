import React, { useEffect, useCallback, useRef } from 'react';
import { Spinner } from '@phosphor-icons/react';
import { useCourseAIStore } from '@/store/useCourseAIStore';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import { formatDuration } from '@/lib/utils';

interface OutlinePanelProps {
  courseId: number;
  videoRef: React.RefObject<HTMLVideoElement | null>;
}

export const OutlinePanel: React.FC<OutlinePanelProps> = ({ courseId, videoRef }) => {
  const { outlineStatus, outlineItems, fetchOutline, triggerOutlineGeneration, clearCourseTimers } = useCourseAIStore();
  const autoTriggeredRef = useRef(false);
  const canGenerate = useInstitutionStore(state => state.features.includes('video.outline'));

  useEffect(() => {
    fetchOutline(courseId);
    return () => { clearCourseTimers(courseId); };
  }, [courseId, fetchOutline, clearCourseTimers]);

  // 旧课程自动触发生成
  useEffect(() => {
    if (canGenerate && outlineStatus === 'unavailable' && !autoTriggeredRef.current) {
      autoTriggeredRef.current = true;
      triggerOutlineGeneration(courseId);
    }
  }, [canGenerate, outlineStatus, courseId, triggerOutlineGeneration]);

  const handleSeek = useCallback(
    (seconds: number) => {
      if (videoRef.current) {
        videoRef.current.currentTime = seconds;
        videoRef.current.play().catch(() => {});
      }
    },
    [videoRef],
  );

  if (outlineStatus === 'idle' || outlineStatus === 'loading') {
    return (
      <div className="um-lesson-outline-status" role="status">
        <Spinner size={16} className="animate-spin" />
        <span>正在整理课程大纲…</span>
      </div>
    );
  }

  if (outlineStatus === 'unavailable' || outlineItems.length === 0) {
    return <p className="um-lesson-empty">暂无课程大纲</p>;
  }

  return (
    <div className="um-lesson-outline">
      <p className="um-lesson-outline-count">{outlineItems.length} 个章节</p>
      <ol className="um-lesson-outline-items">
        {outlineItems.map((item) => (
          <li key={item.index}><button onClick={() => handleSeek(item.timestamp)} aria-label={`${formatDuration(item.timestamp)} ${item.title}`}>
            <time>{formatDuration(item.timestamp)}</time><span>{item.title}</span>
            {item.description && <small>{item.description}</small>}
          </button></li>
        ))}
      </ol>
    </div>
  );
};
