import React from 'react';
import { Target, ArrowsOut, FileText, Video, X, Stack } from '@phosphor-icons/react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn, processMathContent } from '@/lib/utils';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { useTranslation } from 'react-i18next';
import type { KPNode } from './types';
import { LEVEL_COLORS } from './types';

export const NodeDetailPanel: React.FC<{
  node: KPNode | null;
  details: { courses: any[]; articles: any[]; questions: any[] };
  loading: boolean;
  onQuestionClick: (q: any) => void;
  onClear: () => void;
  masteryData?: Record<string, string>;
}> = ({ node, details, loading, onQuestionClick, onClear, masteryData = {} }) => {
  const { t } = useTranslation('knowledgeMap');

  const MASTERY_LABELS: Record<string, string> = {
    mastered: t('masteryLevels.mastered'), stable: t('masteryLevels.stable'), learning: t('masteryLevels.learning'), weak: t('masteryLevels.weak'), unknown: t('masteryLevels.unknown'),
  };
  const MASTERY_BG: Record<string, string> = {
    mastered: 'bg-[#34C759]', stable: 'bg-[#0071E3]', learning: 'bg-[#FF9500]', weak: 'bg-[#FF3B30]', unknown: 'bg-[#AEAEB2]',
  };
  if (!node) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground bg-card rounded-2xl border border-border/50 p-6">
        <Stack className="h-8 w-8 mb-3 opacity-20" />
        <p className="text-xs font-bold uppercase tracking-widest">{t('detailPanel.selectTitle')}</p>
        <p className="text-[10px] mt-1 opacity-50">{t('detailPanel.selectHint')}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-card rounded-2xl border border-border/50 overflow-hidden">
      {/* header */}
      <div className="p-4 border-b border-border/30 flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <Badge className={cn('text-[9px] py-0 h-5 px-2 font-bold uppercase border', LEVEL_COLORS[node.level] || 'bg-muted')}>
            {t(`levels.${node.level}` as any) || node.level}
          </Badge>
          <h3 className="text-sm font-bold truncate">{node.name}</h3>
          {masteryData[String(node.id)] && (
            <Badge className={cn('text-[9px] text-white py-0 h-5 px-2 font-bold', MASTERY_BG[masteryData[String(node.id)]] || 'bg-muted')}>
              {MASTERY_LABELS[masteryData[String(node.id)]] || masteryData[String(node.id)]}
            </Badge>
          )}
        </div>
        <Button variant="ghost" size="icon" className="h-7 w-7 rounded-lg shrink-0" onClick={onClear}>
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>

      {/* content */}
      <ScrollArea className="flex-1">
        <div className="p-4 space-y-5">
          {node.description && (
            <div className="text-xs text-muted-foreground leading-relaxed">
              <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                {processMathContent(node.description)}
              </ReactMarkdown>
            </div>
          )}

          {loading ? (
            <p className="text-[10px] font-medium text-muted-foreground text-center py-8">Loading...</p>
          ) : (
            <>
              <section>
                <h5 className="text-[10px] font-semibold tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
                  <Target className="w-3 h-3" /> {t('detailPanel.relatedQuestions')} ({details.questions.length})
                </h5>
                <div className="space-y-1.5">
                  {details.questions.length === 0 && (
                    <p className="text-[10px] text-muted-foreground/50">{t('detailPanel.noQuestions')}</p>
                  )}
                  {details.questions.map((q: any) => (
                    <button
                      key={q.id}
                      onClick={() => onQuestionClick(q)}
                      className="w-full p-3 bg-muted/50 hover:bg-muted rounded-xl flex items-center gap-2 text-left transition-colors group"
                    >
                      <Badge variant="outline" className="text-[8px] py-0 h-4 uppercase shrink-0">{q.subjective_type || q.q_type || 'Q'}</Badge>
                      <span className="text-[11px] font-medium truncate flex-1">
                        <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                          {processMathContent(q.text)}
                        </ReactMarkdown>
                      </span>
                      <ArrowsOut className="w-3 h-3 text-muted-foreground/40 opacity-0 group-hover:opacity-100 transition-all shrink-0" />
                    </button>
                  ))}
                </div>
              </section>

              <section>
                <h5 className="text-[10px] font-semibold tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
                  <Video className="w-3 h-3" /> {t('detailPanel.courseResources')} ({details.courses.length})
                </h5>
                <div className="space-y-1.5">
                  {details.courses.length === 0 && (
                    <p className="text-[10px] text-muted-foreground/50">{t('detailPanel.noCourses')}</p>
                  )}
                  {details.courses.map((c: any) => (
                    <div key={c.id} className="p-3 bg-emerald-50/50 rounded-xl flex items-center gap-2 border border-emerald-100">
                      <Video className="w-3 h-3 text-emerald-500 shrink-0" />
                      <p className="text-[11px] font-medium truncate">{c.title}</p>
                    </div>
                  ))}
                </div>
              </section>

              <section>
                <h5 className="text-[10px] font-semibold tracking-wider text-muted-foreground mb-2 flex items-center gap-1.5">
                  <FileText className="w-3 h-3" /> {t('detailPanel.referenceArticles')} ({details.articles.length})
                </h5>
                <div className="space-y-1.5">
                  {details.articles.length === 0 && (
                    <p className="text-[10px] text-muted-foreground/50">{t('detailPanel.noArticles')}</p>
                  )}
                  {details.articles.map((a: any) => (
                    <div key={a.id} className="p-3 bg-orange-50/50 rounded-xl flex items-center gap-2 border border-orange-100">
                      <FileText className="w-3 h-3 text-orange-500 shrink-0" />
                      <p className="text-[11px] font-medium truncate">{a.title}</p>
                    </div>
                  ))}
                </div>
              </section>
            </>
          )}
        </div>
      </ScrollArea>
    </div>
  );
};
