import type { Components } from 'react-markdown';
import { formatDuration } from '@/lib/utils';

interface CitationContext {
  course_id: number;
  segments: { id: number; start_time: number; end_time: number; text: string }[];
  visual?: { current: { video_seconds: number }; previous?: { video_seconds: number } };
}

/** Only snapshot-backed links can seek the current player. */
export function courseCitationComponents(context: unknown, courseId: number, onSeek: (seconds: number) => void): Components {
  const snapshot = context as CitationContext | undefined;
  return {
    a: ({ href, children, title, target, rel }) => {
      if (href?.startsWith('/course/') && href.includes('#segment-')) {
        const match = /^\/course\/(\d+)\?t=(\d+(?:\.\d+)?)#segment-(\d+)$/.exec(href);
        const segment = match && snapshot?.course_id === courseId && Number(match[1]) === courseId
          ? snapshot.segments?.find(item => item.id === Number(match[3]) && item.start_time === Number(match[2]))
          : undefined;
        if (!segment) return <span>{children}</span>;
        return <button type="button" className="text-primary underline underline-offset-2" title={segment.text}
          aria-label={`回看讲稿 ${formatDuration(segment.start_time)}`} onClick={() => onSeek(segment.start_time)}>
          讲稿 {formatDuration(segment.start_time)}
        </button>;
      }
      if (href?.startsWith('/course/') && href.includes('?t=')) {
        const match = /^\/course\/(\d+)\?t=(\d+(?:\.\d+)?)$/.exec(href);
        const visual = snapshot?.visual;
        const frame = match && snapshot?.course_id === courseId && Number(match[1]) === courseId
          ? [visual?.current, visual?.previous].find(item => item?.video_seconds === Number(match[2]))
          : undefined;
        if (!frame) return <span>{children}</span>;
        return <button type="button" className="text-primary underline underline-offset-2"
          aria-label={`回看画面 ${formatDuration(frame.video_seconds)}`} onClick={() => onSeek(frame.video_seconds)}>
          画面 {formatDuration(frame.video_seconds)}
        </button>;
      }
      return <a href={href} title={title} target={target} rel={rel}>{children}</a>;
    },
  };
}
