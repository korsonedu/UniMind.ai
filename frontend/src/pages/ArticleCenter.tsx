import React, { useState, useRef } from 'react';
import { Link } from 'react-router-dom';
import { FileText, CaretRight, CaretLeft, PlusCircle } from '@phosphor-icons/react';
import { useNavigate } from 'react-router-dom';
import { PageWrapper } from '@/components/PageWrapper';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { InlineError } from '@/components/InlineError';
import { useFetch } from '@/lib/useFetch';
import { cn } from '@/lib/utils';
import api from '@/lib/api';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/store/useAuthStore';

export const ArticleCenter: React.FC = () => {
  const { user } = useAuthStore();
  const navigate = useNavigate();
  const isManager = user?.role === 'admin' || user?.is_institution_admin;
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const scrollRef = useRef<HTMLDivElement>(null);

  const { t, i18n } = useTranslation('common');

  const cacheKey = `articles-${selectedTag || 'all'}-${page}`;
  const { data, loading, error, refetch } = useFetch<{
    articles: any[];
    tag_stats: any[];
    total_pages: number;
  }>(
    (signal) => api.get('/articles/', { params: { tag: selectedTag, page }, signal }).then(r => r.data),
    cacheKey
  );

  const articles = data?.articles || [];
  const tagStats = data?.tag_stats || [];
  const totalPages = data?.total_pages || 1;
  const totalCount = tagStats.reduce((sum: number, t: any) => sum + (t.count || 0), 0);

  const handleTagChange = (tag: string | null) => {
    // Clicking the active tag deselects it
    setSelectedTag(selectedTag === tag ? null : tag);
    setPage(1);
  };

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
    document.querySelector('main')?.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const scrollTags = (direction: 'left' | 'right') => {
    if (!scrollRef.current) return;
    const amount = 200;
    scrollRef.current.scrollBy({
      left: direction === 'left' ? -amount : amount,
      behavior: 'smooth',
    });
  };

  const actionBtn = isManager ? (
    <Button onClick={() => navigate('/articles/manage')} className="rounded-2xl px-6 h-11 font-bold">
      <PlusCircle className="mr-2 h-4 w-4" />发布文章
    </Button>
  ) : undefined;

  if (loading && articles.length === 0) return (
    <PageWrapper title={t('pages:articleCenter.title')} subtitle={t('pages:articleCenter.subtitle')} action={actionBtn}>
      <div className="max-w-4xl mx-auto flex flex-col border border-border/50 rounded-2xl md:rounded-[2rem] bg-card overflow-hidden">
        <div className="hidden md:grid grid-cols-12 gap-4 px-8 py-4 bg-muted/30 text-[11px] font-semibold tracking-wider border-b border-border/50">
          <div className="col-span-2">{t('articleDate')}</div>
          <div className="col-span-2">{t('articleAuthor')}</div>
          <div className="col-span-6">{t('articleTitle')}</div>
          <div className="col-span-2 text-right pr-4">{t('articleViews')}</div>
        </div>
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="grid grid-cols-12 gap-4 px-8 py-5 items-center border-b border-border/50 last:border-0">
            <div className="col-span-2"><Skeleton className="h-3 w-16" /></div>
            <div className="col-span-2"><Skeleton className="h-5 w-20 rounded-full" /></div>
            <div className="col-span-6"><Skeleton className="h-4 w-3/4" /></div>
            <div className="col-span-2 flex justify-end"><Skeleton className="h-3 w-10" /></div>
          </div>
        ))}
      </div>
    </PageWrapper>
  );
  if (error) return <InlineError message={error} onRetry={refetch} />;

  return (
    <PageWrapper title={t('pages:articleCenter.title')} subtitle={t('pages:articleCenter.subtitle')} action={actionBtn}>
      <div className="max-w-4xl mx-auto flex flex-col gap-5 md:gap-8 w-full text-left">
        
        {/* Tag Pills — horizontal scroll */}
        <div className="relative group/tags">
          {/* Scroll button: left */}
          <button
            onClick={() => scrollTags('left')}
            className="absolute left-0 top-1/2 -translate-y-1/2 z-10 w-7 h-7 rounded-full bg-white/90 dark:bg-slate-900/90 shadow-md border border-border/50 flex items-center justify-center opacity-0 group-hover/tags:opacity-100 transition-opacity disabled:opacity-0"
            aria-label="Scroll left"
          >
            <CaretLeft className="w-3.5 h-3.5 text-muted-foreground" />
          </button>

          <div
            ref={scrollRef}
            className="flex gap-2 overflow-x-auto scrollbar-none pb-1 -mx-1 px-1"
          >
            {/* "全部" pill */}
            <button
              onClick={() => handleTagChange(null)}
              className={cn(
                "shrink-0 rounded-full h-8 px-4 text-xs font-semibold transition-all duration-200 whitespace-nowrap border",
                selectedTag === null
                  ? "bg-foreground text-background border-foreground"
                  : "bg-card text-muted-foreground border-border hover:border-foreground/20 hover:text-foreground"
              )}
            >
              {t('all')} · {totalCount}
            </button>

            {tagStats.map((tag: any) => {
              const isActive = selectedTag === tag.name;
              return (
                <button
                  key={tag.name}
                  onClick={() => handleTagChange(tag.name)}
                  className={cn(
                    "shrink-0 rounded-full h-8 px-4 text-xs font-semibold transition-all duration-200 whitespace-nowrap border",
                    isActive
                      ? "bg-foreground text-background border-foreground"
                      : "bg-card text-muted-foreground border-border hover:border-foreground/20 hover:text-foreground"
                  )}
                >
                  {tag.name} · {tag.count}
                </button>
              );
            })}
          </div>

          {/* Scroll button: right */}
          <button
            onClick={() => scrollTags('right')}
            className="absolute right-0 top-1/2 -translate-y-1/2 z-10 w-7 h-7 rounded-full bg-white/90 dark:bg-slate-900/90 shadow-md border border-border/50 flex items-center justify-center opacity-0 group-hover/tags:opacity-100 transition-opacity disabled:opacity-0"
            aria-label="Scroll right"
          >
            <CaretRight className="w-3.5 h-3.5 text-muted-foreground" />
          </button>
        </div>

        {/* List Content */}
        <div className="flex flex-col border border-border/50 rounded-2xl md:rounded-[2rem] bg-card overflow-hidden shadow-sm">
          {/* List Header */}
          <div className="hidden md:grid grid-cols-12 gap-4 px-8 py-4 bg-muted/30 text-[11px] font-semibold tracking-wider border-b border-border/50">
            <div className="col-span-2">{t('articleDate')}</div>
            <div className="col-span-2">{t('articleAuthor')}</div>
            <div className="col-span-6">{t('articleTitle')}</div>
            <div className="col-span-2 text-right pr-4">{t('articleViews')}</div>
          </div>

          <div className="flex flex-col animate-in fade-in duration-500">
            {articles.length === 0 ? (
              <div className="p-20 flex flex-col items-center justify-center text-center space-y-4">
                <FileText className="h-12 w-12 text-muted-foreground/20" />
                <p className="text-muted-foreground font-bold text-xs uppercase tracking-widest">No articles found</p>
              </div>
            ) : articles.map(article => (
              <Link key={article.id} to={`/article/${article.id}`} className="hover:bg-muted/50 transition-all border-b border-border last:border-0 cursor-pointer group block">
                <div className="md:hidden px-4 py-4 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[11px] font-bold text-muted-foreground tabular-nums">{new Date(article.created_at).toLocaleDateString(i18n.language?.startsWith('zh') ? 'zh-CN' : 'en-US')}</span>
                    <span className="text-[11px] font-bold text-muted-foreground/60">{t('viewsCount', { count: article.views || 0 })}</span>
                  </div>
                  <h3 className="font-bold text-foreground group-hover:text-primary transition-colors text-sm leading-relaxed">
                    {article.title}
                  </h3>
                  <span className="inline-flex px-2 py-0.5 rounded-full bg-indigo-50 dark:bg-indigo-950/30 text-[9px] font-black text-indigo-600 dark:text-indigo-400 uppercase tracking-tighter">
                    {article.author_display_name || 'KS Academy'}
                  </span>
                </div>
                <div className="hidden md:grid grid-cols-12 gap-4 px-8 py-5 items-center">
                  <div className="col-span-2 text-[11px] font-bold text-muted-foreground tabular-nums">
                    {new Date(article.created_at).toLocaleDateString(i18n.language?.startsWith('zh') ? 'zh-CN' : 'en-US')}
                  </div>
                  <div className="col-span-2">
                    <span className="inline-flex px-2 py-0.5 rounded-full bg-indigo-50 dark:bg-indigo-950/30 text-[9px] font-black text-indigo-600 dark:text-indigo-400 uppercase tracking-tighter truncate max-w-full">
                      {article.author_display_name || 'KS Academy'}
                    </span>
                  </div>
                  <div className="col-span-6">
                    <h3 className="font-bold text-foreground group-hover:text-primary transition-colors text-sm truncate pr-4">
                      {article.title}
                    </h3>
                  </div>
                  <div className="col-span-2 flex justify-end items-center gap-4 text-right">
                    <span className="tabular-nums text-[11px] font-bold text-muted-foreground/60">{article.views || 0}</span>
                    <CaretRight className="w-3.5 h-3.5 text-muted-foreground/20 group-hover:text-primary transition-all group-hover:translate-x-1" />
                  </div>
                </div>
              </Link>
            ))}
          </div>

          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div className="p-4 md:p-6 border-t border-border/50 flex flex-col md:flex-row items-center justify-between gap-3 md:gap-0 bg-muted/10">
              <Button 
                disabled={page === 1} 
                onClick={() => handlePageChange(page - 1)}
                variant="ghost"
                className="rounded-xl font-bold text-[11px] uppercase tracking-widest gap-2"
              >
                <CaretLeft className="w-3 h-3" /> Previous
              </Button>
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-semibold text-muted-foreground">Page</span>
                <span className="h-7 px-3 bg-card border border-border rounded-lg flex items-center justify-center text-xs font-semibold tabular-nums">{page}</span>
                <span className="text-[11px] font-bold text-muted-foreground">/ {totalPages}</span>
              </div>
              <Button 
                disabled={page === totalPages} 
                onClick={() => handlePageChange(page + 1)}
                variant="ghost"
                className="rounded-xl font-bold text-[11px] uppercase tracking-widest gap-2"
              >
                Next <CaretRight className="w-3 h-3" />
              </Button>
            </div>
          )}
        </div>
      </div>
    </PageWrapper>
  );
};
