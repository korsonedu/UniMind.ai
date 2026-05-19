import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { formatApiErrorToast } from '@/lib/apiError';
import api from '@/lib/api';
import { Upload, FileText, Sparkles, ChevronDown, ChevronUp, Target, Lightbulb, PenLine, X, Loader2 } from 'lucide-react';

interface ResumeRecord {
  id: number;
  score: number | null;
  diagnostics: string;
  optimized_content: Record<string, any>;
  predicted_questions: string[];
  parsed_content: string;
  created_at: string;
}

export const ResumeTuner: React.FC = () => {
  const [text, setText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [records, setRecords] = useState<ResumeRecord[]>([]);
  const [loadingRecords, setLoadingRecords] = useState(false);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const { t, i18n } = useTranslation('interviews');
  const dropRef = useRef<HTMLDivElement>(null);

  const fetchRecords = useCallback(async () => {
    setLoadingRecords(true);
    try {
      const res = await api.get('/interviews/resume/tune/');
      setRecords((res.data?.results || []) as ResumeRecord[]);
    } catch {
      // silent
    } finally {
      setLoadingRecords(false);
    }
  }, []);

  useEffect(() => { fetchRecords(); }, [fetchRecords]);

  const handleSubmit = async () => {
    if (!text.trim() && !file) { toast.error(t('resumeTuner.fillRequired')); return; }
    setSaving(true);
    try {
      const fd = new FormData();
      if (text.trim()) fd.append('resume_text', text.trim());
      if (file) fd.append('file', file);
      await api.post('/interviews/resume/tune/', fd);
      setText('');
      setFile(null);
      await fetchRecords();
      toast.success(t('resumeTuner.analysisComplete'));
    } catch (e) {
      toast.error(formatApiErrorToast(e, t('resumeTuner.analysisFailed')));
    } finally {
      setSaving(false);
    }
  };

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') setDragOver(true);
    else if (e.type === 'dragleave') setDragOver(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f && ['.pdf', '.docx', '.doc', '.txt'].some(ext => f.name.toLowerCase().endsWith(ext))) {
      setFile(f); setText('');
    } else {
      toast.error(t('resumeTuner.unsupportedFormat'));
    }
  }, []);

  const renderExpanded = (r: ResumeRecord) => {
    const optimizedEntries = (() => {
      const oc = r.optimized_content;
      if (!oc || typeof oc !== 'object') return [];
      return Object.entries(oc).filter(([k]) => k !== 'score' && k !== 'diagnostics');
    })();

    const hasContent = r.diagnostics || optimizedEntries.length > 0 || r.predicted_questions.length > 0;

    return (
    <div className="mt-4 space-y-4 animate-in fade-in slide-in-from-top-2 duration-300">
      {!hasContent && (
        <div className="rounded-2xl bg-slate-50/80 border border-slate-200/60 p-4">
          <p className="text-[13px] text-muted-foreground text-center">
            {t('resumeTuner.noData')}
          </p>
        </div>
      )}

      {r.diagnostics && (
        <div className="rounded-2xl bg-amber-50/80 border border-amber-200/60 p-4">
          <div className="flex items-center gap-2 mb-2">
            <Target className="h-3.5 w-3.5 text-amber-600" />
            <p className="text-[11px] font-black text-amber-700 uppercase tracking-widest">{t('resumeTuner.diagnosis')}</p>
          </div>
          <p className="text-[13px] text-amber-800 leading-relaxed">{r.diagnostics}</p>
        </div>
      )}

      {optimizedEntries.length > 0 && (
        <div className="rounded-2xl bg-emerald-50/80 border border-emerald-200/60 p-4">
          <div className="flex items-center gap-2 mb-2">
            <PenLine className="h-3.5 w-3.5 text-emerald-600" />
            <p className="text-[11px] font-black text-emerald-700 uppercase tracking-widest">{t('resumeTuner.polish')}</p>
          </div>
          <div className="space-y-2">
            {optimizedEntries.map(([key, val]) => (
              <div key={key}>
                <p className="text-[11px] font-bold text-emerald-600/80 capitalize">{key}</p>
                <p className="text-[13px] text-emerald-800 leading-relaxed">{typeof val === 'string' ? val : JSON.stringify(val)}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {r.predicted_questions.length > 0 && (
        <div className="rounded-2xl bg-indigo-50/80 border border-indigo-200/60 p-4">
          <div className="flex items-center gap-2 mb-2">
            <Lightbulb className="h-3.5 w-3.5 text-indigo-600" />
            <p className="text-[11px] font-black text-indigo-700 uppercase tracking-widest">{t('resumeTuner.predictedQuestions')}</p>
          </div>
          <ul className="space-y-1.5">
            {r.predicted_questions.map((q, i) => (
              <li key={i} className="text-[13px] text-indigo-800 flex items-start gap-2">
                <span className="text-indigo-400 font-black shrink-0 mt-0.5">{i + 1}.</span>
                {q}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
      {/* Left: submit form */}
      <Card className="p-5 rounded-2xl border border-border/60 space-y-4">
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 rounded-xl bg-gradient-to-br from-indigo-500/20 to-purple-500/20 flex items-center justify-center">
            <Sparkles className="h-4 w-4 text-indigo-600" />
          </div>
          <div>
            <p className="text-sm font-black tracking-tight">{t('resumeTuner.title')}</p>
            <p className="text-[11px] text-muted-foreground font-medium">{t('resumeTuner.subtitle')}</p>
          </div>
        </div>

        {/* Drop zone */}
        <div
          ref={dropRef}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          className={`relative rounded-2xl border-2 border-dashed transition-all duration-200 p-6 text-center cursor-pointer ${
            dragOver
              ? 'border-indigo-400 bg-indigo-50/50 scale-[1.01]'
              : file
              ? 'border-emerald-300 bg-emerald-50/30'
              : 'border-border/60 hover:border-slate-300 hover:bg-slate-50/50'
          }`}
          onClick={() => document.getElementById('resume-file-input')?.click()}
        >
          {file ? (
            <div className="space-y-1">
              <div className="h-10 w-10 rounded-2xl bg-emerald-100 flex items-center justify-center mx-auto">
                <FileText className="h-5 w-5 text-emerald-600" />
              </div>
              <p className="text-sm font-bold text-emerald-700 truncate max-w-[200px] mx-auto">{file.name}</p>
              <p className="text-[11px] text-emerald-500 font-medium">{(file.size / 1024).toFixed(1)} KB</p>
              <button
                className="text-[11px] font-bold text-muted-foreground hover:text-destructive transition-colors"
                onClick={(e) => { e.stopPropagation(); setFile(null); }}
              >
                {t('resumeTuner.remove')}
              </button>
            </div>
          ) : (
            <div className="space-y-1">
              <div className="h-10 w-10 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto">
                <Upload className="h-5 w-5 text-slate-400" />
              </div>
              <p className="text-[13px] font-bold text-muted-foreground">{t('resumeTuner.dragHint')}</p>
              <p className="text-[11px] text-muted-foreground/60 font-medium">{t('resumeTuner.formatHint')}</p>
            </div>
          )}
        </div>
        <input
          id="resume-file-input"
          type="file"
          accept=".pdf,.doc,.docx,.txt"
          className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) { setFile(f); setText(''); } }}
        />

        {/* Divider */}
        <div className="flex items-center gap-3">
          <div className="flex-1 h-px bg-border/60" />
          <span className="text-[10px] font-black text-muted-foreground/50 uppercase tracking-widest">{t('resumeTuner.or')}</span>
          <div className="flex-1 h-px bg-border/60" />
        </div>

        {/* Text input */}
        <div className="relative">
          <textarea
            value={text}
            onChange={(e) => { setText(e.target.value); if (e.target.value) setFile(null); }}
            className="w-full min-h-[100px] rounded-2xl border border-border/60 bg-slate-50/50 p-4 text-[13px] leading-relaxed resize-none placeholder:text-muted-foreground/40 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-all"
            placeholder={t('resumeTuner.pastePlaceholder')}
          />
          {text && (
            <button
              className="absolute top-3 right-3 h-6 w-6 rounded-full bg-slate-200/80 flex items-center justify-center hover:bg-slate-300 transition-colors"
              onClick={() => setText('')}
            >
              <X className="h-3 w-3 text-slate-500" />
            </button>
          )}
        </div>

        <Button
          className="w-full h-11 rounded-2xl bg-slate-900 text-white text-[13px] font-extrabold hover:bg-slate-800 transition-all active:scale-[0.98]"
          onClick={handleSubmit}
          disabled={saving || (!text.trim() && !file)}
        >
          {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Sparkles className="h-4 w-4 mr-2" />}
          {saving ? t('resumeTuner.analyzing') : t('resumeTuner.submit')}
        </Button>
      </Card>

      {/* Right: history */}
      <div className="rounded-2xl border border-border/60 bg-card text-card-foreground shadow-sm flex flex-col" style={{ height: '500px' }}>
        <div className="flex items-center justify-between p-5 pb-3 shrink-0">
          <p className="text-sm font-black tracking-tight">{t('resumeTuner.history')}</p>
          {records.length > 0 && (
            <Badge variant="secondary" className="text-[10px] font-bold">{records.length}</Badge>
          )}
        </div>

        {loadingRecords ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : records.length === 0 ? (
          <div className="text-center py-12 space-y-2 px-5">
            <div className="h-10 w-10 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto">
              <FileText className="h-5 w-5 text-slate-300" />
            </div>
            <p className="text-[13px] font-bold text-muted-foreground">{t('resumeTuner.noHistory')}</p>
            <p className="text-[11px] text-muted-foreground/50 font-medium">{t('resumeTuner.noHistoryHint')}</p>
          </div>
        ) : (
          <div className="space-y-2 flex-1 overflow-y-auto px-5 pb-5 min-h-0">
            {records.map((r) => (
              <div
                key={r.id}
                className="rounded-2xl border border-border/60 bg-white hover:border-slate-300 transition-all"
              >
                <button
                  className="w-full px-4 py-3 flex items-center justify-between text-left"
                  onClick={() => setExpandedId(expandedId === r.id ? null : r.id)}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    {r.score != null && (
                      <span className={`shrink-0 text-[11px] font-black px-2 py-0.5 rounded-lg ${
                        r.score >= 80 ? 'bg-emerald-100 text-emerald-700' :
                        r.score >= 60 ? 'bg-amber-100 text-amber-700' :
                        'bg-red-100 text-red-700'
                      }`}>
                        {t('resumeTuner.score', { score: r.score })}
                      </span>
                    )}
                    <div className="min-w-0">
                      <p className="text-[13px] font-bold truncate">
                        {t('resumeTuner.recordNumber', { id: r.id })}
                      </p>
                      <p className="text-[10px] text-muted-foreground/50 font-medium">
                        {new Date(r.created_at).toLocaleDateString(i18n.language?.startsWith('zh') ? 'zh-CN' : 'en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                      </p>
                    </div>
                  </div>
                  {expandedId === r.id ? (
                    <ChevronUp className="h-4 w-4 text-muted-foreground shrink-0" />
                  ) : (
                    <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
                  )}
                </button>
                {expandedId === r.id && (
                  <div className="px-4 pb-4">{renderExpanded(r)}</div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
