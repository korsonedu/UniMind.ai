import React, { useState, useEffect, useCallback, useRef } from 'react';
import { ClosedCaption, Loader2 } from 'lucide-react';
import { useCourseAIStore } from '@/store/useCourseAIStore';
import { cn } from '@/lib/utils';

interface SubtitlesOverlayProps {
  courseId: number;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  visible?: boolean;
}

export const SubtitlesOverlay: React.FC<SubtitlesOverlayProps> = ({
  courseId,
  videoRef,
  visible: initialVisible = false,
}) => {
  const { transcriptStatus, transcriptSegments, fetchTranscript, triggerTranscription } =
    useCourseAIStore();
  const [visible, setVisible] = useState(initialVisible);
  const activeIdxRef = useRef(-1);
  const [, forceRender] = useState(0);
  const autoTriggeredRef = useRef(false);

  useEffect(() => {
    fetchTranscript(courseId);
  }, [courseId, fetchTranscript]);

  // 旧课程自动触发转录
  useEffect(() => {
    if (transcriptStatus === 'unavailable' && !autoTriggeredRef.current) {
      autoTriggeredRef.current = true;
      triggerTranscription(courseId);
    }
  }, [transcriptStatus, courseId, triggerTranscription]);

  // Sync subtitle index with video time
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

  const toggle = useCallback(() => setVisible((v) => !v), []);

  if (transcriptStatus === 'unavailable') return null;

  const activeIdx = activeIdxRef.current;

  return (
    <>
      <button
        onClick={toggle}
        className={cn(
          'absolute top-3 right-3 z-10 flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider backdrop-blur-md transition-all',
          visible
            ? 'bg-white/90 text-indigo-600 shadow-sm'
            : 'bg-black/40 text-white/70 hover:bg-black/60',
        )}
      >
        {transcriptStatus === 'loading' ? (
          <Loader2 className="h-3 w-3 animate-spin" />
        ) : (
          <ClosedCaption className="h-3 w-3" />
        )}
        智能字幕
      </button>

      {visible && activeIdx >= 0 && (
        <div className="absolute bottom-16 left-1/2 -translate-x-1/2 z-10 max-w-[85%]">
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
      )}
    </>
  );
};
