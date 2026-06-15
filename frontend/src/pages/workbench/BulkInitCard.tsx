import { useState, useEffect } from 'react';
import { Sparkle, Spinner } from '@phosphor-icons/react';
import api from '@/lib/api';
import { Slider } from '@/components/ui/slider';
import { Button } from '@/components/ui/button';

interface BulkInitStatus {
  eligible: boolean;
  has_used: boolean;
  kp_count: number;
  max_questions: number;
  available_subjects: string[];
}

const DISMISS_KEY = 'unimind_bulk_init_dismissed';

export function BulkInitCard() {
  const [status, setStatus] = useState<BulkInitStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [subject, setSubject] = useState('');
  const [questionCount, setQuestionCount] = useState(150);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem(DISMISS_KEY) === '1'
  );

  useEffect(() => {
    api.get('/users/institution/me/bulk-init/')
      .then(res => {
        const d: BulkInitStatus = res.data;
        setStatus(d);
        if (d.available_subjects.length === 1) {
          setSubject(d.available_subjects[0]);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading || !status || !status.eligible || done || dismissed) return null;

  const handleGenerate = async () => {
    setSubmitting(true);
    try {
      await api.post('/quizzes/admin/bulk-pipeline/', {
        subject: subject || undefined,
        total_target: questionCount,
      });
      setDone(true);
    } catch (e: any) {
      if (e?.response?.data?.code === 'bulk_init_already_used') {
        setDone(true);
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div id="bulk-init-card" className="rounded-lg border border-primary/15 bg-primary/[0.02] p-3 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Sparkle className="h-4 w-4 text-primary/60" weight="fill" />
          <span className="text-xs font-bold text-muted-foreground">初始化题库</span>
        </div>
        <button
          onClick={() => { setDismissed(true); localStorage.setItem(DISMISS_KEY, '1'); }}
          className="text-[10px] text-muted-foreground/50 hover:text-muted-foreground transition-colors"
        >
          稍后
        </button>
      </div>

      <p className="text-xs text-muted-foreground leading-relaxed">
        已设置 {status.kp_count} 个知识点，AI 可批量生成题目。之后你可以手动出题或使用 ARC 精修。
      </p>

      {/* Subject selector */}
      {status.available_subjects.length > 1 && (
        <div className="flex flex-wrap gap-1">
          {status.available_subjects.slice(0, 8).map(s => (
            <button
              key={s}
              onClick={() => setSubject(s)}
              className={`text-[11px] font-bold px-2 py-0.5 rounded border transition-colors ${
                subject === s
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border text-muted-foreground hover:border-primary/30'
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Question count */}
      <div className="flex items-center gap-3">
        <Slider
          value={[questionCount]}
          onValueChange={([v]) => setQuestionCount(v)}
          min={50}
          max={status.max_questions}
          step={50}
          className="flex-1"
        />
        <span className="text-xs font-black text-primary w-12 text-right">{questionCount}</span>
      </div>

      <Button
        onClick={handleGenerate}
        disabled={submitting}
        className="w-full h-7 text-xs"
        size="sm"
      >
        {submitting ? (
          <>
            <Spinner className="h-3 w-3 animate-spin mr-1.5" />
            生成中...
          </>
        ) : (
          '开始生成'
        )}
      </Button>
    </div>
  );
}
