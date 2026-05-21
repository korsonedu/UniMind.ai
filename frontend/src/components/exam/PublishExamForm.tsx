import React, { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import api from '@/lib/api';
import { formatApiErrorToast } from '@/lib/apiError';

interface PublishExamFormProps {
  onPublished: () => void;
}

export const PublishExamForm: React.FC<PublishExamFormProps> = ({ onPublished }) => {
  const [title, setTitle] = useState('');
  const [desc, setDesc] = useState('');
  const [saving, setSaving] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const { t } = useTranslation('pdfMockExam');

  const submit = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file || !title.trim()) {
      toast.error(t('toast.fillTitle'));
      return;
    }
    setSaving(true);
    try {
      const fd = new FormData();
      fd.append('title', title.trim());
      fd.append('description', desc.trim());
      fd.append('exam_pdf', file);
      await api.post('/quizzes/teacher-exams/create/', fd);
      toast.success(t('toast.examPublished'));
      setTitle('');
      setDesc('');
      if (fileRef.current) fileRef.current.value = '';
      setExpanded(false);
      onPublished();
    } catch (e) {
      toast.error(formatApiErrorToast(e, t('toast.publishFailed')));
    } finally {
      setSaving(false);
    }
  };

  if (!expanded) {
    return (
      <div className="flex justify-end">
        <Button size="sm" variant="apple" onClick={() => setExpanded(true)}>
          {t('aiSection.publishNew')}
        </Button>
      </div>
    );
  }

  return (
    <div className="p-4 rounded-lg border border-primary/30 bg-primary/5 space-y-3">
      <p className="text-sm font-bold">{t('publishDialog.title')}</p>
      <Input
        placeholder={t('publishDialog.titlePlaceholder')}
        className="h-10 rounded-lg"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        autoComplete="off"
      />
      <textarea
        placeholder={t('publishDialog.descriptionPlaceholder')}
        className="flex w-full rounded-lg border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        rows={2}
        value={desc}
        onChange={(e) => setDesc(e.target.value)}
      />
      <Input ref={fileRef} type="file" accept=".pdf" className="h-10 text-xs rounded-lg" />
      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={() => setExpanded(false)}>{t('publishDialog.cancel')}</Button>
        <Button size="sm" onClick={submit} disabled={saving}>
          {saving ? t('publishDialog.saving') : t('publishDialog.submit')}
        </Button>
      </div>
    </div>
  );
};
