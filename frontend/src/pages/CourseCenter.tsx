import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { PlusCircle, PlayCircle, BookOpen, MagnifyingGlass, SquaresFour, ListBullets, CaretLeft, CaretRight } from '@phosphor-icons/react';
import { useAuthStore } from '@/store/useAuthStore';
import { useNavigate, Link } from 'react-router-dom';
import { PageWrapper } from '@/components/PageWrapper';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/EmptyState';
import { InlineError } from '@/components/InlineError';
import { useFetch } from '@/lib/useFetch';
import api from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

type ViewMode = 'grid' | 'list';

export const CourseCenter: React.FC = () => {
  const user = useAuthStore(s => s.user);
  const navigate = useNavigate();
  const [allTags, setAllTags] = useState<any[]>([]);
  const [activeTags, setActiveTags] = useState<string[]>([]);
  const [classes, setClasses] = useState<{ id: number; name: string }[]>([]);
  const [classId, setClassId] = useState<number | null>(null);
  const [search, setSearch] = useState('');
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [page, setPage] = useState(1);

  useEffect(() => {
    api.get('/courses/tags/').then(r => setAllTags(r.data || [])).catch(() => {});
    api.get('/users/me/classes/').then(r => setClasses(r.data || [])).catch(() => {});
  }, []);

  const { t } = useTranslation('common');
  const queryParams: string[] = [];
  if (search.trim()) queryParams.push(`search=${encodeURIComponent(search.trim())}`);
  if (activeTags.length > 0) activeTags.forEach(t => queryParams.push(`tag=${encodeURIComponent(t)}`));
  if (classId) queryParams.push(`class_id=${classId}`);
  queryParams.push('page_size=12');
  queryParams.push(`page=${page}`);
  const tagQuery = queryParams.length > 0 ? '?' + queryParams.join('&') : '';
  const fetchKey = `courses-${search}-${activeTags.join(',')}-${classId || 'all'}-${page}`;

  const { data: coursesData, loading, error, refetch } = useFetch<any>(
    (signal) => api.get(`/courses/${tagQuery}`, { signal }).then(r => r.data),
    fetchKey
  );

  const courses = coursesData?.items || coursesData || [];
  const totalPages = coursesData?.total_pages || 1;

  const isManager = user?.role === 'admin' || user?.is_institution_admin;
  const ActionBtn = isManager ? (
    <Button
      onClick={() => navigate('/courses/manage')}
      className="bg-primary text-primary-foreground hover:opacity-90 rounded-2xl px-6 h-11 font-bold shadow-lg transition-all hover:scale-[1.02]"
    >
      <PlusCircle className="mr-2 h-4 w-4" /> {t('publishCourse')}
    </Button>
  ) : null;

  if (loading) return (
    <PageWrapper title={t('pages:courseCenter.title')} subtitle={t('pages:courseCenter.subtitle')}>
      <div className="max-w-5xl mx-auto grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="rounded-2xl overflow-hidden bg-card border border-border/50">
            <Skeleton className="aspect-video w-full rounded-none" />
            <div className="p-4 space-y-2">
              <Skeleton className="h-5 w-3/4" />
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-1/2" />
            </div>
          </div>
        ))}
      </div>
    </PageWrapper>
  );
  if (error) return <InlineError message={error} onRetry={refetch} />;

  return (
    <PageWrapper
      title={t('pages:courseCenter.title')}
      subtitle={t('pages:courseCenter.subtitle')}
      action={ActionBtn}
    >
      <div className="max-w-6xl mx-auto space-y-4 md:space-y-6">
        {/* 工具栏：搜索 + 视图切换 */}
        <div className="flex items-center gap-2">
          <div className="relative flex-1 max-w-sm">
            <MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1); }}
              placeholder="搜索课程..."
              className="pl-9 h-9"
            />
          </div>
          <div className="flex items-center border border-border rounded-lg p-0.5">
            <button
              onClick={() => setViewMode('grid')}
              className={cn(
                "p-1.5 rounded-md transition-colors",
                viewMode === 'grid' ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground"
              )}
            >
              <SquaresFour className="h-4 w-4" />
            </button>
            <button
              onClick={() => setViewMode('list')}
              className={cn(
                "p-1.5 rounded-md transition-colors",
                viewMode === 'list' ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground"
              )}
            >
              <ListBullets className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* 班级筛选 */}
        {classes.length > 0 && (
          <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-none">
            <Badge
              className={cn(
                "cursor-pointer px-3 py-1 rounded-full text-[11px] font-bold shrink-0 transition-colors",
                !classId ? "bg-black text-white dark:bg-white dark:text-black" : "bg-slate-100 dark:bg-zinc-800 text-slate-600 dark:text-zinc-400 hover:bg-slate-200 dark:hover:bg-zinc-700"
              )}
              onClick={() => { setClassId(null); setPage(1); }}
            >
              全部班级
            </Badge>
            {classes.map((c) => (
              <Badge
                key={c.id}
                className={cn(
                  "cursor-pointer px-3 py-1 rounded-full text-[11px] font-bold shrink-0 transition-colors",
                  classId === c.id ? "bg-black text-white dark:bg-white dark:text-black" : "bg-slate-100 dark:bg-zinc-800 text-slate-600 dark:text-zinc-400 hover:bg-slate-200 dark:hover:bg-zinc-700"
                )}
                onClick={() => { setClassId(c.id); setPage(1); }}
              >
                {c.name}
              </Badge>
            ))}
          </div>
        )}

        {/* 标签筛选 */}
        {allTags.length > 0 && (
          <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-none">
            {activeTags.length > 0 && (
              <Badge
                className="cursor-pointer bg-black text-white dark:bg-white dark:text-black hover:opacity-80 px-3 py-1 rounded-full text-[11px] font-bold shrink-0"
                onClick={() => { setActiveTags([]); setPage(1); }}
              >
                全部 ×
              </Badge>
            )}
            {allTags.map((tag: any) => {
              const isActive = activeTags.includes(tag.slug);
              return (
                <Badge
                  key={tag.id}
                  className={cn(
                    "cursor-pointer px-3 py-1 rounded-full text-[11px] font-bold shrink-0 transition-colors",
                    isActive ? "bg-black text-white dark:bg-white dark:text-black" : "bg-slate-100 dark:bg-zinc-800 text-slate-600 dark:text-zinc-400 hover:bg-slate-200 dark:hover:bg-zinc-700"
                  )}
                  onClick={() => {
                    setPage(1);
                    if (isActive) {
                      setActiveTags(activeTags.filter(t => t !== tag.slug));
                    } else {
                      setActiveTags([...activeTags, tag.slug]);
                    }
                  }}
                >
                  {tag.name}
                </Badge>
              );
            })}
          </div>
        )}

        {/* 内容区 */}
        {!courses.length ? (
          <EmptyState icon={BookOpen} title={t('noCourses')} description={t('noCoursesHint')} className="h-[40vh]" />
        ) : viewMode === 'grid' ? (
          /* 网格视图 */
          <>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 text-left animate-in fade-in duration-300">
              {courses.map((course: any) => (
                <Link
                  key={course.id}
                  to={`/course/${course.id}`}
                  className="border-none shadow-sm rounded-2xl overflow-hidden bg-card border border-border group hover:shadow-lg transition-[box-shadow,transform] duration-300 cursor-pointer block"
                >
                  <div className="aspect-video bg-slate-100 dark:bg-zinc-800 relative overflow-hidden">
                    {course.cover_image ? (
                      <img src={course.cover_image} alt={course.title} className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-110" loading="lazy" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-muted-foreground font-bold uppercase tracking-widest text-[11px]">No Preview</div>
                    )}
                    <div className="absolute inset-0 bg-black/20 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                      <div className="h-8 w-8 rounded-full bg-background border border-border flex items-center justify-center shadow-lg scale-75 group-hover:scale-100 transition-transform">
                        <PlayCircle className="h-4 w-4 text-foreground" />
                      </div>
                    </div>
                  </div>
                  <CardContent className="p-4 space-y-2">
                    <div className="flex justify-between items-start gap-2">
                      <h3 className="font-bold text-sm leading-tight group-hover:text-emerald-600 dark:group-hover:text-emerald-400 transition-colors line-clamp-1 flex-1">{course.title}</h3>
                    </div>
                    <p className="text-[11px] text-muted-foreground line-clamp-2 font-medium leading-relaxed min-h-[28px]">{course.description}</p>
                    {course.tags && course.tags.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1">
                        {course.tags.map((t: any) => (
                          <span key={t.id} className="text-[9px] font-bold text-slate-400 dark:text-zinc-500 uppercase tracking-wide">
                            #{t.name}
                          </span>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Link>
              ))}
            </div>
            {/* 分页 */}
            {totalPages > 1 && (
              <div className="flex items-center justify-center gap-3 pt-2 pb-4">
                <Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}
                  className="rounded-xl text-xs font-bold gap-1">
                  <CaretLeft className="h-3 w-3" /> 上一页
                </Button>
                <span className="text-xs text-muted-foreground font-bold">{page} / {totalPages}</span>
                <Button variant="ghost" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}
                  className="rounded-xl text-xs font-bold gap-1">
                  下一页 <CaretRight className="h-3 w-3" />
                </Button>
              </div>
            )}
          </>
        ) : (
          /* 列表视图 */
          <div className="space-y-2">
            {courses.map((course: any) => (
              <Link
                key={course.id}
                to={`/course/${course.id}`}
                className="flex items-center gap-4 p-4 rounded-xl border border-border bg-card hover:border-primary/20 hover:shadow-sm transition-all duration-200 group"
              >
                <div className="w-32 shrink-0 aspect-video rounded-lg bg-slate-100 dark:bg-zinc-800 overflow-hidden">
                  {course.cover_image ? (
                    <img src={course.cover_image} alt={course.title} className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105" loading="lazy" />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center">
                      <PlayCircle className="h-5 w-5 text-muted-foreground/30" />
                    </div>
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-bold text-sm group-hover:text-emerald-600 dark:group-hover:text-emerald-400 transition-colors truncate">{course.title}</h3>
                  <p className="text-xs text-muted-foreground line-clamp-2 mt-1 leading-relaxed">{course.description}</p>
                  {course.tags && course.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {course.tags.map((t: any) => (
                        <span key={t.id} className="text-[9px] font-bold text-slate-400 dark:text-zinc-500 uppercase tracking-wide">#{t.name}</span>
                      ))}
                    </div>
                  )}
                </div>
                <PlayCircle className="h-5 w-5 text-muted-foreground/0 group-hover:text-muted-foreground/30 transition-all shrink-0" />
              </Link>
            ))}
            {/* 分页 */}
            {totalPages > 1 && (
              <div className="flex items-center justify-center gap-3 pt-2 pb-4">
                <Button variant="ghost" size="sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}
                  className="rounded-xl text-xs font-bold gap-1">
                  <CaretLeft className="h-3 w-3" /> 上一页
                </Button>
                <span className="text-xs text-muted-foreground font-bold">{page} / {totalPages}</span>
                <Button variant="ghost" size="sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}
                  className="rounded-xl text-xs font-bold gap-1">
                  下一页 <CaretRight className="h-3 w-3" />
                </Button>
              </div>
            )}
          </div>
        )}
      </div>
    </PageWrapper>
  );
};
