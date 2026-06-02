import React from 'react';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/EmptyState';
import type { MockExamItem } from './types';

interface AiExamTabProps {
  loading: boolean;
  creating: boolean;
  failed: string;
  items: MockExamItem[];
  onCreate: () => void;
  onDelete: (id: number) => void;
}

export const AiExamTab: React.FC<AiExamTabProps> = ({
  loading, creating, failed, items, onCreate, onDelete,
}) => {
  const { t, i18n } = useTranslation('pdfMockExam');

  return (
    <>
      <Card className="p-5 rounded-lg border border-border flex items-center justify-between max-md:flex-col max-md:items-start max-md:gap-3">
        <div>
          <p className="text-sm font-bold">{t('aiSection.title')}</p>
          <p className="text-xs text-muted-foreground mt-1">{t('aiSection.description')}</p>
        </div>
        <Button className="rounded-lg text-xs font-medium max-md:w-full" onClick={onCreate} disabled={creating}>
          {creating ? t('aiSection.generating') : t('aiSection.generate')}
        </Button>
      </Card>

      {loading ? (
        <Card className="p-10 rounded-lg border border-border text-center text-sm font-medium text-muted-foreground">{t('aiSection.loading')}</Card>
      ) : failed ? (
        <Card className="p-10 rounded-lg border border-red-200 bg-red-50/70 text-center text-sm font-medium text-red-700">{failed}</Card>
      ) : items.length === 0 ? (
        <Card className="p-6 rounded-lg border border-border"><EmptyState title={t('aiSection.noHistory')} className="py-4" /></Card>
      ) : (
        items.map((item) => (
          <Card key={item.id} className={`p-4 rounded-lg border ${item.status === 'processing' ? 'border-amber-200 bg-amber-50/40' : 'border-border'}`}>
            <div className="flex items-center justify-between gap-3 max-md:flex-col max-md:items-start">
              <div>
                <p className="text-sm font-bold">
                  {t('aiSection.aiLabel', { id: item.id })}
                  {item.status === 'processing' && <span className="ml-2 text-amber-600 text-xs font-medium animate-pulse">{t('aiSection.statusProcessing')}</span>}
                  {item.status === 'ready' && <span className="ml-2 text-green-600 text-xs">{t('aiSection.statusReady')}</span>}
                  {item.status === 'failed' && <span className="ml-2 text-red-600 text-xs">{t('aiSection.statusFailed')}</span>}
                </p>
                {item.status !== 'processing' && (
                  <p className="text-xs text-muted-foreground mt-1">
                    {t('aiSection.questionInfo', { count: item.question_count, coverage: item.weak_coverage })} · {new Date(item.created_at).toLocaleString(i18n.language?.startsWith('zh') ? 'zh-CN' : 'en-US')}
                  </p>
                )}
                {item.error_message ? <p className="text-xs text-red-600 mt-1">{item.error_message}</p> : null}
              </div>
              <div className="flex gap-2 shrink-0 max-md:w-full max-md:justify-end">
                {item.status === 'ready' && (
                  <>
                    <Button size="sm" variant="outline" className="h-8 text-[11px]" onClick={() => window.open(item.exam_pdf_url, '_blank', 'noopener,noreferrer')}>
                      {t('aiSection.downloadExam')}
                    </Button>
                    <Button size="sm" variant="outline" className="h-8 text-[11px]" onClick={() => window.open(item.answer_pdf_url, '_blank', 'noopener,noreferrer')}>
                      {t('aiSection.downloadAnswer')}
                    </Button>
                  </>
                )}
                <Button size="sm" variant="ghost" className="h-8 text-[11px] text-red-500 hover:text-red-700" onClick={() => onDelete(item.id)}>
                  {t('aiSection.delete')}
                </Button>
              </div>
            </div>
          </Card>
        ))
      )}
    </>
  );
};
