import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { FileText, PencilSimple, Trash, Plus, Eye } from '@phosphor-icons/react';
import { MarkdownEditor } from '@/components/MarkdownEditor';
import { TagInput } from './MaintenanceComponents';
import { QuickCreateKPDialog } from './QuickCreateKPDialog';
import { Pagination } from '@/components/Pagination';
import api from '@/lib/api';
import { toast } from 'sonner';
import { useConfirm } from '@/components/useConfirm';

export const ArticleSection: React.FC = () => {
  const { t } = useTranslation('maintenance');
  const { confirm, Dialog: ConfirmDialog } = useConfirm();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [kpList, setKpList] = useState<any[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [editingItem, setEditingItem] = useState<any | null>(null);
  const [showNewKP, setShowNewKP] = useState(false);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [form, setForm] = useState({ title: '', content: '', author_display_name: '', tags: [] as string[], knowledge_point: '0' });

  const fetchItems = useCallback(async (p = 1) => {
    try {
      const [a, k] = await Promise.all([
        api.get('/articles/', { params: { page: p } }),
        api.get('/quizzes/knowledge-points/'),
      ]);
      setItems(a.data.articles || []);
      setTotal(a.data.total ?? (a.data.articles || []).length);
      setTotalPages(a.data.total_pages ?? 1);
      setKpList(k.data);
    } catch (e) { console.debug('[ArticleSection] fetch failed:', e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchItems(page); }, [fetchItems, page]);

  const resetForm = () => setForm({ title: '', content: '', author_display_name: '', tags: [], knowledge_point: '0' });

  const handleCreate = async () => {
    if (!form.title) return toast.error('标题必填');
    try {
      await api.post('/articles/', {
        ...form,
        knowledge_point: form.knowledge_point === '0' ? null : form.knowledge_point,
      });
      toast.success(t('article.articlePublished'));
      resetForm();
      setShowCreate(false);
      fetchItems();
    } catch { toast.error(t('article.failed')); }
  };

  const handleUpdate = async () => {
    if (!editingItem) return;
    try {
      await api.patch(`/articles/${editingItem.id}/`, editingItem);
      toast.success('已更新');
      setEditingItem(null);
      fetchItems();
    } catch { toast.error('更新失败'); }
  };

  const handleDelete = async (id: number, title: string) => {
    if (!(await confirm(`删除文章「${title}」？此操作不可撤销。`))) return;
    try {
      await api.delete(`/articles/${id}/`);
      toast.success('已删除');
      fetchItems();
    } catch { toast.error('删除失败'); }
  };

  const onKPCreated = (kpId: string) => {
    setForm(prev => ({ ...prev, knowledge_point: kpId }));
    if (editingItem) setEditingItem({ ...editingItem, knowledge_point: kpId });
  };

  if (loading) return null;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <a href="/articles" className="p-1 -ml-1 rounded-lg hover:bg-[#F5F5F7] transition-colors text-[#6E6E73] hover:text-[#1D1D1F]" title="返回文章列表">
            <svg width="16" height="16" viewBox="0 0 256 256" fill="currentColor"><path d="M224 128a8 8 0 0 1-8 8H59.31l58.35 58.34a8 8 0 0 1-11.32 11.32l-72-72a8 8 0 0 1 0-11.32l72-72a8 8 0 0 1 11.32 11.32L59.31 120H216a8 8 0 0 1 8 8Z"/></svg>
          </a>
          <FileText className="h-5 w-5 text-[#6E6E73]" />
          <h3 className="text-lg font-semibold tracking-tight">文章管理</h3>
          <Badge variant="secondary" className="text-[11px] rounded-full bg-[#F5F5F7] text-[#6E6E73] hover:bg-[#F5F5F7]">{total}</Badge>
        </div>
        <Button onClick={() => { resetForm(); setShowCreate(true); }} className="h-10 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm px-5 shadow-[0_1px_3px_rgba(0,113,227,0.3)] transition-[background-color,box-shadow] gap-2">
          <Plus className="w-4 h-4" />
          {t('sectionList.publishArticleBtn')}
        </Button>
      </div>

      {items.length === 0 ? (
        <Card className="p-16 bg-white rounded-2xl border border-black/[0.04] shadow-[0_1px_2px_rgba(0,0,0,0.02),0_4px_16px_rgba(0,0,0,0.03)] text-center">
          <FileText className="h-10 w-10 text-[#AEAEB2] mx-auto mb-4 opacity-30" />
          <p className="text-sm text-[#8E8E93] font-medium">{t('sectionList.noArticles')}</p>
          <p className="text-xs text-[#AEAEB2] mt-1">{t('sectionList.noArticlesHint')}</p>
        </Card>
      ) : (
        <>
          <Card className="bg-white rounded-2xl border border-black/[0.04] shadow-[0_1px_2px_rgba(0,0,0,0.02),0_4px_16px_rgba(0,0,0,0.03)] overflow-hidden">
            <ScrollArea className="h-[560px]">
              <div className="divide-y divide-black/[0.04]">
                {items.map((item: any) => (
                  <div key={item.id} className="p-4 hover:bg-[#F5F5F7]/50 transition-colors group">
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-semibold">{item.title}</p>
                        <p className="text-xs text-[#8E8E93] mt-0.5 line-clamp-2">{item.content?.replace(/[#*`>\[\]!\-]/g, '').slice(0, 150)}</p>
                        <div className="flex items-center gap-2 mt-2 flex-wrap">
                          {item.author_display_name && (
                            <span className="text-[11px] text-[#AEAEB2] font-medium">{item.author_display_name}</span>
                          )}
                          {item.knowledge_point_name && (
                            <Badge variant="secondary" className="text-[10px] rounded-lg bg-[#F5F5F7] text-[#8E8E93] font-medium hover:bg-[#F5F5F7]">{item.knowledge_point_name}</Badge>
                          )}
                          {item.tags?.map((tag: string, i: number) => (
                            <Badge key={i} className="text-[10px] bg-black text-white hover:bg-black/80 rounded-lg">{tag}</Badge>
                          ))}
                          {item.view_count !== undefined && (
                            <span className="text-[11px] text-[#AEAEB2] flex items-center gap-0.5"><Eye className="w-3 h-3" /> {item.view_count}</span>
                          )}
                        </div>
                        <p className="text-[11px] text-[#AEAEB2] mt-1.5">
                          {item.created_at ? new Date(item.created_at).toLocaleDateString() : ''}
                          {item.updated_at && item.updated_at !== item.created_at ? ` · 更新 ${new Date(item.updated_at).toLocaleDateString()}` : ''}
                        </p>
                      </div>
                      <div className="flex gap-1  shrink-0">
                        <Button onClick={() => setEditingItem({ ...item, knowledge_point: item.knowledge_point?.toString() || '0' })} variant="ghost" size="icon" className="h-8 w-8 text-[#6E6E73] hover:bg-[#F5F5F7] rounded-lg">
                          <PencilSimple className="w-3.5 h-3.5" />
                        </Button>
                        <Button onClick={() => handleDelete(item.id, item.title)} variant="ghost" size="icon" className="h-8 w-8 text-[#6E6E73] hover:bg-red-50 hover:text-red-500 rounded-lg">
                          <Trash className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </Card>
          <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
        </>
      )}

      {/* Create Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="sm:max-w-[850px] max-h-[90vh] overflow-y-auto rounded-3xl p-8 border-none shadow-[0_0_0_1px_rgba(0,0,0,0.04),0_4px_8px_rgba(0,0,0,0.04),0_16px_32px_rgba(0,0,0,0.08),0_32px_64px_rgba(0,0,0,0.04)] bg-white text-left">
          <DialogHeader>
            <DialogTitle className="text-lg font-semibold flex items-center gap-3">
              <FileText className="h-5 w-5 text-[#6E6E73]" /> {t('article.writeDeepArticle')}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-5 pt-4">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">{t('article.titlePlaceholder')}</Label>
              <Input
                value={form.title}
                onChange={e => setForm({ ...form, title: e.target.value })}
                className="bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 h-11 rounded-xl px-4 text-sm font-medium"
                placeholder={t('article.titlePlaceholder')}
              />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-[#6E6E73] ml-1">{t('article.knowledgePoint')}</Label>
                <Select value={form.knowledge_point} onValueChange={v => v === 'NEW_KP' ? setShowNewKP(true) : setForm({ ...form, knowledge_point: v })}>
                  <SelectTrigger className="h-10 rounded-xl bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 font-medium text-xs">
                    <SelectValue placeholder={t('article.knowledgePoint')} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="0">{t('quiz.noMount')}</SelectItem>
                    <SelectItem value="NEW_KP" className="text-[#0071E3] font-semibold">{t('course.newKnowledgePoint')}</SelectItem>
                    {kpList.map(kp => <SelectItem key={kp.id} value={kp.id.toString()}>{kp.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-[#6E6E73] ml-1">{t('article.authorSignature')}</Label>
                <Input
                  value={form.author_display_name}
                  onChange={e => setForm({ ...form, author_display_name: e.target.value })}
                  className="bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 h-10 rounded-xl px-4 text-xs font-medium"
                  placeholder={t('article.authorSignature')}
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-[#6E6E73] ml-1">{t('article.tags')}</Label>
                <TagInput tags={form.tags} setTags={t => setForm({ ...form, tags: t })} compact />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">{t('article.content')}</Label>
              <MarkdownEditor content={form.content} onChange={v => setForm({ ...form, content: v })} />
            </div>
            <Button onClick={handleCreate} className="w-full h-11 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm shadow-[0_1px_3px_rgba(0,113,227,0.3)] transition-[background-color,box-shadow]">
              {t('sectionList.publishArticleBtn')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={!!editingItem} onOpenChange={open => !open && setEditingItem(null)}>
        <DialogContent className="sm:max-w-[850px] max-h-[90vh] overflow-y-auto rounded-3xl p-8 border-none shadow-[0_0_0_1px_rgba(0,0,0,0.04),0_4px_8px_rgba(0,0,0,0.04),0_16px_32px_rgba(0,0,0,0.08),0_32px_64px_rgba(0,0,0,0.04)] bg-white text-left">
          <DialogHeader>
            <DialogTitle className="text-lg font-semibold">{t('editDialog.title')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-5 pt-4">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">{t('article.title')}</Label>
              <Input
                value={editingItem?.title || ''}
                onChange={e => setEditingItem({ ...editingItem, title: e.target.value })}
                className="bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 h-11 rounded-xl px-4 text-sm font-medium"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-[#6E6E73] ml-1">{t('editDialog.signature')}</Label>
                <Input
                  value={editingItem?.author_display_name || ''}
                  onChange={e => setEditingItem({ ...editingItem, author_display_name: e.target.value })}
                  className="bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 h-10 rounded-xl px-4 text-xs font-medium"
                  placeholder={t('editDialog.signature')}
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-[#6E6E73] ml-1">{t('article.knowledgePoint')}</Label>
                <Select value={editingItem?.knowledge_point || '0'} onValueChange={v => v === 'NEW_KP' ? setShowNewKP(true) : setEditingItem({ ...editingItem, knowledge_point: v })}>
                  <SelectTrigger className="h-10 rounded-xl bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 font-medium text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="0">{t('quiz.noMount')}</SelectItem>
                    <SelectItem value="NEW_KP" className="text-[#0071E3] font-semibold">{t('course.newKnowledgePoint')}</SelectItem>
                    {kpList.map(kp => <SelectItem key={kp.id} value={kp.id.toString()}>{kp.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">{t('article.tags')}</Label>
              <TagInput tags={editingItem?.tags || []} setTags={tg => setEditingItem({ ...editingItem, tags: tg })} compact />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">{t('article.content')}</Label>
              <MarkdownEditor content={editingItem?.content || ''} onChange={v => setEditingItem({ ...editingItem, content: v })} />
            </div>
            <Button onClick={handleUpdate} className="w-full h-11 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm shadow-[0_1px_3px_rgba(0,113,227,0.3)] transition-[background-color,box-shadow]">
              {t('editDialog.updateAndSync')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Quick Create KP */}
      <QuickCreateKPDialog
        open={showNewKP}
        onOpenChange={setShowNewKP}
        kpList={kpList}
        onCreated={onKPCreated}
        onRefresh={fetchItems}
      />
      {ConfirmDialog}
    </div>
  );
};
