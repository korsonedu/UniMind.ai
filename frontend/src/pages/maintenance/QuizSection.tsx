import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Target, Plus } from '@phosphor-icons/react';
import { QuestionBankPanel } from './QuestionBankPanel';
import api from '@/lib/api';
import { toast } from 'sonner';
import { useConfirm } from '@/components/useConfirm';

export const QuizSection: React.FC = () => {
  const { t } = useTranslation('maintenance');
  const { confirm, Dialog: ConfirmDialog } = useConfirm();
  const [kpList, setKpList] = useState<any[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [editingItem, setEditingItem] = useState<any | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [form, setForm] = useState({
    text: '', q_type: 'objective', subjective_type: 'noun', grading_points: '',
    knowledge_point: '0', options: ['', '', '', ''], answer: '', difficulty_level: 'normal',
  });

  const fetchKPList = useCallback(async () => {
    try {
      const res = await api.get('/quizzes/knowledge-points/');
      setKpList(res.data);
    } catch (e) { console.debug('[QuizSection] fetch failed:', e); }
  }, []);

  useEffect(() => { fetchKPList(); }, [fetchKPList]);

  const handleCreate = async () => {
    if (!form.text) return toast.error(t('quiz.questionMissing'));
    try {
      await api.post('/quizzes/questions/', {
        text: form.text, q_type: form.q_type, subjective_type: form.subjective_type,
        grading_points: form.grading_points,
        knowledge_point: form.knowledge_point === '0' ? null : form.knowledge_point,
        options: form.q_type === 'objective' ? form.options : null,
        correct_answer: form.answer, difficulty_level: form.difficulty_level,
      });
      toast.success(t('quiz.questionStored'));
      setShowCreate(false);
      setRefreshKey(k => k + 1);
    } catch { toast.error(t('quiz.storeFailed')); }
  };

  const handleUpdate = async () => {
    if (!editingItem) return;
    try {
      await api.patch(`/quizzes/questions/${editingItem.id}/`, editingItem);
      toast.success('已更新');
      setEditingItem(null);
      setRefreshKey(k => k + 1);
    } catch { toast.error('更新失败'); }
  };

  const handleDelete = async (id: number) => {
    if (!(await confirm('确定删除此题目？'))) return;
    try {
      await api.delete(`/quizzes/questions/${id}/`);
      toast.success('已删除');
      setRefreshKey(k => k + 1);
    } catch { toast.error('删除失败'); }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Target className="h-5 w-5 text-[#6E6E73]" />
          <h3 className="text-lg font-semibold tracking-tight">{t('tabs.questionBank')}</h3>
        </div>
        <Button onClick={() => setShowCreate(true)} className="h-10 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm px-5 shadow-[0_1px_3px_rgba(0,113,227,0.3)] transition-[background-color,box-shadow] gap-2">
          <Plus className="w-4 h-4" />
          {t('quiz.entryTitle')}
        </Button>
      </div>

      <QuestionBankPanel
        kpList={kpList}
        onEdit={q => setEditingItem({ ...q })}
        onDelete={handleDelete}
        refreshTrigger={refreshKey}
      />

      {/* Create Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="sm:max-w-[800px] max-h-[90vh] overflow-y-auto rounded-3xl p-8 border-none shadow-[0_0_0_1px_rgba(0,0,0,0.04),0_4px_8px_rgba(0,0,0,0.04),0_16px_32px_rgba(0,0,0,0.08),0_32px_64px_rgba(0,0,0,0.04)] bg-white text-left">
          <DialogHeader>
            <DialogTitle className="text-lg font-semibold flex items-center gap-3">
              <Target className="h-5 w-5 text-[#6E6E73]" /> {t('quiz.entryTitle')}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-5 pt-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Select value={form.q_type} onValueChange={v => setForm({ ...form, q_type: v })}>
                <SelectTrigger className="h-10 rounded-xl bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 font-medium text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="objective">{t('quiz.objective')}</SelectItem>
                  <SelectItem value="subjective">{t('quiz.subjective')}</SelectItem>
                </SelectContent>
              </Select>
              {form.q_type === 'subjective' && (
                <Select value={form.subjective_type} onValueChange={v => setForm({ ...form, subjective_type: v })}>
                  <SelectTrigger className="h-10 rounded-xl bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 font-medium text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="noun">{t('quiz.noun')}</SelectItem>
                    <SelectItem value="short">{t('quiz.shortAnswer')}</SelectItem>
                    <SelectItem value="essay">{t('quiz.essay')}</SelectItem>
                  </SelectContent>
                </Select>
              )}
              <Select value={form.knowledge_point} onValueChange={v => setForm({ ...form, knowledge_point: v })}>
                <SelectTrigger className="h-10 rounded-xl bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 font-medium text-xs px-4"><SelectValue placeholder={t('quiz.knowledgePoint')} /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="0">{t('quiz.noMount')}</SelectItem>
                  {kpList.map(kp => <SelectItem key={kp.id} value={kp.id.toString()}>{kp.name}</SelectItem>)}
                </SelectContent>
              </Select>
              <Select value={form.difficulty_level} onValueChange={v => setForm({ ...form, difficulty_level: v })}>
                <SelectTrigger className="h-10 rounded-xl bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 font-medium text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="entry">{t('quiz.entry')}</SelectItem>
                  <SelectItem value="easy">{t('quiz.easy')}</SelectItem>
                  <SelectItem value="normal">{t('quiz.normal')}</SelectItem>
                  <SelectItem value="hard">{t('quiz.hard')}</SelectItem>
                  <SelectItem value="extreme">{t('quiz.extreme')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">题目内容</Label>
              <textarea
                value={form.text}
                onChange={e => setForm({ ...form, text: e.target.value })}
                className="w-full bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 rounded-2xl p-5 min-h-[160px] font-medium text-sm outline-none"
                placeholder={t('quiz.textPlaceholder')}
              />
            </div>
            <p className="text-[11px] text-[#8E8E93] -mt-4 ml-1">支持 LaTeX 公式：<code className="text-[11px] bg-black/[0.04] px-1.5 py-0.5 rounded-md">$...$</code> 行内、<code className="text-[11px] bg-black/[0.04] px-1.5 py-0.5 rounded-md">$$...$$</code> 块级</p>
            {form.q_type === 'objective' ? (
              <div className="space-y-4">
                <Label className="text-xs font-medium text-[#6E6E73] ml-1">{t('quiz.options')}</Label>
                <div className="grid grid-cols-2 gap-3">
                  {form.options.map((opt, i) => (
                    <div key={i} className="flex gap-2">
                      <div className="h-10 w-10 rounded-xl bg-[#1D1D1F] text-white flex items-center justify-center font-semibold text-xs shrink-0">{String.fromCharCode(65 + i)}</div>
                      <Input value={opt} onChange={e => { const no = [...form.options]; no[i] = e.target.value; setForm({ ...form, options: no }); }} className="h-10 rounded-xl bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 font-medium text-xs px-4" />
                    </div>
                  ))}
                </div>
                <Input value={form.answer} onChange={e => setForm({ ...form, answer: e.target.value })} placeholder={t('quiz.correctAnswerLetter')} className="h-11 rounded-xl bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 font-medium text-xs px-5" />
              </div>
            ) : (
              <div className="space-y-4">
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium text-[#6E6E73] ml-1">{t('quiz.gradingPointsPlaceholder')}</Label>
                  <textarea value={form.grading_points} onChange={e => setForm({ ...form, grading_points: e.target.value })} className="w-full bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 rounded-xl p-4 min-h-[120px] font-medium text-sm outline-none" placeholder={t('quiz.gradingPointsPlaceholder')} />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium text-[#6E6E73] ml-1">{t('quiz.referenceAnswerPlaceholder')}</Label>
                  <textarea value={form.answer} onChange={e => setForm({ ...form, answer: e.target.value })} className="w-full bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 rounded-xl p-4 min-h-[120px] font-medium text-sm outline-none" placeholder={t('quiz.referenceAnswerPlaceholder')} />
                </div>
              </div>
            )}
            <Button onClick={handleCreate} className="w-full h-11 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm shadow-[0_1px_3px_rgba(0,113,227,0.3)] transition-[background-color,box-shadow]">
              {t('quiz.entryBank')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={!!editingItem} onOpenChange={open => !open && setEditingItem(null)}>
        <DialogContent className="sm:max-w-[800px] max-h-[90vh] overflow-y-auto rounded-3xl p-8 border-none shadow-[0_0_0_1px_rgba(0,0,0,0.04),0_4px_8px_rgba(0,0,0,0.04),0_16px_32px_rgba(0,0,0,0.08),0_32px_64px_rgba(0,0,0,0.04)] bg-white text-left">
          <DialogHeader>
            <DialogTitle className="text-lg font-semibold">{t('sectionList.editQuestion')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-5 pt-4">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">题目内容</Label>
              <textarea value={editingItem?.text || ''} onChange={e => setEditingItem({ ...editingItem, text: e.target.value })} className="w-full bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 rounded-2xl p-5 min-h-[160px] font-medium text-sm outline-none" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-[#6E6E73] ml-1">{t('quiz.knowledgePoint')}</Label>
                <Select value={editingItem?.knowledge_point || '0'} onValueChange={v => setEditingItem({ ...editingItem, knowledge_point: v })}>
                  <SelectTrigger className="h-10 rounded-xl bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 font-medium text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="0">{t('quiz.noMount')}</SelectItem>
                    {kpList.map(kp => <SelectItem key={kp.id} value={kp.id.toString()}>{kp.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-[#6E6E73] ml-1">难度</Label>
                <Select value={editingItem?.difficulty_level || 'normal'} onValueChange={v => setEditingItem({ ...editingItem, difficulty_level: v })}>
                  <SelectTrigger className="h-10 rounded-xl bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 font-medium text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="entry">{t('quiz.entry')}</SelectItem>
                    <SelectItem value="easy">{t('quiz.easy')}</SelectItem>
                    <SelectItem value="normal">{t('quiz.normal')}</SelectItem>
                    <SelectItem value="hard">{t('quiz.hard')}</SelectItem>
                    <SelectItem value="extreme">{t('quiz.extreme')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-[#6E6E73] ml-1">{t('editDialog.gradingPoints')}</Label>
                <textarea value={editingItem?.grading_points || ''} onChange={e => setEditingItem({ ...editingItem, grading_points: e.target.value })} className="w-full bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 rounded-xl p-4 min-h-[120px] font-medium text-sm outline-none" placeholder={t('editDialog.gradingPoints')} />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-[#6E6E73] ml-1">{t('editDialog.answer')}</Label>
                <textarea value={editingItem?.correct_answer || ''} onChange={e => setEditingItem({ ...editingItem, correct_answer: e.target.value })} className="w-full bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 rounded-xl p-4 min-h-[120px] font-medium text-sm outline-none" placeholder={t('editDialog.answer')} />
              </div>
            </div>
            <Button onClick={handleUpdate} className="w-full h-11 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm shadow-[0_1px_3px_rgba(0,113,227,0.3)] transition-[background-color,box-shadow]">
              {t('editDialog.updateAndSync')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
      {ConfirmDialog}
    </div>
  );
};
