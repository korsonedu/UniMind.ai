/**
 * 资产管理 — 统计面板 + 快捷入口。
 */
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { BookOpen, FileText, Brain, ArrowRight, Spinner } from '@phosphor-icons/react';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import { quotaStatus } from '@/store/useInstitutionStore';
import { cn } from '@/lib/utils';

const TABS = [
  {
    key: 'course',
    label: '课程 / 视频',
    icon: BookOpen,
    to: '/courses',
    detail: '上传与管理课程视频',
  },
  {
    key: 'question',
    label: '题目',
    icon: Brain,
    to: '/questions',
    detail: '管理题库，AI 出题，布置作业',
  },
  {
    key: 'article',
    label: '文章',
    icon: FileText,
    to: '/articles',
    detail: '发布与管理长文',
  },
] as const;

export default function AssetHub() {
  const navigate = useNavigate();
  const { usage, fetchFeatures, loading } = useInstitutionStore();

  useEffect(() => {
    if (!usage && !loading) fetchFeatures();
  }, [fetchFeatures, usage, loading]);

  return (
    <div className="max-w-2xl mx-auto p-4 md:p-6 space-y-6">
      <h1 className="text-lg font-bold">资产管理</h1>

      {loading && !usage ? (
        <div className="flex items-center justify-center py-12">
          <Spinner className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="space-y-2">
          {TABS.map(tab => {
            const quota = usage?.[tab.key];
            const count = quota?.used ?? 0;
            const limit = quota?.limit;
            const status = quota ? quotaStatus(quota) : 'normal';

            return (
              <button
                key={tab.key}
                onClick={() => navigate(tab.to)}
                className="w-full flex items-center gap-4 px-4 py-4 rounded-xl border border-border bg-card hover:border-primary/20 hover:bg-muted/20 transition-colors text-left group"
              >
                <div className={cn(
                  'h-9 w-9 rounded-lg flex items-center justify-center shrink-0 transition-colors',
                  status === 'exhausted' ? 'bg-red-50 text-red-500' :
                  status === 'warning' ? 'bg-amber-50 text-amber-500' :
                  'bg-muted text-muted-foreground group-hover:bg-primary/10 group-hover:text-primary'
                )}>
                  <tab.icon className="h-5 w-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold">{tab.label}</span>
                  </div>
                  <div className="text-xs text-muted-foreground mt-0.5">{tab.detail}</div>
                </div>
                <div className="text-right shrink-0">
                  <div className={cn(
                    'text-sm font-bold tabular-nums',
                    status === 'exhausted' ? 'text-red-500' :
                    status === 'warning' ? 'text-amber-500' :
                    'text-foreground/80'
                  )}>
                    {loading ? '...' : `${count}${limit ? ` / ${limit}` : ''}`}
                  </div>
                  {status === 'exhausted' && (
                    <span className="text-[10px] font-bold text-red-500">已满</span>
                  )}
                  {status === 'warning' && (
                    <span className="text-[10px] font-bold text-amber-500">将满</span>
                  )}
                </div>
                <ArrowRight className="h-4 w-4 text-muted-foreground shrink-0 opacity-50 group-hover:opacity-100 transition-opacity" />
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
