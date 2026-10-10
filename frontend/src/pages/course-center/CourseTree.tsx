import { useId, useState } from 'react';
import type { ReactNode } from 'react';
import { CaretRight as ChevronRight, MagnifyingGlass as Search } from '@phosphor-icons/react';
import { matchesSearch, type Course, type CourseGrouping } from './types';

export interface CourseTreeProps {
  courses: Course[];
  treeCourses: Course[];
  selectedId?: number;
  loading: boolean;
  error: string;
  query: string;
  grouping: CourseGrouping;
  filter: string;
  tag: string;
  status: string;
  scope: string;
  onQueryChange: (value: string) => void;
  onFilter: (value: string, grouping?: CourseGrouping) => void;
  onFacet: (key: 'tag' | 'status' | 'scope', value: string) => void;
  onSelect: (course: Course) => void;
  onRetry: () => void;
  onPublish?: () => void;
  extraFilters?: ReactNode;
}

export function CourseTree({ courses, treeCourses, selectedId, loading, error, query, grouping, filter, tag, status, scope, onQueryChange, onFilter, onFacet, onSelect, onRetry, onPublish, extraFilters }: CourseTreeProps) {
  const searchId = useId();
  const tagId = useId();
  const statusId = useId();
  const treeId = useId();
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const subjects = new Map<string, Map<string, Course[]>>();
  treeCourses.filter(course => matchesSearch(course, query)).forEach(course => {
    const subject = course.subject_name || course.subject || '未分类';
    const album = course.album_name || '';
    const albums = subjects.get(subject) || new Map<string, Course[]>();
    albums.set(album, [...(albums.get(album) || []), course]);
    subjects.set(subject, albums);
  });
  const tags = [...new Set(courses.flatMap(course => course.tags || []))].sort((a, b) => a.localeCompare(b, 'zh-CN'));
  const toggle = (key: string) => setCollapsed(previous => { const next = new Set(previous); if (next.has(key)) next.delete(key); else next.add(key); return next; });
  const leaves = (items: Course[]) => items.map(course => <li key={course.id}><button type="button" className="um-course-list-item" title={course.title} aria-current={selectedId === course.id ? 'page' : undefined} onClick={() => onSelect(course)}><span className="um-course-list-title">{course.title}</span></button></li>);
  return <div className="um-course-list">
    <div className="um-course-list-heading"><h2>课程</h2><span className="um-course-muted">{!loading && !error && `${courses.length} 门`}</span></div>
    <nav className="um-course-shortcuts" aria-label="课程快捷导航"><button type="button" aria-current={!selectedId && scope === 'all' && !filter ? 'page' : undefined} onClick={() => onFacet('scope', 'all')}>学习门户</button><button type="button" aria-current={!selectedId && scope === 'learning' ? 'page' : undefined} onClick={() => onFacet('scope', 'learning')}>继续学习</button><button type="button" aria-current={!selectedId && scope === 'later' ? 'page' : undefined} onClick={() => onFacet('scope', 'later')}>稍后观看</button></nav>
    <div className="um-course-search"><label htmlFor={searchId} className="sr-only">搜索课程</label><Search size={16} aria-hidden="true" /><input id={searchId} type="search" value={query} onChange={event => onQueryChange(event.target.value)} placeholder="搜索课程" autoComplete="off" /></div>
    <div className="um-course-facets"><label className="sr-only" htmlFor={tagId}>标签筛选</label><select id={tagId} value={tag} onChange={event => onFacet('tag', event.target.value)}><option value="">全部标签</option>{tags.map(value => <option key={value} value={value}>{value}</option>)}</select><label className="sr-only" htmlFor={statusId}>学习状态筛选</label><select id={statusId} value={status} onChange={event => onFacet('status', event.target.value)}><option value="all">全部状态</option><option value="learning">未看完</option><option value="finished">已看完</option><option value="new">未开始</option></select></div>
    {extraFilters && <div className="um-course-facets um-course-extra-filters">{extraFilters}</div>}<div className="um-course-list-scroll" aria-busy={loading}>{loading ? <p className="um-course-list-message" role="status">正在加载…</p> : error ? <div className="um-course-list-message"><p role="alert">{error}</p><button type="button" className="um-course-button" onClick={onRetry}>重新加载</button></div> : !subjects.size ? <div className="um-course-list-message"><p>暂无匹配课程</p>{query && <button type="button" className="um-course-text-button" onClick={() => onQueryChange('')}>清除搜索</button>}</div> : <nav aria-label="课程目录"><ul className="um-course-tree">
      {[...subjects].sort(([a], [b]) => a.localeCompare(b, 'zh-CN')).map(([subject, albums], subjectIndex) => {
        const expanded = !!query.trim() || !collapsed.has(subject);
        const branchId = `${treeId}-${subjectIndex}`;
        const count = [...albums.values()].reduce((sum, list) => sum + list.length, 0);
        return <li key={subject}><div className="um-course-tree-branch"><button type="button" className="um-course-tree-toggle" aria-label={`${expanded ? '收起' : '展开'}${subject}`} aria-expanded={expanded} aria-controls={branchId} disabled={!!query.trim()} onClick={() => toggle(subject)}><ChevronRight size={14} /></button><button type="button" className="um-course-tree-label" title={subject} aria-current={!selectedId && grouping === 'subject' && filter === subject ? 'page' : undefined} onClick={() => onFilter(subject, 'subject')}><span>{subject}</span><span>{count}</span></button></div><ul id={branchId} hidden={!expanded}>{[...albums].map(([album, items], albumIndex) => {
          if (!album) return leaves(items);
          const key = `${subject}/${album}`;
          const albumExpanded = !!query.trim() || !collapsed.has(key);
          const albumId = `${branchId}-${albumIndex}`;
          return <li key={key} className="um-course-tree-album"><div className="um-course-tree-branch"><button type="button" className="um-course-tree-toggle" aria-label={`${albumExpanded ? '收起' : '展开'}${album}`} aria-expanded={albumExpanded} aria-controls={albumId} disabled={!!query.trim()} onClick={() => toggle(key)}><ChevronRight size={14} /></button><button type="button" className="um-course-tree-label" title={album} aria-current={!selectedId && grouping === 'album' && filter === album ? 'page' : undefined} onClick={() => onFilter(album, 'album')}><span>{album}</span></button></div><ul id={albumId} hidden={!albumExpanded}>{leaves(items)}</ul></li>;
        })}</ul></li>;
      })}
    </ul></nav>}</div>
    {onPublish && <div className="um-course-list-footer"><button type="button" className="um-course-button" onClick={onPublish}>发布课程</button></div>}
  </div>;
}
