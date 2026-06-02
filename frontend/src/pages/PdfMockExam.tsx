import React, { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { PageWrapper } from '@/components/PageWrapper';
import api from '@/lib/api';
import { formatApiErrorToast } from '@/lib/apiError';
import { toast } from 'sonner';
import { useAuthStore } from '@/store/useAuthStore';
import { AiExamTab } from '@/components/exam/AiExamTab';
import { TeacherExamTab } from '@/components/exam/TeacherExamTab';
import type { MockExamItem, TeacherExamItem } from '@/components/exam/types';

export const PdfMockExam: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'ai' | 'teacher'>('ai');
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [items, setItems] = useState<MockExamItem[]>([]);
  const [teacherItems, setTeacherItems] = useState<TeacherExamItem[]>([]);
  const [failed, setFailed] = useState('');
  const { t } = useTranslation('pdfMockExam');
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.is_admin || user?.is_institution_admin || user?.role === 'admin';

  const loadData = useCallback(async () => {
    setLoading(true);
    setFailed('');
    try {
      const res = await api.get('/quizzes/personalized-mock-exams/');
      setItems((res.data?.results || []) as MockExamItem[]);
      const tRes = await api.get('/quizzes/teacher-exams/');
      setTeacherItems((tRes.data?.results || []) as TeacherExamItem[]);
    } catch (e) {
      setFailed(formatApiErrorToast(e, t('toast.loadDataFailed')));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => { loadData(); }, []);

  useEffect(() => {
    if (!items.some((i) => i.status === 'processing')) return;
    const timer = setInterval(loadData, 5000);
    return () => clearInterval(timer);
  }, [items, loadData]);

  const createExam = async () => {
    setCreating(true);
    try {
      await api.post('/quizzes/personalized-mock-exams/', {});
      toast.success(t('toast.aiTaskSubmitted'));
      await loadData();
    } catch (e) {
      toast.error(formatApiErrorToast(e, t('toast.generateFailed')));
    } finally {
      setCreating(false);
    }
  };

  const deleteExam = async (examId: number) => {
    try {
      await api.delete(`/quizzes/personalized-mock-exams/?id=${examId}`);
      toast.success(t('toast.deleted'));
      await loadData();
    } catch (e) {
      toast.error(formatApiErrorToast(e, t('toast.deleteFailed')));
    }
  };

  return (
    <PageWrapper title={t('pageTitle')} subtitle={t('pageSubtitle')}>
      <div className="max-w-4xl mx-auto space-y-4 pb-16 px-4 md:px-0">
        <div className="flex items-center gap-4 border-b border-border overflow-x-auto">
          <button
            onClick={() => setActiveTab('ai')}
            className={`text-sm font-bold pb-2 border-b-2 transition-colors whitespace-nowrap ${
              activeTab === 'ai' ? 'border-foreground text-foreground' : 'border-transparent text-muted-foreground'
            }`}
          >
            {t('tabAI')}
          </button>
          <button
            onClick={() => setActiveTab('teacher')}
            className={`text-sm font-bold pb-2 border-b-2 transition-colors whitespace-nowrap ${
              activeTab === 'teacher' ? 'border-foreground text-foreground' : 'border-transparent text-muted-foreground'
            }`}
          >
            {t('tabTeacher')}
          </button>
        </div>

        {activeTab === 'ai' ? (
          <AiExamTab
            loading={loading}
            creating={creating}
            failed={failed}
            items={items}
            onCreate={createExam}
            onDelete={deleteExam}
          />
        ) : (
          <TeacherExamTab
            loading={loading}
            failed={failed}
            items={teacherItems}
            isAdmin={isAdmin}
            onRefresh={loadData}
          />
        )}
      </div>
    </PageWrapper>
  );
};
