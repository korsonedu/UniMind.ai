/**
 * 资产管理 — Tab 切换 + 机构运营视角。
 */
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { BookOpen, FileText, Brain, ArrowRight } from '@phosphor-icons/react';
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
    detail: '管理题库，AI 出题',
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
    <div className="max-w-2xl mx-auto p-4 md:p-6 space-y-5">
      <h1 className="text-lg font-bold">资产管理</h1>

      {/* Tabs as content rows */}
      <div className="space-y-1">
        {TABS.map(tab => {
          const quota = usage?.[tab.key];
          const count = quota?.used ?? 0;
          const limit = quota?.limit;
          const status = quota ? quotaStatus(quota) : 'normal';

          return (
            <button
              key={tab.key}
              onClick={() => navigate(tab.to)}
              className="w-full flex items-center gap-4 px-4 py-3.5 rounded-xl border border-border bg-card hover:border-primary/20 transition-colors text-left"
            >
              <tab.icon className="h-5 w-5 text-muted-foreground shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold">{tab.label}</span>
                </div>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {loading ? '...' : `${count}${limit ? ` / ${limit}` : ''} 个`}
                  </span>
                  {status === 'exhausted' && (
                    <span className="text-[10px] font-bold text-red-500 bg-red-50 px-1.5 py-0.5 rounded-sm">已满</span>
                  )}
                  {status === 'warning' && (
                    <span className="text-[10px] font-bold text-amber-500 bg-amber-50 px-1.5 py-0.5 rounded-sm">将满</span>
                  )}
                </div>
              </div>
              <ArrowRight className="h-4 w-4 text-muted-foreground shrink-0" />
            </button>
          );
        })}
      </div>
    </div>
  );
}
