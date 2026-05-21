import React, { useState, useEffect, useRef } from 'react';
import type { ChangeEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Search, Upload, FileUp, RefreshCcw, ChevronDown, ChevronRight, Edit3, Trash2, Sparkles, Check, X, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import api from '@/lib/api';
import 'katex/dist/katex.min.css';
import { toast } from 'sonner';

const AI_TYPE_OPTIONS = [
  { typeKey: 'objective', icon: '🎯' },
  { typeKey: 'noun', icon: '📝' },
  { typeKey: 'short', icon: '📄' },
  { typeKey: 'essay', icon: '💡' },
  { typeKey: 'calculate', icon: '🔢' },
];

const AI_DIFFICULTY_OPTIONS = [
  { value: 'entry' },
  { value: 'easy' },
  { value: 'normal' },
  { value: 'hard' },
  { value: 'extreme' },
  { value: 'mixed' },
];

const AI_TYPE_RATIO_PRESET_OPTIONS = [
  { value: 'balanced' },
  { value: 'objective_focus' },
  { value: 'subjective_focus' },
  { value: 'sprint_mix' },
];

const AI_TYPE_RATIO_PRESET_MAP: Record<string, Record<string, number>> = {
  balanced: { objective: 0.3, noun: 0.15, short: 0.2, essay: 0.2, calculate: 0.15 },
  objective_focus: { objective: 0.55, noun: 0.1, short: 0.15, essay: 0.1, calculate: 0.1 },
  subjective_focus: { objective: 0.15, noun: 0.2, short: 0.3, essay: 0.25, calculate: 0.1 },
  sprint_mix: { objective: 0.2, noun: 0.1, short: 0.2, essay: 0.25, calculate: 0.25 },
};

export const QuestionBankPanel = ({ kpList, onEdit, onDelete }: { kpList: any[], onEdit: (q: any) => void, onDelete: (id: number) => void }) => {
  const { t } = useTranslation('maintenance');
  const DEFAULT_AI_TYPES: string[] = [];
  // Prevent AI timeout/failure from too many questions per request
  const MAX_AI_TOTAL = 10; // Max total questions per generation
  const [bankSearch, setBankSearch] = useState('');
  const [bankKP, setBankKP] = useState('0');
  const [bankType, setBankType] = useState('all');
  const [bankPage, setBankPage] = useState(1);
  const [bankData, setBankData] = useState<{ total: number, total_pages: number, results: any[] }>({ total: 0, total_pages: 1, results: [] });
  const [expanded, setExpanded] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // AI Smart Generate State
  const [showAIModal, setShowAIModal] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [genCount, setGenCount] = useState(3);
  const [selectedKPs, setSelectedKPs] = useState<number[]>([]);
  const [selectedTypes, setSelectedTypes] = useState<string[]>(DEFAULT_AI_TYPES);
  const [selectedTypeRatioPreset, setSelectedTypeRatioPreset] = useState('balanced');
  const [selectedDifficulty, setSelectedDifficulty] = useState('normal');
  const [previewQuestions, setPreviewQuestions] = useState<any[]>([]);
  const [showPreview, setShowPreview] = useState(false);

  const invalidDifficultyCount = previewQuestions.filter(q => q.difficulty_check_passed === false).length;

  const getTypeLabel = (typeKey: string) => {
    const map: Record<string, string> = {
      objective: t('questionBank.typeObjective'),
      noun: t('questionBank.typeNoun'),
      short: t('questionBank.typeShort'),
      essay: t('questionBank.typeEssay'),
      calculate: t('questionBank.typeCalculate'),
    };
    return map[typeKey] || typeKey;
  };

  const getDifficultyLabel = (value: string) => {
    const map: Record<string, string> = {
      entry: t('questionBank.difficultyEntry'),
      easy: t('questionBank.difficultyEasy'),
      normal: t('questionBank.difficultyNormal'),
      hard: t('questionBank.difficultyHard'),
      extreme: t('questionBank.difficultyExtreme'),
      mixed: t('questionBank.difficultyMixed'),
    };
    return map[value] || value;
  };

  const getPresetLabel = (value: string) => {
    const map: Record<string, string> = {
      balanced: t('questionBank.ratioBalanced'),
      objective_focus: t('questionBank.ratioObjectiveFocus'),
      subjective_focus: t('questionBank.ratioSubjectiveFocus'),
      sprint_mix: t('questionBank.ratioSprintMix'),
    };
    return map[value] || value;
  };

  const autoResizeTextarea = (el: HTMLTextAreaElement | null) => {
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  };

  const buildTypeRatioPayload = () => {
    const baseRatio = AI_TYPE_RATIO_PRESET_MAP[selectedTypeRatioPreset] || AI_TYPE_RATIO_PRESET_MAP.balanced;
    const enabledSet = new Set(selectedTypes);
    const filteredEntries = Object.entries(baseRatio).filter(([typeKey, weight]) => enabledSet.has(typeKey) && weight > 0);
    const total = filteredEntries.reduce((sum, [, weight]) => sum + weight, 0);

    if (total > 0) {
      const normalized: Record<string, number> = {};
      filteredEntries.forEach(([typeKey, weight]) => {
        normalized[typeKey] = Number((weight / total).toFixed(4));
      });
      return normalized;
    }

    if (selectedTypes.length > 0) {
      const equalWeight = Number((1 / selectedTypes.length).toFixed(4));
      return selectedTypes.reduce((acc, typeKey) => ({ ...acc, [typeKey]: equalWeight }), {} as Record<string, number>);
    }

    return {};
  };

  const fetchBank = async (page = bankPage) => {
    setLoading(true);
    try {
      const res = await api.get('/quizzes/admin/questions/', {
        params: {
          search: bankSearch || undefined, kp_id: bankKP !== '0' ? bankKP : undefined,
          q_type: bankType !== 'all' ? bankType : undefined, page, page_size: 50
        }
      });
      setBankData(res.data);
    } catch (e) { toast.error(t('questionBank.loadFailed')); }
    setLoading(false);
  };

  useEffect(() => { setBankPage(1); fetchBank(1); }, [bankSearch, bankKP, bankType]);

  const handleExport = async () => {
    try {
      const res = await api.get('/quizzes/admin/export-structured/', { params: { kp_id: bankKP !== '0' ? bankKP : undefined } });
      toast.success(res.data.message || t('questionBank.exportSuccess', { total: res.data.total }));
    } catch (e) { toast.error(t('questionBank.exportFailed')); }
  };

  const handleImportCSV = async (e: ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const fd = new FormData();
      fd.append('file', file);
      try {
          const res = await api.post('/quizzes/import-csv/', fd);
          toast.success(t('questionBank.importSuccess', { count: res.data.count }));
          fetchBank(1);
      } catch (e: any) {
          toast.error(e.response?.data?.error || t('questionBank.importFailed'));
      }
      e.target.value = '';
  };

  const handleAIGenerate = async () => {
    if (selectedKPs.length === 0) return toast.error(t('questionBank.pleaseSelectKp'));
    if (selectedTypes.length === 0) return toast.error(t('questionBank.pleaseSelectType'));
    const totalRequested = selectedKPs.length * genCount;
    if (totalRequested > MAX_AI_TOTAL) {
      return toast.error(t('questionBank.maxGenExceeded', { max: MAX_AI_TOTAL }));
    }
    if (totalRequested > MAX_AI_TOTAL - 2) {
      toast.warning(t('questionBank.genSlowWarning', { total: totalRequested }));
    }
    setIsGenerating(true);
    try {
      const res = await api.post('/quizzes/ai-smart-generate-preview/', {
          kp_ids: selectedKPs,
          count: genCount,
          types: selectedTypes,
          difficulty_level: selectedDifficulty,
          type_ratio: buildTypeRatioPayload(),
      });
      setPreviewQuestions(res.data.questions);
      setShowAIModal(false);
      setShowPreview(true);
    } catch (e: any) {
      toast.error(e?.response?.data?.error || t('questionBank.generateFailed'));
    }
    finally { setIsGenerating(false); }
  };

  const handleConfirmSave = async () => {
    setIsSaving(true);
    try {
      const res = await api.post('/quizzes/ai-smart-generate-confirm/', { questions: previewQuestions });
      const data = res.data || {};

      if (data.status === 'partial_success') {
        const failedIndexes = new Set<number>((data.errors || []).map((item: any) => Number(item.index) - 1));
        const failedQuestions = previewQuestions.filter((_, index) => failedIndexes.has(index));
        setPreviewQuestions(failedQuestions);
        const errMsg = data.error || t('questionBank.partialFail');
        const sampleInfo = data.errors?.[0]?.error ? ` — ${data.errors[0].error}` : '';
        toast.warning(errMsg + sampleInfo);
      } else {
        toast.success(t('questionBank.importSuccess', { count: data.count ?? previewQuestions.length }));
        setShowPreview(false);
        setPreviewQuestions([]);
      }
      fetchBank(1);
    } catch (e: any) {
      const errData = e?.response?.data;
      const firstErr = errData?.errors?.[0]?.error;
      toast.error(errData?.error || firstErr || t('questionBank.importFailed'));
    }
    finally { setIsSaving(false); }
  };

  const resetAIGenerateState = () => {
    setGenCount(3);
    setSelectedKPs([]);
    setSelectedTypes([...DEFAULT_AI_TYPES]);
    setSelectedTypeRatioPreset('balanced');
    setSelectedDifficulty('normal');
  };

  useEffect(() => {
    if (showAIModal) resetAIGenerateState();
  }, [showAIModal]);

  const toggleKP = (id: number) => {
    setSelectedKPs(prev => prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]);
  };

  const toggleType = (type: string) => {
      setSelectedTypes(prev => prev.includes(type) ? prev.filter(t => t !== type) : [...prev, type]);
  };

  // Recursively flatten knowledge tree, extract all leaf KP nodes
  const getAllLeafKPs = (list: any[]) => {
    let leafs: any[] = [];
    list.forEach(item => {
      if (item.level === 'kp') {
        leafs.push(item);
      }
      if (item.children && item.children.length > 0) {
        leafs = [...leafs, ...getAllLeafKPs(item.children)];
      }
    });
    return leafs;
  };

  const leafKPs = getAllLeafKPs(kpList);

  const updatePreviewQuestion = (index: number, field: string, value: any) => {
    const updated = [...previewQuestions];
    if (field === 'option') {
        const { key, val } = value;
        updated[index].options[key] = val;
    } else {
        updated[index][field] = value;
    }
    setPreviewQuestions(updated);
  };

  useEffect(() => {
    const nodes = document.querySelectorAll<HTMLTextAreaElement>('[data-ai-option-textarea="true"]');
    nodes.forEach(autoResizeTextarea);
  }, [previewQuestions]);

  const getQuestionTypeLabel = (q: any) => {
    if (q.q_type === 'objective') return t('questionBank.typeObjective');
    if (q.subjective_type === 'noun') return t('questionBank.typeNoun');
    if (q.subjective_type === 'short') return t('questionBank.typeShort');
    if (q.subjective_type === 'essay') return t('questionBank.typeEssay');
    if (q.subjective_type === 'calculate') return t('questionBank.typeCalculate');
    return t('questionBank.typeSubjective');
  };

  return (
    <Card className="border-none shadow-sm rounded-[2rem] bg-white border border-black/[0.03] overflow-hidden flex flex-col" style={{ height: 'calc(100vh - 260px)', minHeight: '600px' }}>
      <div className="p-4 border-b border-black/[0.03] bg-slate-50/50 space-y-3 shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-bold text-black/40 uppercase tracking-widest">{t('questionBank.browseTitle')}</span>
            <span className="text-[11px] font-bold bg-black text-white rounded-full px-2 py-0.5">{bankData.total}</span>
          </div>
          <div className="flex gap-2">
            <Button onClick={() => { resetAIGenerateState(); setShowAIModal(true); }} variant="outline" className="h-8 px-3 rounded-xl text-[11px] font-bold border-indigo-200 bg-indigo-50/50 text-indigo-600 gap-1.5 hover:bg-indigo-100/50 transition-colors">
                <Sparkles className="w-3 h-3" /> {t('questionBank.aiGenerate')}
            </Button>
            <Button onClick={() => fileInputRef.current?.click()} variant="outline" className="h-8 px-3 rounded-xl text-[11px] font-bold border-black/10 gap-1.5">
                <Upload className="w-3 h-3" /> {t('questionBank.importCsv')}
            </Button>
            <input type="file" ref={fileInputRef} onChange={handleImportCSV} className="hidden" accept=".csv" />
            <Button onClick={handleExport} variant="outline" className="h-8 px-3 rounded-xl text-[11px] font-bold border-black/10 gap-1.5">
                <FileUp className="w-3 h-3" /> {t('questionBank.exportAiStructured')}
            </Button>
          </div>
        </div>
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3 h-3 opacity-30" />
            <Input value={bankSearch} onChange={e => setBankSearch(e.target.value)} placeholder={t('questionBank.searchPlaceholder')} className="pl-8 h-8 bg-white border-none rounded-xl font-bold text-xs shadow-sm" />
          </div>
          <Select value={bankKP} onValueChange={setBankKP}>
            <SelectTrigger className="h-8 w-32 rounded-xl bg-white border-none font-bold text-[11px] shadow-sm"><SelectValue placeholder={t('questionBank.allKp')} /></SelectTrigger>
            <SelectContent className="rounded-xl"><SelectItem value="0" className="text-xs">{t('questionBank.allKp')}</SelectItem>{kpList.map(kp => <SelectItem key={kp.id} value={kp.id.toString()} className="text-xs">{kp.name}</SelectItem>)}</SelectContent>
          </Select>
          <Select value={bankType} onValueChange={setBankType}>
            <SelectTrigger className="h-8 w-24 rounded-xl bg-white border-none font-bold text-[11px] shadow-sm"><SelectValue /></SelectTrigger>
            <SelectContent className="rounded-xl"><SelectItem value="all" className="text-xs">{t('questionBank.allTypes')}</SelectItem><SelectItem value="objective" className="text-xs">{t('questionBank.objective')}</SelectItem><SelectItem value="subjective" className="text-xs">{t('questionBank.subjective')}</SelectItem></SelectContent>
          </Select>
          <Button onClick={() => fetchBank(bankPage)} variant="ghost" size="icon" className="h-8 w-8 rounded-xl shrink-0">
            <RefreshCcw className={cn('w-3.5 h-3.5 opacity-40', loading && 'animate-spin')} />
          </Button>
        </div>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-3 space-y-1.5">
          {loading && <div className="py-10 text-center text-xs font-bold opacity-20">{t('questionBank.loading')}</div>}
          {!loading && bankData.results.length === 0 && <div className="py-10 text-center text-xs font-bold opacity-20">{t('questionBank.noQuestions')}</div>}
          {bankData.results.map(q => (
            <div key={q.id} className="rounded-2xl bg-unimind-bg-secondary/70 hover:bg-unimind-bg-secondary transition-colors border border-transparent hover:border-black/[0.04]">
              <div className="p-3 flex items-start gap-3 cursor-pointer" onClick={() => setExpanded(expanded === q.id ? null : q.id)}>
                <div className="flex flex-col gap-1 shrink-0 pt-0.5">
                  <Badge className={cn('text-[11px] py-0 h-4 px-1.5 rounded-md border-none font-bold', q.q_type === 'objective' ? 'bg-blue-100 text-blue-700' : 'bg-purple-100 text-purple-700')}>{q.q_type === 'objective' ? t('questionBank.objectiveBadge') : t('questionBank.subjectiveBadge')}</Badge>
                  {q.subjective_type && <Badge className="text-[11px] py-0 h-3.5 px-1 rounded-md border-none bg-black/5 text-black/40 font-bold">{getTypeLabel(q.subjective_type)}</Badge>}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-[11px] font-bold text-foreground leading-relaxed line-clamp-2">{q.text}</p>
                  <p className="text-[11px] font-bold text-black/30 mt-1">{q.knowledge_point_name} · {q.difficulty_level_display} (ELO {q.difficulty})</p>
                </div>
                <div className="flex gap-1 shrink-0">
                  <Button onClick={e => { e.stopPropagation(); onEdit(q); }} variant="ghost" size="icon" className="h-7 w-7 rounded-lg hover:bg-white text-blue-600 shadow-sm"><Edit3 className="w-3 h-3" /></Button>
                  <Button onClick={e => { e.stopPropagation(); onDelete(q.id); fetchBank(bankPage); }} variant="ghost" size="icon" className="h-7 w-7 rounded-lg hover:bg-white text-red-500 shadow-sm"><Trash2 className="w-3 h-3" /></Button>
                  <div className="h-7 w-7 flex items-center justify-center opacity-30">{expanded === q.id ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}</div>
                </div>
              </div>
              {expanded === q.id && (
                <div className="px-4 pb-4 space-y-2 border-t border-black/[0.04] mt-0 pt-3">
                  {q.correct_answer && <div><p className="text-[11px] font-bold opacity-30 uppercase tracking-widest mb-1">{t('questionBank.answer')}</p><p className="text-[11px] font-medium text-black/70 whitespace-pre-wrap bg-emerald-50/50 rounded-xl p-3">{q.correct_answer}</p></div>}
                  {q.grading_points && <div><p className="text-[11px] font-bold opacity-30 uppercase tracking-widest mb-1">{t('questionBank.gradingPoints')}</p><p className="text-[11px] font-medium text-black/70 bg-blue-50/50 rounded-xl p-3">{q.grading_points}</p></div>}
                </div>
              )}
            </div>
          ))}
        </div>
      </ScrollArea>

      {bankData.total_pages > 1 && (
        <div className="p-3 border-t border-black/[0.03] flex items-center justify-between shrink-0">
          <Button onClick={() => { const p = Math.max(1, bankPage - 1); setBankPage(p); fetchBank(p); }} disabled={bankPage === 1} variant="ghost" className="h-8 px-4 rounded-xl text-xs font-bold">{t('questionBank.prevPage')}</Button>
          <span className="text-[11px] font-bold opacity-40">{bankPage} / {bankData.total_pages}</span>
          <Button onClick={() => { const p = Math.min(bankData.total_pages, bankPage + 1); setBankPage(p); fetchBank(p); }} disabled={bankPage === bankData.total_pages} variant="ghost" className="h-8 px-4 rounded-xl text-xs font-bold">{t('questionBank.nextPage')}</Button>
        </div>
      )}

      {/* AI Generate Selection Modal */}
      <Dialog
        open={showAIModal}
        onOpenChange={open => {
          if (open) resetAIGenerateState();
          setShowAIModal(open);
        }}
      >
          <DialogContent className="rounded-[2.5rem] border-none shadow-2xl p-8 max-w-xl bg-white text-left overflow-hidden max-h-[90vh] flex flex-col">
              <DialogHeader>
                  <DialogTitle className="text-xl font-bold flex items-center gap-2">
                      <Sparkles className="w-5 h-5 text-indigo-500" /> {t('questionBank.aiWorkshopTitle')}
                  </DialogTitle>
                  <DialogDescription className="text-xs font-medium text-black/40">{t('questionBank.aiWorkshopDesc')}</DialogDescription>
              </DialogHeader>
              <div className="flex-1 overflow-y-auto mt-6 space-y-6 pr-2 scrollbar-thin">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <div>
                      <p className="text-[11px] font-bold text-black/30 uppercase tracking-widest mb-2">{t('questionBank.genCountPerKp')}</p>
                      <Input
                        type="number"
                        min={1}
                        max={10}
                        value={genCount}
                        onChange={e => setGenCount(parseInt(e.target.value) || 1)}
                        className="h-10 rounded-xl border-black/5 bg-slate-50 font-bold text-xs shadow-inner"
                      />
                    </div>
                    <div>
                      <p className="text-[11px] font-bold text-black/30 uppercase tracking-widest mb-2">{t('questionBank.targetDifficulty')}</p>
                      <Select value={selectedDifficulty} onValueChange={setSelectedDifficulty}>
                        <SelectTrigger className="h-10 rounded-xl border-black/5 bg-slate-50 font-bold text-xs shadow-inner">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="rounded-xl">
                          {AI_DIFFICULTY_OPTIONS.map(item => (
                            <SelectItem key={item.value} value={item.value} className="text-xs">
                              {getDifficultyLabel(item.value)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <p className="text-[11px] font-bold text-black/30 uppercase tracking-widest mb-2">{t('questionBank.typeRatioPreset')}</p>
                      <Select value={selectedTypeRatioPreset} onValueChange={setSelectedTypeRatioPreset}>
                        <SelectTrigger className="h-10 rounded-xl border-black/5 bg-slate-50 font-bold text-xs shadow-inner">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="rounded-xl">
                          {AI_TYPE_RATIO_PRESET_OPTIONS.map(item => (
                            <SelectItem key={item.value} value={item.value} className="text-xs">
                              {getPresetLabel(item.value)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="md:col-span-3">
                        <p className="text-[11px] font-bold text-black/30 uppercase tracking-widest mb-3">{t('questionBank.targetTypes')}</p>
                        <div className="grid grid-cols-5 gap-2">
                            {AI_TYPE_OPTIONS.map(t_opt => (
                                <div
                                    key={t_opt.typeKey}
                                    onClick={() => toggleType(t_opt.typeKey)}
                                    className={cn(
                                        "flex flex-col items-center justify-center p-3 rounded-2xl border transition-all cursor-pointer gap-2 select-none h-20",
                                        selectedTypes.includes(t_opt.typeKey)
                                            ? "bg-indigo-600 border-indigo-600 text-white shadow-lg shadow-indigo-100 scale-[1.02]"
                                            : "bg-slate-50 border-black/[0.03] text-slate-500 hover:border-indigo-200 hover:bg-white"
                                    )}
                                >
                                    <span className="text-xl">{t_opt.icon}</span>
                                    <span className="text-[10px] font-black uppercase text-center">{getTypeLabel(t_opt.typeKey)}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                  </div>
                  <div className="space-y-2">
                      <p className="text-[11px] font-bold text-black/30 uppercase tracking-widest">{t('questionBank.selectKpTitle', { count: selectedKPs.length })}</p>
                      <div className="grid grid-cols-2 gap-1.5 p-4 bg-slate-50/50 rounded-[2rem] border border-black/5 min-h-[300px]">
                          {leafKPs.map(kp => (
                              <div key={kp.id} onClick={() => toggleKP(kp.id)} className={cn("p-2 px-3 rounded-xl border cursor-pointer transition-all flex items-center gap-2", selectedKPs.includes(kp.id) ? "bg-indigo-600 border-indigo-600 text-white shadow-md scale-[1.02]" : "bg-white border-black/5 text-black/70 hover:border-indigo-200")}>
                                  <div className={cn("w-3.5 h-3.5 rounded-full border flex items-center justify-center shrink-0", selectedKPs.includes(kp.id) ? "bg-white border-white" : "border-black/10")}>{selectedKPs.includes(kp.id) && <Check className="w-2.5 h-2.5 text-indigo-600" />}</div>
                                  <span className="text-[11px] font-bold truncate leading-none">{kp.name}</span>
                              </div>
                          ))}
                      </div>
                  </div>
              </div>

              <DialogFooter className="mt-6 border-t border-black/5 pt-6">
                  <Button variant="ghost" onClick={() => setShowAIModal(false)} className="rounded-xl h-11 font-bold text-xs px-6">{t('questionBank.cancel')}</Button>
                  <Button
                    onClick={handleAIGenerate}
                    disabled={isGenerating || selectedKPs.length === 0 || selectedTypes.length === 0}
                    className="rounded-xl h-11 bg-indigo-600 text-white font-bold text-xs px-10 shadow-lg shadow-indigo-200 hover:bg-indigo-700 transition-all active:scale-95"
                  >
                      {isGenerating ? <Loader2 className="w-4 h-4 animate-spin" /> : t('questionBank.startGenerate')}
                  </Button>
              </DialogFooter>
          </DialogContent>
      </Dialog>

      {/* Preview & Edit Modal */}
      <Dialog open={showPreview} onOpenChange={setShowPreview}>
          <DialogContent className="rounded-[3rem] border-none shadow-2xl p-0 max-w-4xl bg-unimind-bg-secondary text-left overflow-hidden h-[90vh] flex flex-col">
              <div className="p-8 pb-4 bg-white/80 backdrop-blur-xl border-b border-black/[0.03] z-10 sticky top-0">
                  <DialogHeader>
                      <DialogTitle className="text-2xl font-black tracking-tight text-foreground">{t('questionBank.previewTitle')}</DialogTitle>
                      <DialogDescription className="text-sm font-medium text-black/30">{t('questionBank.previewDesc')}</DialogDescription>
                  </DialogHeader>
                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    <Badge className="bg-indigo-50 text-indigo-600 border-none text-[10px] font-black rounded-lg h-6 px-3">
                      {t('questionBank.targetDifficultyLabel')}{getDifficultyLabel(selectedDifficulty)}
                    </Badge>
                    <Badge className="bg-slate-100 text-slate-600 border-none text-[10px] font-black rounded-lg h-6 px-3">
                      {t('questionBank.totalQuestionsLabel')}{previewQuestions.length}
                    </Badge>
                    <Badge className={cn("border-none text-[10px] font-black rounded-lg h-6 px-3", invalidDifficultyCount > 0 ? "bg-rose-100 text-rose-600" : "bg-emerald-100 text-emerald-600")}>
                      {t('questionBank.difficultyCheckFailed')}{invalidDifficultyCount}
                    </Badge>
                    {invalidDifficultyCount > 0 && (
                      <Button
                        variant="outline"
                        onClick={() => setPreviewQuestions(prev => prev.filter(q => q.difficulty_check_passed !== false))}
                        className="h-6 rounded-lg text-[10px] font-bold px-3 border-rose-200 text-rose-600 hover:bg-rose-50"
                      >
                        {t('questionBank.removeFailed')}
                      </Button>
                    )}
                  </div>
              </div>

              <ScrollArea className="flex-1 p-8">
                  <div className="space-y-10 pb-10">
                      {previewQuestions.map((q, idx) => (
                          <div key={idx} className="bg-white rounded-[2.5rem] shadow-sm border border-black/[0.03] overflow-hidden transition-all hover:shadow hover:scale-[1.01] group relative">
                              <div className="p-8 space-y-6">
                                  <div className="flex justify-between items-start gap-4">
                                      <div className="flex-1">
                                          <div className="flex items-center gap-2 mb-4">
                                              <Badge className="bg-indigo-600 text-white text-[10px] font-black rounded-lg h-5 px-2 uppercase border-none shadow-sm">{q.related_knowledge_id}</Badge>
                                              <span className="text-xs font-bold text-black/40">{q.kp_name}</span>
                                              <Badge className="bg-amber-100 text-amber-700 text-[10px] font-black rounded-lg h-5 px-2 uppercase border-none">{getQuestionTypeLabel(q)}</Badge>
                                              <Badge className="bg-slate-100 text-slate-500 text-[10px] font-black rounded-lg h-5 px-2 uppercase border-none">{getDifficultyLabel(q.difficulty_level)}</Badge>
                                              {q.difficulty_estimated_level && (
                                                <Badge className="bg-cyan-100 text-cyan-700 text-[10px] font-black rounded-lg h-5 px-2 uppercase border-none">
                                                  {t('questionBank.estimatedLabel')}{getDifficultyLabel(q.difficulty_estimated_level)}
                                                </Badge>
                                              )}
                                              <Badge className={cn("text-[10px] font-black rounded-lg h-5 px-2 uppercase border-none", q.difficulty_check_passed === false ? "bg-rose-100 text-rose-600" : "bg-emerald-100 text-emerald-600")}>
                                                {q.difficulty_check_passed === false ? t('questionBank.difficultyDeviation') : t('questionBank.difficultyPassed')}
                                              </Badge>
                                          </div>
                                          <textarea
                                              value={q.question}
                                              onChange={e => updatePreviewQuestion(idx, 'question', e.target.value)}
                                              className="w-full bg-slate-50 border-none rounded-2xl p-5 text-[14px] font-bold text-foreground leading-relaxed resize-none focus:ring-1 focus:ring-indigo-100 min-h-[100px]"
                                              placeholder={t('questionBank.enterQuestionStem')}
                                          />
                                          <p className="text-[10px] text-muted-foreground mt-1 ml-1">支持 LaTeX 公式：<code className="text-[10px] bg-muted/30 px-1 rounded">$...$</code> 行内、<code className="text-[10px] bg-muted/30 px-1 rounded">$$...$$</code> 块级</p>
                                      </div>
                                      <Button onClick={() => setPreviewQuestions(prev => prev.filter((_, i) => i !== idx))} variant="ghost" size="icon" className="h-10 w-10 rounded-full text-red-400 hover:text-red-500 hover:bg-red-50 transition-all opacity-100"><X className="w-5 h-5" /></Button>
                                  </div>

                                  {q.q_type === 'objective' ? (
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                        {['A', 'B', 'C', 'D'].map(opt => (
                                            <div key={opt} className={cn("flex items-start gap-3 p-4 rounded-2xl border transition-all", q.answer === opt ? "bg-indigo-50 border-indigo-200 ring-1 ring-indigo-100" : "bg-slate-50/50 border-black/[0.02]")}>
                                                <div onClick={() => updatePreviewQuestion(idx, 'answer', opt)} className={cn("w-8 h-8 rounded-full border flex items-center justify-center font-black text-xs cursor-pointer shrink-0 shadow-sm transition-all mt-0.5", q.answer === opt ? "bg-indigo-600 border-indigo-600 text-white" : "bg-white border-black/10 text-black/30")}>{opt}</div>
                                                <textarea
                                                  data-ai-option-textarea="true"
                                                  value={q.options[opt]}
                                                  rows={1}
                                                  onInput={e => autoResizeTextarea(e.currentTarget)}
                                                  onChange={e => updatePreviewQuestion(idx, 'option', { key: opt, val: e.target.value })}
                                                  className="flex-1 bg-transparent border-none p-0 text-xs font-bold text-foreground leading-relaxed focus:ring-0 placeholder:text-black/20 resize-none min-h-0 overflow-hidden whitespace-pre-wrap break-words"
                                                  placeholder={t('questionBank.optionContent')}
                                                />
                                            </div>
                                        ))}
                                    </div>
                                  ) : (
                                      <div className="space-y-3">
                                          <p className="text-[11px] font-bold text-black/20 uppercase tracking-widest px-1">{t('questionBank.referenceAnswer')}</p>
                                          <textarea value={q.answer} onChange={e => updatePreviewQuestion(idx, 'answer', e.target.value)} className="w-full bg-emerald-50/30 border border-emerald-100/50 rounded-2xl p-5 text-xs font-bold text-emerald-900 leading-relaxed min-h-[100px] focus:ring-1 focus:ring-emerald-100 whitespace-pre-wrap break-words" placeholder={t('questionBank.enterReferenceAnswer')} />
                                      </div>
                                  )}

                              </div>
                          </div>
                      ))}
                  </div>
              </ScrollArea>

              <div className="p-8 bg-white/90 backdrop-blur-xl border-t border-black/[0.03] flex items-center justify-between z-10 sticky bottom-0">
                  <div className="flex items-center gap-4">
                      <div className="h-10 w-10 rounded-xl bg-indigo-50 flex items-center justify-center text-indigo-600"><Check className="w-5 h-5" /></div>
                      <div>
                          <p className="text-sm font-black text-foreground">{t('questionBank.readyForReview')}</p>
                          <p className="text-[11px] font-bold text-black/30">{t('questionBank.questionsPending', { count: previewQuestions.length })}</p>
                      </div>
                  </div>
                  <div className="flex gap-4">
                    <Button variant="ghost" onClick={() => setShowPreview(false)} className="rounded-xl h-12 font-bold text-xs px-8 hover:bg-slate-50">{t('questionBank.abandon')}</Button>
                    <Button onClick={handleConfirmSave} disabled={isSaving || previewQuestions.length === 0} className="rounded-xl h-12 bg-indigo-600 text-white font-bold text-xs px-12 shadow hover:bg-indigo-700 transition-all active:scale-95">
                        {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : t('questionBank.confirmImport')}
                    </Button>
                  </div>
              </div>
          </DialogContent>
      </Dialog>
    </Card>
  );
};
