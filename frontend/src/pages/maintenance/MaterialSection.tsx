import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Rocket, Upload, Edit3, Trash2, Plus, FileText } from 'lucide-react';
import { Pagination } from '@/components/Pagination';
import api from '@/lib/api';
import { useUploadStore } from '@/store/useUploadStore';
import { toast } from 'sonner';
import { useConfirm } from '@/components/useConfirm';

export const MaterialSection: React.FC = () => {
  const { t } = useTranslation('maintenance');
  const { confirm, Dialog: ConfirmDialog } = useConfirm();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editingItem, setEditingItem] = useState<any | null>(null);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [form, setForm] = useState({ name: '', description: '', file: null as File | null });
  const [isSubmitting, setIsSubmitting] = useState(false);

  const fetchItems = useCallback(async (p = 1) => {
    try {
      const res = await api.get('/courses/startup-materials/', { params: { page: p, page_size: 10 } });
      setItems(res.data.items || res.data);
      setTotal(res.data.total ?? (Array.isArray(res.data) ? res.data.length : 0));
      setTotalPages(res.data.total_pages ?? 1);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchItems(page); }, [fetchItems, page]);

  const resetForm = () => setForm({ name: '', description: '', file: null });

  const handleCreate = async () => {
    if (!form.name || !form.file) return toast.error(t('startupMaterial.infoIncomplete'));
    setIsSubmitting(true);

    const file = form.file;
    const name = form.name;
    const description = form.description;

    const controller = new AbortController();
    const uploadId = `${Date.now()}-${file.name}`;
    const { addTask, updateProgress, setStatus } = useUploadStore.getState();
    addTask({ id: uploadId, fileName: file.name, progress: 0, status: 'uploading', controller });

    resetForm();
    setShowCreate(false);
    setIsSubmitting(false);

    const fd = new FormData();
    fd.append('name', name);
    fd.append('description', description);
    fd.append('file', file);

    try {
      await api.post('/courses/startup-materials/', fd, {
        signal: controller.signal,
        onUploadProgress: (p: any) => {
          if (p.total) updateProgress(uploadId, Math.round((p.loaded / p.total) * 100));
        },
      });
      setStatus(uploadId, 'completed');
      toast.success(t('startupMaterial.materialUploaded'));
      fetchItems();
    } catch (e: any) {
      if (e?.name !== 'AbortError' && e?.code !== 'ERR_CANCELED') {
        toast.error(t('startupMaterial.uploadFailed'));
        setStatus(uploadId, 'failed', t('startupMaterial.uploadFailed'));
      }
    }
  };

  const handleUpdate = async () => {
    if (!editingItem) return;
    const fd = new FormData();
    Object.keys(editingItem).forEach(key => {
      if (editingItem[key] instanceof File) fd.append(key, editingItem[key]);
      else if (editingItem[key] !== null && editingItem[key] !== undefined) {
        if (key === 'file' && typeof editingItem[key] === 'string') return;
        fd.append(key, String(editingItem[key]));
      }
    });
    try {
      await api.patch(`/courses/startup-materials/${editingItem.id}/`, fd);
      toast.success('已更新');
      setEditingItem(null);
      fetchItems();
    } catch { toast.error('更新失败'); }
  };

  const handleDelete = async (id: number) => {
    if (!(await confirm('确定删除该资料？此操作不可撤销。'))) return;
    try {
      await api.delete(`/courses/startup-materials/${id}/`);
      toast.success('已删除');
      fetchItems();
    } catch { toast.error('删除失败'); }
  };

  const formatSize = (bytes?: number) => {
    if (!bytes) return '';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  if (loading) return null;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Rocket className="h-5 w-5 text-[#6E6E73]" />
          <h3 className="text-lg font-semibold tracking-tight">{t('startupMaterial.uploadMaterial')}</h3>
          <Badge variant="secondary" className="text-[11px] rounded-full bg-[#F5F5F7] text-[#6E6E73] hover:bg-[#F5F5F7]">{total}</Badge>
        </div>
        <Button onClick={() => { resetForm(); setShowCreate(true); }} className="h-10 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm px-5 shadow-[0_1px_3px_rgba(0,113,227,0.3)] transition-[background-color,box-shadow] gap-2">
          <Plus className="w-4 h-4" />
          {t('sectionList.uploadMaterial')}
        </Button>
      </div>

      {/* List */}
      {items.length === 0 ? (
        <Card className="p-16 bg-white rounded-2xl border border-black/[0.04] shadow-[0_1px_2px_rgba(0,0,0,0.02),0_4px_16px_rgba(0,0,0,0.03)] text-center">
          <FileText className="h-10 w-10 text-[#AEAEB2] mx-auto mb-4 opacity-30" />
          <p className="text-sm text-[#8E8E93] font-medium">{t('sectionList.noMaterials')}</p>
          <p className="text-xs text-[#AEAEB2] mt-1">{t('sectionList.noMaterialsHint')}</p>
        </Card>
      ) : (
        <>
          <Card className="bg-white rounded-2xl border border-black/[0.04] shadow-[0_1px_2px_rgba(0,0,0,0.02),0_4px_16px_rgba(0,0,0,0.03)] overflow-hidden">
            <ScrollArea className="h-[560px]">
              <div className="divide-y divide-black/[0.04]">
                {items.map((item: any) => (
                  <div key={item.id} className="p-4 hover:bg-[#F5F5F7]/50 transition-colors group">
                    <div className="flex items-center justify-between">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-semibold">{item.name}</p>
                        <p className="text-xs text-[#8E8E93] mt-0.5 line-clamp-1">{item.description || '—'}</p>
                        <div className="flex items-center gap-3 mt-1.5">
                          {item.file && (
                            <span className="text-[11px] text-[#AEAEB2] font-medium">
                              {item.file_name || (typeof item.file === 'string' ? item.file.split('/').pop() : '')} · {formatSize(item.file_size)}
                            </span>
                          )}
                          {item.created_at && (
                            <span className="text-[11px] text-[#AEAEB2]">{new Date(item.created_at).toLocaleDateString()}</span>
                          )}
                        </div>
                      </div>
                      <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                        <Button onClick={() => setEditingItem({ ...item })} variant="ghost" size="icon" className="h-8 w-8 text-[#6E6E73] hover:bg-[#F5F5F7] rounded-lg">
                          <Edit3 className="w-3.5 h-3.5" />
                        </Button>
                        <Button onClick={() => handleDelete(item.id)} variant="ghost" size="icon" className="h-8 w-8 text-[#6E6E73] hover:bg-red-50 hover:text-red-500 rounded-lg">
                          <Trash2 className="w-3.5 h-3.5" />
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
        <DialogContent className="sm:max-w-[600px] rounded-3xl p-8 border-none shadow-[0_0_0_1px_rgba(0,0,0,0.04),0_4px_8px_rgba(0,0,0,0.04),0_16px_32px_rgba(0,0,0,0.08),0_32px_64px_rgba(0,0,0,0.04)] bg-white text-left">
          <DialogHeader>
            <DialogTitle className="text-lg font-semibold flex items-center gap-3">
              <Rocket className="h-5 w-5 text-[#6E6E73]" /> {t('startupMaterial.uploadMaterial')}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-5 pt-4">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">名称</Label>
              <Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder={t('startupMaterial.namePlaceholder')} className="bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 h-11 rounded-xl px-4 text-sm font-medium" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">简介</Label>
              <textarea value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} className="w-full bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 rounded-2xl p-5 min-h-[80px] font-medium text-sm resize-none outline-none" placeholder={t('startupMaterial.descPlaceholder')} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">文件</Label>
              <div className="relative">
                <Button variant="outline" className="w-full h-14 rounded-xl border-dashed border-2 border-black/[0.06] hover:border-[#0071E3]/30 bg-[#F5F5F7]/50 hover:bg-[#F5F5F7] px-4 font-medium text-xs text-[#6E6E73] hover:text-[#1D1D1F] transition-[border-color,background-color,color] justify-between">
                  <span>{form.file ? form.file.name : t('startupMaterial.uploadFile')}</span>
                  <Upload className="w-4 h-4 opacity-30" />
                </Button>
                <input type="file" onChange={e => setForm({ ...form, file: e.target.files?.[0] || null })} className="absolute inset-0 opacity-0 cursor-pointer" />
              </div>
            </div>
            <Button onClick={handleCreate} disabled={isSubmitting} className="w-full h-11 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm shadow-[0_1px_3px_rgba(0,113,227,0.3)] transition-[background-color,box-shadow]">
              {t('startupMaterial.uploadMaterialBtn')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={!!editingItem} onOpenChange={open => !open && setEditingItem(null)}>
        <DialogContent className="sm:max-w-[600px] rounded-3xl p-8 border-none shadow-[0_0_0_1px_rgba(0,0,0,0.04),0_4px_8px_rgba(0,0,0,0.04),0_16px_32px_rgba(0,0,0,0.08),0_32px_64px_rgba(0,0,0,0.04)] bg-white text-left">
          <DialogHeader>
            <DialogTitle className="text-lg font-semibold">{t('sectionList.editMaterial')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-5 pt-4">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">名称</Label>
              <Input value={editingItem?.name || ''} onChange={e => setEditingItem({ ...editingItem, name: e.target.value })} className="bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 h-11 rounded-xl px-4 text-sm font-medium" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">简介</Label>
              <textarea value={editingItem?.description || ''} onChange={e => setEditingItem({ ...editingItem, description: e.target.value })} className="w-full bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 rounded-2xl p-5 min-h-[80px] font-medium text-sm resize-none outline-none" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">{t('sectionList.replaceFile')}</Label>
              <Input type="file" onChange={e => setEditingItem({ ...editingItem, file: e.target.files?.[0] })} className="rounded-xl h-10 bg-[#F5F5F7] text-xs" />
            </div>
            <Button onClick={handleUpdate} className="w-full h-11 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm shadow-[0_1px_3px_rgba(0,113,227,0.3)] transition-[background-color,box-shadow]">
              {t('sectionList.update')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
      {ConfirmDialog}
    </div>
  );
};
