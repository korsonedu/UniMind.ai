import type { Components } from 'react-markdown';
import { Link } from 'react-router-dom';
import { learningUrl } from '@/lib/projectLearning';

function sameOriginCourseUrl(href?: string) {
  try {
    const url = href ? new URL(href, window.location.href) : null;
    return url?.origin === window.location.origin && /^\/course\/\d+\/?$/.test(url.pathname) ? url : null;
  } catch { return null; }
}

export function projectCoursePath(href: string, projectId?: number | null, conversationId?: string) {
  if (!projectId) return null;
  const url = sameOriginCourseUrl(href);
  return url ? learningUrl(url.pathname + url.search + url.hash, projectId, conversationId) : null;
}

/** Keep only same-origin course navigation inside the current learning project. */
export function projectCourseLinks(projectId: number | null, conversationId: string, citations?: Components, currentCourseId?: number): Components {
  return {
    a: ({ href, children, title, target, rel, ...props }) => {
      const url = sameOriginCourseUrl(href);
      if (projectId && url) {
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
