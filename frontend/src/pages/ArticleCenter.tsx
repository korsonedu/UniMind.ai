import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { FileText, ChevronRight, ChevronLeft } from 'lucide-react';
import { PageWrapper } from '@/components/PageWrapper';
import { Button } from '@/components/ui/button';
import { Loading } from '@/components/Loading';
import { EmptyState } from '@/components/EmptyState';
import { InlineError } from '@/components/InlineError';
import { useFetch } from '@/lib/useFetch';
import { cn } from '@/lib/utils';
import api from '@/lib/api';
import { useTranslation } from 'react-i18next';

export const ArticleCenter: React.FC = () => {
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [showAllTags, setShowAllTags] = useState(false);
  const [page, setPage] = useState(1);

  const { t, i18n } = useTranslation('common');

  const navigate = useNavigate();

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

  const handleTagChange = (tag: string | null) => {
    setSelectedTag(tag);
    setPage(1);
  };

  const handlePageChange = (newPage: number) => {
    setPage(newPage);
    document.querySelector('main')?.scrollTo({ top: 0, behavior: 'smooth' });
  };

  if (loading && articles.length === 0) return <Loading message="Loading articles..." />;
  if (error) return <InlineError message={error} onRetry={refetch} />;

  return (
    <PageWrapper title={t('pages:articleCenter.title')} subtitle={t('pages:articleCenter.subtitle')}>
      <div className="flex flex-col gap-5 md:gap-8 w-full text-left">
        
        {/* Tags */}
        <div className="flex flex-col gap-3 px-1 md:px-2">
          <div className={cn(
            "flex flex-wrap gap-2 overflow-hidden transition-all duration-500",
            !showAllTags ? "max-h-[32px]" : "max-h-[500px]"
          )}>
            <Button 
              onClick={() => handleTagChange(null)}
              variant={selectedTag === null ? "default" : "outline"}
              className="rounded-full h-7 px-4 text-[11px] font-bold uppercase tracking-widest transition-all"
            >
              {t('all')}
            </Button>
            {tagStats && Array.isArray(tagStats) && tagStats.map((tag) => (
              <Button 
                key={tag.name}
                onClick={() => handleTagChange(tag.name)}
                variant={selectedTag === tag.name ? "default" : "outline"}
                className="rounded-full h-7 px-4 text-[11px] font-bold uppercase tracking-widest transition-all border-black/5"
              >
                {tag.name} · {tag.count}
              </Button>
            ))}
          </div>
          {tagStats.length > 4 && (
            <div className="flex justify-start mt-1">
              <Button 
                onClick={() => setShowAllTags(!showAllTags)}
                variant="ghost"
                className="h-6 px-2 text-[11px] font-bold text-indigo-600 hover:bg-indigo-50 flex items-center gap-1 group"
              >
                {showAllTags ? t('collapseTags') : t('expandTags', { count: tagStats.length - 4 })}
                <div className={cn("transition-transform duration-300", showAllTags ? "rotate-180" : "rotate-0")}>
                  <ChevronRight className={cn("w-3 h-3 transform rotate-90")} />
                </div>
              </Button>
            </div>
          )}
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
                    <ChevronRight className="w-3.5 h-3.5 text-muted-foreground/20 group-hover:text-primary transition-all group-hover:translate-x-1" />
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
                <ChevronLeft className="w-3 h-3" /> Previous
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
                Next <ChevronRight className="w-3 h-3" />
              </Button>
            </div>
          )}
        </div>
      </div>
    </PageWrapper>
  );
};
