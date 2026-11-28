import { useQuery } from '@tanstack/react-query';
import { useParams, useSearchParams } from 'react-router-dom';
import { CitationLines } from '@/components/CitationLines';
import { citationLine } from '@/lib/utils';
import { WorkspaceToolbar } from '@/components/WorkspaceToolbar';
import { t, useLocale } from '@/i18n';
import api from '@/lib/api';
import { activeWorkspace } from '@/lib/activeWorkspace';
import { useAuthStore } from '@/store/useAuthStore';
import type { Article } from '@/types/api';

export default function CitedArticle() {
  useLocale();
  const { id } = useParams();
  const [params] = useSearchParams();
  const userId = useAuthStore(state => state.user?.id);
  const validId = !!id && /^[1-9]\d*$/.test(id);
  const article = useQuery({
    queryKey: ['cited-article', userId, activeWorkspace(), id],
    queryFn: ({ signal }) => api.get<Article>(`/articles/${id}/`, { signal }).then(response => response.data),
    enabled: !!userId && validId,
  });
  const line = citationLine(params.get('line'));
  const version = params.get('version');
  const updated = Boolean(article.data && version && Date.parse(version) !== Date.parse(article.data.updated_at));

  return <main className="flex h-full min-h-0 flex-col">
    <WorkspaceToolbar className="flex min-w-0 items-center truncate px-4 text-sm font-medium">{article.data?.title ?? t('文章')}</WorkspaceToolbar>
    <div className="min-h-0 flex-1 overflow-auto">
      <article className="mx-auto max-w-4xl p-6">
        {validId && article.isPending && <p role="status">{t('正在读取资料…')}</p>}
        {(!validId || article.isError) && <p role="alert">{t('资料读取失败')}</p>}
        {article.data && <>
          <h1 className="mb-4 text-2xl font-semibold">{article.data.title}</h1>
          {updated && <p role="status">{t('原文已更新，引用行号可能已变化。')}</p>}
          <CitationLines content={article.data.content} line={updated ? null : line} />
        </>}
      </article>
    </div>
  </main>;
}
