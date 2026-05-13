import React, { useEffect, useState, useCallback } from 'react';
import { Loader2, Clock, ChevronDown, ChevronUp, Sparkles } from 'lucide-react';
import { useCourseAIStore } from '@/store/useCourseAIStore';
import { cn, formatDuration } from '@/lib/utils';

interface OutlinePanelProps {
  courseId: number;
  videoRef: React.RefObject<HTMLVideoElement | null>;
}

export const OutlinePanel: React.FC<OutlinePanelProps> = ({ courseId, videoRef }) => {
  const { outlineStatus, outlineItems, fetchOutline } = useCourseAIStore();
  const [expanded, setExpanded] = useState(true);

  useEffect(() => {
    fetchOutline(courseId);
  }, [courseId, fetchOutline]);

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
      <div className="flex items-center gap-2 py-2 text-muted-foreground/60">
        <Loader2 className="h-3 w-3 animate-spin" />
        <span className="text-[10px] font-bold uppercase tracking-wider">AI 正在分析课程内容…</span>
      </div>
    );
  }

  if (outlineStatus === 'unavailable' || outlineItems.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors"
      >
        <Sparkles className="h-3 w-3 text-indigo-500" />
        AI 智能大纲 ({outlineItems.length} 章节)
        {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
      </button>

      {expanded && (
        <div className="space-y-1 pl-1">
          {outlineItems.map((item) => (
            <button
              key={item.index}
              onClick={() => handleSeek(item.timestamp)}
              className={cn(
                'w-full text-left p-2.5 rounded-xl',
                'hover:bg-muted/50 transition-colors group',
              )}
            >
              <div className="flex items-center gap-3">
                <span className="shrink-0 text-[10px] font-bold text-indigo-500 bg-indigo-50 px-1.5 py-0.5 rounded-md tabular-nums">
                  {formatDuration(item.timestamp)}
                </span>
                <span className="text-xs font-bold text-foreground leading-snug group-hover:text-indigo-600 transition-colors">
                  {item.title}
                </span>
              </div>
              {item.description && (
                <p className="text-[10px] text-muted-foreground/60 mt-0.5 ml-[52px] line-clamp-2 leading-relaxed">
                  {item.description}
                </p>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
