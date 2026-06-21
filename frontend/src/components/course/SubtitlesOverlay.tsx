import React, { useState, useEffect, useRef } from 'react';
import { useCourseAIStore } from '@/store/useCourseAIStore';

interface SubtitlesOverlayProps {
  courseId: number;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  visible?: boolean;
}

export const SubtitlesOverlay: React.FC<SubtitlesOverlayProps> = ({
  courseId,
  videoRef,
  visible = false,
}) => {
  const { transcriptStatus, transcriptSegments, fetchTranscript, triggerTranscription, clearCourseTimers } =
    useCourseAIStore();
  const activeIdxRef = useRef(-1);
  const [, forceRender] = useState(0);
  const autoTriggeredRef = useRef(false);

  useEffect(() => {
    fetchTranscript(courseId);
    return () => { clearCourseTimers(courseId); };
  }, [courseId, fetchTranscript, clearCourseTimers]);

  useEffect(() => {
    if (transcriptStatus === 'unavailable' && !autoTriggeredRef.current) {
      autoTriggeredRef.current = true;
      triggerTranscription(courseId);
    }
  }, [transcriptStatus, courseId, triggerTranscription]);

  useEffect(() => {
    if (!visible || transcriptSegments.length === 0) return;
    const video = videoRef.current;
    if (!video) return;

    let raf = 0;
    const tick = () => {
      if (video.paused) { raf = requestAnimationFrame(tick); return; }
      const t = video.currentTime;
      let found = -1;
      for (let i = 0; i < transcriptSegments.length; i++) {
        if (t >= transcriptSegments[i].start && t <= transcriptSegments[i].end) {
          found = i;
          break;
        }
      }
      if (found !== activeIdxRef.current) {
        activeIdxRef.current = found;
        forceRender((n) => n + 1);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [visible, transcriptSegments, videoRef]);

  if (!visible || activeIdxRef.current < 0) return null;

  const activeIdx = activeIdxRef.current;

  return (
    <div className="absolute bottom-12 left-1/2 -translate-x-1/2 z-10 max-w-[85%]">
      <p
        className="text-center text-sm md:text-base font-medium text-white leading-relaxed drop-shadow-lg"
        style={{
          textShadow:
            '0 1px 3px rgba(0,0,0,0.8), 0 0 8px rgba(0,0,0,0.6)',
        }}
      >
        {transcriptSegments[activeIdx]?.text}
      </p>
    </div>
  );
};
