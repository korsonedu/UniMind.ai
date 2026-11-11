import type { Components } from 'react-markdown';
import { Link } from 'react-router-dom';
import { learningUrl } from '@/lib/projectLearning';

/** Keep only same-origin course navigation inside the current learning project. */
export function projectCourseLinks(projectId: number | null, conversationId: string, citations?: Components, currentCourseId?: number): Components {
  return {
    a: ({ href, children, title, target, rel, ...props }) => {
      let url: URL | undefined;
      try { if (href) url = new URL(href, window.location.href); } catch { /* Keep malformed links as ordinary Markdown output. */ }
      if (projectId && url?.origin === window.location.origin && /^\/course\/\d+\/?$/.test(url.pathname)) {
        const coursePath = url.pathname + url.search + url.hash;
        if (Number(url.pathname.split('/')[2]) === currentCourseId && (url.searchParams.has('t') || url.hash.startsWith('#segment-'))) {
          const Citation = citations?.a;
          if (typeof Citation === 'function') return <Citation {...props} href={coursePath} title={title} target={target} rel={rel}>{children}</Citation>;
        }
        return <Link to={learningUrl(coursePath, projectId, conversationId)} title={title}>{children}</Link>;
      }
      const Citation = citations?.a;
      return typeof Citation === 'function' ? <Citation {...props} href={href} title={title} target={target} rel={rel}>{children}</Citation> : <a href={href} title={title} target={target} rel={rel}>{children}</a>;
    },
  };
}
