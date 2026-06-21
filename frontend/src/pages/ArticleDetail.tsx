import React, { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { CaretLeft, Calendar, Spinner } from '@phosphor-icons/react';
import api from '@/lib/api';
import { processMathContent } from '@/lib/utils';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

export const ArticleDetail: React.FC = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [article, setArticle] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [scrollProgress, setScrollProgress] = useState(0);
  const viewCounted = useRef(false);
  const { t, i18n } = useTranslation('common');

  useEffect(() => {
    const handleScroll = () => {
      const totalHeight = document.documentElement.scrollHeight - window.innerHeight;
      const progress = (window.pageYOffset / totalHeight) * 100;
      setScrollProgress(progress);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    // Fetch article content
    api.get(`/articles/${id}/`).then(res => {
      setArticle(res.data);
    }).finally(() => setLoading(false));

    // Increment view count only once per component mount
    if (!viewCounted.current) {
      api.post(`/articles/${id}/view/`).catch(() => {});
      viewCounted.current = true;
    }
  }, [id]);

  if (loading) return (
    <div className="min-h-dvh flex flex-col items-center justify-center gap-4 text-center">
      <Spinner className="h-10 w-10 animate-spin text-muted-foreground/40" />
      <p className="text-[11px] font-medium text-muted-foreground">Loading...</p>
    </div>
  );

  if (!article) return <div className="min-h-dvh flex items-center justify-center font-bold">Article Not Found</div>;

  const processedContent = processMathContent(article.content);

  return (
    <div className="w-full max-w-4xl mx-auto animate-in fade-in duration-700 text-left p-4 md:p-10 pb-24 md:pb-32 relative">
      <style>{`
        .article-content h1 { font-size: 1.5rem; font-weight: 900; line-height: 1.2; margin-top: 1.5rem; margin-bottom: 0.75rem; letter-spacing: -0.05em; color: hsl(var(--foreground)); }
        .article-content h2 { font-size: 1.25rem; font-weight: 900; line-height: 1.3; margin-top: 1.25rem; margin-bottom: 0.5rem; color: hsl(var(--foreground)); }
        .article-content h3 { font-size: 1rem; font-weight: 800; margin-top: 1rem; margin-bottom: 0.4rem; color: hsl(var(--foreground)); }
        .article-content p { margin-bottom: 1.25rem; line-height: 1.7; font-size: 1rem; color: hsl(var(--muted-foreground)); }
        .article-content ul { list-style-type: disc; padding-left: 1.5rem; margin-bottom: 1.25rem; color: hsl(var(--muted-foreground)); }
        .article-content ol { list-style-type: decimal; padding-left: 1.5rem; margin-bottom: 1.25rem; color: hsl(var(--muted-foreground)); }
        .article-content .katex-display { display: block; text-align: center; margin: 1.5em 0; overflow-x: auto; overflow-y: hidden; }
        .article-content li { margin-bottom: 0.5rem; }
        .article-content blockquote { border-left: 4px solid hsl(var(--primary)); padding: 0.75rem 1.5rem; font-style: italic; background: hsl(var(--unimind-bg-secondary)); margin-bottom: 1.25rem; border-radius: 0 0.75rem 0.75rem 0; color: hsl(var(--muted-foreground)); }
        .article-content code { background: hsl(var(--unimind-bg-secondary)); color: hsl(var(--primary)); padding: 0.2rem 0.4rem; border-radius: 0.375rem; font-family: monospace; font-size: 0.875rem; }
        .article-content pre { background: hsl(var(--foreground)); color: hsl(var(--unimind-bg-secondary)); padding: 1.5rem; border-radius: 1rem; font-family: monospace; margin-bottom: 1.25rem; overflow-x: auto; }
        .article-content pre code { background: transparent; color: inherit; padding: 0; }
        .article-content img { border-radius: 1.5rem; box-shadow: 0 20px 25px -5px rgb(0 0 0 / 0.1); margin: 2rem 0; max-width: 100%; }

        .dark .article-content h1, .dark .article-content h2, .dark .article-content h3 { color: white; }
        .dark .article-content p, .dark .article-content ul, .dark .article-content ol { color: hsl(var(--border)); }
        .dark .article-content blockquote { background: rgba(255,255,255,0.05); color: hsl(var(--muted-foreground)); }
      `}</style>

      <div className="fixed top-0 left-0 w-full h-1 z-[var(--z-overlay)] bg-muted/20">
        <div 
          className="h-full bg-indigo-500 transition-all duration-150 ease-out"
          style={{ width: `${scrollProgress}%` }}
        />
      </div>

      <header className="space-y-5 md:space-y-8 border-b border-border/50 pb-7 md:pb-10 mb-8 md:mb-12">
        <Button variant="ghost" size="icon" onClick={() => navigate(-1)} className="rounded-xl hover:bg-muted shadow-sm border border-border h-10 w-10 transition-all">
          <CaretLeft className="h-5 w-5"/>
        </Button>
        <div className="space-y-4">
           <div className="flex items-center gap-3">
              <span className="text-[10px] font-bold text-indigo-600 bg-indigo-50 dark:bg-indigo-950/30 px-3 py-1 rounded-full uppercase tracking-widest border border-indigo-100 dark:border-indigo-900/50">Academic Paper</span>
              <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest flex items-center gap-1.5"><Calendar className="w-3 h-3"/> {new Date(article.created_at).toLocaleDateString(i18n.language?.startsWith('zh') ? 'zh-CN' : 'en-US')}</span>
           </div>
           <h1 className="text-2xl md:text-3xl lg:text-4xl font-black tracking-tighter text-slate-900 dark:text-white leading-[1.1]">{article.title}</h1>
           <div className="flex flex-wrap gap-2 pt-2">
              {article.tags?.map((t: string) => (
                <span key={t} className="text-[9px] font-bold text-muted-foreground bg-muted px-2.5 py-1 rounded-md uppercase tracking-wider">{t}</span>
              ))}
           </div>
        </div>
      </header>

      <div className="article-content max-w-none">
         <ReactMarkdown 
           remarkPlugins={[remarkMath, remarkGfm]} 
           rehypePlugins={[rehypeKatex]}
         >
           {processedContent}
         </ReactMarkdown>
      </div>

      <footer className="mt-14 md:mt-20 pt-8 md:pt-12 border-t border-border/50 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
         <div className="flex items-center gap-4 text-left">
            <div className="h-12 w-12 rounded-full bg-black flex items-center justify-center text-white font-bold text-sm shadow-sm uppercase">
               {article.author_display_name?.[0] || 'U'}
            </div>
            <div>
               <p className="text-sm font-bold text-slate-900 dark:text-white">{article.author_display_name || t('articleDefaultAuthor')}</p>
               <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-widest">Verified Academic Resource</p>
            </div>
         </div>
         <Button asChild variant="outline" className="rounded-2xl font-bold h-12 w-full md:w-auto px-8 border-border hover:bg-muted transition-colors"><Link to="/articles">{t('articleBackToList')}</Link></Button>
      </footer>
    </div>
  );
};
