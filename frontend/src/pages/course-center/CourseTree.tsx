import { useId, useState } from 'react';
import type { ReactNode } from 'react';
import { CaretRight as ChevronRight, MagnifyingGlass as Search, SlidersHorizontal } from '@phosphor-icons/react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { courseGroups, matchesSearch, type Course, type CourseGrouping } from './types';

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
  filtersActive: boolean;
  onResetFilters: () => void;
  onQueryChange: (value: string) => void;
  onFilter: (value: string, grouping?: CourseGrouping) => void;
  onFacet: (key: 'tag' | 'status' | 'scope', value: string) => void;
  onSelect: (course: Course) => void;
  onRetry: () => void;
  extraFilters?: ReactNode;
}

export function CourseTree({ courses, treeCourses, selectedId, loading, error, query, grouping, filter, tag, status, scope, filtersActive, onResetFilters, onQueryChange, onFilter, onFacet, onSelect, onRetry, extraFilters }: CourseTreeProps) {
  const searchId = useId();
  const tagId = useId();
  const statusId = useId();
  const scopeId = useId();
  const subjectId = useId();
  const moduleId = useId();
  const treeId = useId();
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const subjects = new Map<string, Map<string, { name: string; order: number; courses: Course[] }>>();
  const matchingCourses = treeCourses.filter(course => matchesSearch(course, query));
  matchingCourses.forEach(course => {
    const subject = course.subject_name || course.subject || '待归类学科';
    const modules = subjects.get(subject) || new Map<string, { name: string; order: number; courses: Course[] }>();
    const key = JSON.stringify([subject, course.module ?? null]);
    const module = modules.get(key) || { name: course.module_name || '待归类模块', order: course.module ? course.module_sort_order || 0 : Infinity, courses: [] };
    module.courses.push(course);
    modules.set(key, module);
    subjects.set(subject, modules);
  });
  const tags = [...new Set(courses.flatMap(course => course.tags || []))].sort((a, b) => a.localeCompare(b, 'zh-CN'));
  const subjectName = (course: Course) => course.subject_name || course.subject || '待归类学科';
  const selectedModule = grouping === 'module' && filter ? courses.find(course => courseGroups(course, 'module').includes(filter)) : undefined;
  const subjectFilter = grouping === 'subject' ? filter : selectedModule ? subjectName(selectedModule) : '';
  const moduleFilter = selectedModule ? courseGroups(selectedModule, 'module')[1] : '';
  const allSubjects = [...new Set(courses.map(subjectName))].sort((a, b) => a === '待归类学科' ? 1 : b === '待归类学科' ? -1 : a.localeCompare(b, 'zh-CN'));
  const moduleOptions = [...new Map(courses.filter(course => !subjectFilter || subjectName(course) === subjectFilter).map(course => [courseGroups(course, 'module')[1], course])).entries()]
    .sort(([, left], [, right]) => (left.module ? left.module_sort_order || 0 : Infinity) - (right.module ? right.module_sort_order || 0 : Infinity) || (left.module_name || '').localeCompare(right.module_name || '', 'zh-CN'));
  const toggle = (key: string) => setCollapsed(previous => { const next = new Set(previous); if (next.has(key)) next.delete(key); else next.add(key); return next; });
  const leaves = (items: Course[]) => items.map(course => <li key={course.id}><button type="button" className="um-course-list-item" title={course.title} aria-current={selectedId === course.id ? 'page' : undefined} onClick={() => onSelect(course)}><span className="um-course-list-title">{course.title}</span></button></li>);
  return <div className="um-course-list">
    <div className="um-course-list-heading"><h2>课程</h2><span className="um-course-muted">{!loading && !error && `${filtersActive || query.trim() ? `${matchingCourses.length} / ` : ''}${courses.length} 门`}</span></div>
    <div className="um-course-directory-tools">
      <div className="um-course-search"><label htmlFor={searchId} className="sr-only">搜索课程</label><Search size={16} aria-hidden="true" /><input id={searchId} type="search" value={query} onChange={event => onQueryChange(event.target.value)} placeholder="搜索课程" autoComplete="off" /></div>
      <Popover><PopoverTrigger asChild><button type="button" className="um-course-filter-trigger" data-active={filtersActive || undefined} aria-label={filtersActive ? '筛选课程，已启用' : '筛选课程'} title="筛选课程"><SlidersHorizontal size={18} aria-hidden="true" /></button></PopoverTrigger>
        <PopoverContent className="um-course-filter-panel" align="start" collisionPadding={12} aria-label="课程筛选">
          <div className="um-course-filter-heading"><h3>筛选课程</h3><button type="button" className="um-course-text-button" disabled={!filtersActive} onClick={onResetFilters}>重置</button></div>
          <div className="um-course-facets">
            <label htmlFor={subjectId}>学科</label><select id={subjectId} value={subjectFilter} onChange={event => onFilter(event.target.value, 'subject')}><option value="">全部学科</option>{allSubjects.map(value => <option key={value} value={value}>{value}</option>)}</select>
            <label htmlFor={moduleId}>模块</label><select id={moduleId} value={moduleFilter} onChange={event => onFilter(event.target.value || subjectFilter, event.target.value ? 'module' : 'subject')}><option value="">全部模块</option>{moduleOptions.map(([key, course]) => <option key={key} value={key}>{!subjectFilter ? `${subjectName(course)} / ` : ''}{course.module_name || '待归类模块'}</option>)}</select>
            <label htmlFor={scopeId}>观看范围</label><select id={scopeId} value={scope} onChange={event => onFacet('scope', event.target.value)}><option value="all">全部课程</option><option value="learning">继续学习</option><option value="later">稍后观看</option></select>
            <label htmlFor={tagId}>标签筛选</label><select id={tagId} value={tag} onChange={event => onFacet('tag', event.target.value)}><option value="">全部标签</option>{tags.map(value => <option key={value} value={value}>{value}</option>)}</select>
            <label htmlFor={statusId}>学习状态筛选</label><select id={statusId} value={status} onChange={event => onFacet('status', event.target.value)}><option value="all">全部状态</option><option value="learning">未看完</option><option value="finished">已看完</option><option value="new">未开始</option></select>
            {extraFilters}
          </div>
        </PopoverContent>
      </Popover>
    </div>
    <nav className="um-course-shortcuts" aria-label="课程快捷导航"><button type="button" aria-current={!selectedId && scope === 'all' && !filter ? 'page' : undefined} onClick={() => { onResetFilters(); onQueryChange(''); }}>学习门户</button></nav>
    <div className="um-course-list-scroll" aria-busy={loading}>{loading ? <p className="um-course-list-message" role="status">正在加载…</p> : error ? <div className="um-course-list-message"><p role="alert">{error}</p><button type="button" className="um-course-button" onClick={onRetry}>重新加载</button></div> : !subjects.size ? <div className="um-course-list-message"><p>暂无匹配课程</p>{query && <button type="button" className="um-course-text-button" onClick={() => onQueryChange('')}>清除搜索</button>}{filtersActive && <button type="button" className="um-course-text-button" onClick={onResetFilters}>重置筛选</button>}</div> : <nav aria-label="课程目录"><ul className="um-course-tree">
      {[...subjects].sort(([left], [right]) => left === '待归类学科' ? 1 : right === '待归类学科' ? -1 : left.localeCompare(right, 'zh-CN')).map(([subject, modules], subjectIndex) => {
        const key = `subject:${subject}`;
        const expanded = !!query.trim() || !collapsed.has(key);
        const branchId = `${treeId}-${subjectIndex}`;
        const count = [...modules.values()].reduce((sum, module) => sum + module.courses.length, 0);
        return <li key={key}><div className="um-course-tree-branch"><button type="button" className="um-course-tree-toggle" aria-label={`${expanded ? '收起' : '展开'}${subject}`} aria-expanded={expanded} aria-controls={branchId} disabled={!!query.trim()} onClick={() => toggle(key)}><ChevronRight size={14} /></button><button type="button" className="um-course-tree-label" title={subject} aria-current={!selectedId && grouping === 'subject' && filter === subject ? 'page' : undefined} onClick={() => onFilter(subject, 'subject')}><span>{subject}</span><span>{count}</span></button></div><ul id={branchId} hidden={!expanded}>{[...modules].sort(([, a], [, b]) => a.order - b.order || a.name.localeCompare(b.name, 'zh-CN')).map(([moduleKey, module], moduleIndex) => {
          const moduleExpanded = !!query.trim() || !collapsed.has(moduleKey);
          const moduleId = `${branchId}-${moduleIndex}`;
          return <li key={moduleKey} className="um-course-tree-album"><div className="um-course-tree-branch"><button type="button" className="um-course-tree-toggle" aria-label={`${moduleExpanded ? '收起' : '展开'}${module.name}`} aria-expanded={moduleExpanded} aria-controls={moduleId} disabled={!!query.trim()} onClick={() => toggle(moduleKey)}><ChevronRight size={14} /></button><button type="button" className="um-course-tree-label" title={module.name} aria-current={!selectedId && grouping === 'module' && filter === moduleKey ? 'page' : undefined} onClick={() => onFilter(moduleKey, 'module')}><span>{module.name}</span><span>{module.courses.length}</span></button></div><ul id={moduleId} hidden={!moduleExpanded}>{leaves(module.courses)}</ul></li>;
        })}</ul></li>;
      })}
    </ul></nav>}</div>
  </div>;
}
