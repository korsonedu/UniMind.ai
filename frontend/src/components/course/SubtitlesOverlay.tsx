import { useEffect } from 'react';
import { activeTranscriptSegment, useCourseAIStore } from '@/store/useCourseAIStore';

interface SubtitlesOverlayProps {
  courseId: number;
  currentTime: number;
  visible?: boolean;
}

export function SubtitlesOverlay({
  courseId,
  currentTime,
  visible = false,
}: SubtitlesOverlayProps) {
  const { transcriptCourseId, transcriptSegments, fetchTranscript, clearCourseTimers } =
    useCourseAIStore();

  useEffect(() => {
    fetchTranscript(courseId);
    return () => { clearCourseTimers(courseId); };
  }, [courseId, fetchTranscript, clearCourseTimers]);

  if (!visible || transcriptCourseId !== courseId) return null;
  const segment = activeTranscriptSegment(transcriptSegments, currentTime);
  if (!segment) return null;

  return (
    <div className="absolute bottom-12 left-1/2 -translate-x-1/2 z-10 max-w-[85%]">
      <p
        className="text-center text-sm md:text-base font-medium text-white leading-relaxed drop-shadow-lg"
        style={{
          textShadow:
            '0 1px 3px rgba(0,0,0,0.8), 0 0 8px rgba(0,0,0,0.6)',
        }}
      >
        {segment.text}
      </p>
    </div>
  );
}
