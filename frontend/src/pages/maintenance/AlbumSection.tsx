import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Layers, Upload, Edit3, Trash2, Plus, Image as ImageIcon, ChevronDown, ChevronRight } from 'lucide-react';
import api from '@/lib/api';
import { toast } from 'sonner';

export const AlbumSection: React.FC = () => {
  const { t } = useTranslation('maintenance');
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editingItem, setEditingItem] = useState<any | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [form, setForm] = useState({ name: '', description: '', cover: null as File | null });

  const fetchItems = useCallback(async () => {
    try {
      const res = await api.get('/courses/albums/');
      setItems(res.data);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchItems(); }, [fetchItems]);

  const resetForm = () => setForm({ name: '', description: '', cover: null });

  const handleCreate = async () => {
    if (!form.name) return toast.error(t('album.nameRequired'));
    const fd = new FormData();
    fd.append('name', form.name);
    fd.append('description', form.description);
    if (form.cover) fd.append('cover_image', form.cover);
    try {
      await api.post('/courses/albums/', fd);
      toast.success(t('album.albumCreated'));
      resetForm();
      setShowCreate(false);
      fetchItems();
    } catch { toast.error(t('album.failed')); }
  };

  const handleUpdate = async () => {
    if (!editingItem) return;
    const fd = new FormData();
    Object.keys(editingItem).forEach(key => {
      if (editingItem[key] instanceof File) fd.append(key, editingItem[key]);
      else if (editingItem[key] !== null && editingItem[key] !== undefined) {
        if (key === 'cover_image' && typeof editingItem[key] === 'string') return;
        fd.append(key, String(editingItem[key]));
      }
    });
    try {
      await api.patch(`/courses/albums/${editingItem.id}/`, fd);
      toast.success('已更新');
      setEditingItem(null);
      fetchItems();
    } catch { toast.error('更新失败'); }
  };

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(`删除专辑「${name}」？此操作不可撤销。`)) return;
    try {
      await api.delete(`/courses/albums/${id}/`);
      toast.success('已删除');
      fetchItems();
    } catch { toast.error('删除失败'); }
  };

  if (loading) return null;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Layers className="h-5 w-5 text-[#6E6E73]" />
          <h3 className="text-lg font-semibold tracking-tight">{t('tabs.albumManager')}</h3>
          <Badge variant="secondary" className="text-[11px] rounded-full bg-[#F5F5F7] text-[#6E6E73] hover:bg-[#F5F5F7]">{items.length}</Badge>
        </div>
        <Button onClick={() => { resetForm(); setShowCreate(true); }} className="h-10 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm px-5 shadow-[0_1px_3px_rgba(0,113,227,0.3)] transition-[background-color,box-shadow] gap-2">
          <Plus className="w-4 h-4" />
          {t('album.newAlbum')}
        </Button>
      </div>

      {/* List */}
      {items.length === 0 ? (
        <Card className="p-16 bg-white rounded-2xl border border-black/[0.04] shadow-[0_1px_2px_rgba(0,0,0,0.02),0_4px_16px_rgba(0,0,0,0.03)] text-center">
          <Layers className="h-10 w-10 text-[#AEAEB2] mx-auto mb-4 opacity-30" />
          <p className="text-sm text-[#8E8E93] font-medium">{t('sectionList.noAlbums')}</p>
          <p className="text-xs text-[#AEAEB2] mt-1">{t('sectionList.noAlbumsHint')}</p>
        </Card>
      ) : (
        <Card className="bg-white rounded-2xl border border-black/[0.04] shadow-[0_1px_2px_rgba(0,0,0,0.02),0_4px_16px_rgba(0,0,0,0.03)] overflow-hidden">
          <ScrollArea className="h-[560px]">
            <div className="divide-y divide-black/[0.04]">
              {items.map((item: any) => {
                const isExpanded = expandedId === item.id;
                return (
                  <div key={item.id}>
                    <div
                      className="p-4 hover:bg-[#F5F5F7]/50 transition-colors group cursor-pointer"
                      onClick={() => setExpandedId(isExpanded ? null : item.id)}
                    >
                      <div className="flex items-center gap-4">
                        {isExpanded ? (
                          <ChevronDown className="h-4 w-4 text-[#AEAEB2] shrink-0" />
                        ) : (
                          <ChevronRight className="h-4 w-4 text-[#AEAEB2] shrink-0" />
                        )}
                        <div className="h-12 w-12 rounded-xl bg-[#F5F5F7] flex items-center justify-center overflow-hidden shrink-0">
                          {item.cover_image ? (
                            <img src={item.cover_image} alt="" className="h-full w-full object-cover" />
                          ) : (
                            <ImageIcon className="h-5 w-5 text-[#AEAEB2]" />
                          )}
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-semibold">{item.name}</p>
                          <p className="text-xs text-[#8E8E93] mt-0.5 line-clamp-1">{item.description || '—'}</p>
                          <div className="flex items-center gap-3 mt-1.5">
                            {item.course_count !== undefined && (
                              <Badge variant="secondary" className="text-[11px] rounded-full bg-[#F5F5F7] text-[#8E8E93] font-medium hover:bg-[#F5F5F7]">{item.course_count} 门课程</Badge>
                            )}
                            {item.created_at && (
                              <span className="text-[11px] text-[#AEAEB2]">{new Date(item.created_at).toLocaleDateString()}</span>
                            )}
                          </div>
                        </div>
                        <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                          <Button onClick={(e) => { e.stopPropagation(); setEditingItem({ ...item }); }} variant="ghost" size="icon" className="h-8 w-8 text-[#6E6E73] hover:bg-[#F5F5F7] rounded-lg">
                            <Edit3 className="w-3.5 h-3.5" />
                          </Button>
                          <Button onClick={(e) => { e.stopPropagation(); handleDelete(item.id, item.name); }} variant="ghost" size="icon" className="h-8 w-8 text-[#6E6E73] hover:bg-red-50 hover:text-red-500 rounded-lg">
                            <Trash2 className="w-3.5 h-3.5" />
                          </Button>
                        </div>
                      </div>
                    </div>
                    {isExpanded && item.courses && item.courses.length > 0 && (
                      <div className="px-4 pb-4 pl-14">
                        <div className="rounded-xl bg-[#F5F5F7]/60 p-3 space-y-1.5">
                          {item.courses.map((c: any) => (
                            <div key={c.id} className="flex items-center gap-3 py-1.5 px-2 rounded-lg hover:bg-white/60 transition-colors">
                              <div className="h-8 w-8 rounded-lg bg-white flex items-center justify-center overflow-hidden shrink-0">
                                {c.cover_image ? (
                                  <img src={c.cover_image} alt="" className="h-full w-full object-cover" />
                                ) : (
                                  <ImageIcon className="h-3.5 w-3.5 text-[#AEAEB2]" />
                                )}
                              </div>
                              <span className="text-xs font-medium text-[#1D1D1F] truncate">{c.title}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    {isExpanded && (!item.courses || item.courses.length === 0) && (
                      <div className="px-4 pb-4 pl-14">
                        <p className="text-xs text-[#AEAEB2] font-medium py-2">{t('sectionList.noAlbums', { defaultValue: '暂无课程' })}</p>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </ScrollArea>
        </Card>
      )}

      {/* Create Dialog */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="sm:max-w-[600px] rounded-3xl p-8 border-none shadow-[0_0_0_1px_rgba(0,0,0,0.04),0_4px_8px_rgba(0,0,0,0.04),0_16px_32px_rgba(0,0,0,0.08),0_32px_64px_rgba(0,0,0,0.04)] bg-white text-left">
          <DialogHeader>
            <DialogTitle className="text-lg font-semibold flex items-center gap-3">
              <Layers className="h-5 w-5 text-[#6E6E73]" /> {t('album.newAlbum')}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-5 pt-4">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">专辑名称</Label>
              <Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder={t('album.namePlaceholder')} className="bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 h-11 rounded-xl px-4 text-sm font-medium" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">描述</Label>
              <textarea value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} className="w-full bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 rounded-2xl p-5 min-h-[100px] font-medium text-sm resize-none outline-none" placeholder={t('album.descPlaceholder')} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">{t('album.uploadCover')}</Label>
              <div className="relative">
                <Button variant="outline" className="w-full h-14 rounded-xl border-dashed border-2 border-black/[0.06] hover:border-[#0071E3]/30 bg-[#F5F5F7]/50 hover:bg-[#F5F5F7] px-4 font-medium text-xs text-[#6E6E73] hover:text-[#1D1D1F] transition-[border-color,background-color,color] justify-between">
                  <span>{form.cover ? form.cover.name : t('album.uploadCover')}</span>
                  <Upload className="w-4 h-4 opacity-30" />
                </Button>
                <input type="file" onChange={e => setForm({ ...form, cover: e.target.files?.[0] || null })} className="absolute inset-0 opacity-0 cursor-pointer" accept="image/*" />
              </div>
            </div>
            <Button onClick={handleCreate} className="w-full h-11 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm shadow-[0_1px_3px_rgba(0,113,227,0.3)] transition-[background-color,box-shadow]">
              {t('album.createAlbum')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={!!editingItem} onOpenChange={open => !open && setEditingItem(null)}>
        <DialogContent className="sm:max-w-[600px] rounded-3xl p-8 border-none shadow-[0_0_0_1px_rgba(0,0,0,0.04),0_4px_8px_rgba(0,0,0,0.04),0_16px_32px_rgba(0,0,0,0.08),0_32px_64px_rgba(0,0,0,0.04)] bg-white text-left">
          <DialogHeader>
            <DialogTitle className="text-lg font-semibold">{t('sectionList.editAlbum')}</DialogTitle>
          </DialogHeader>
          <div className="space-y-5 pt-4">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">名称</Label>
              <Input value={editingItem?.name || ''} onChange={e => setEditingItem({ ...editingItem, name: e.target.value })} className="bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 h-11 rounded-xl px-4 text-sm font-medium" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">描述</Label>
              <textarea value={editingItem?.description || ''} onChange={e => setEditingItem({ ...editingItem, description: e.target.value })} className="w-full bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 rounded-2xl p-5 min-h-[80px] font-medium text-sm resize-none outline-none" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">{t('sectionList.updateCover')}</Label>
              <Input type="file" onChange={e => setEditingItem({ ...editingItem, cover_image: e.target.files?.[0] })} className="rounded-xl h-10 bg-[#F5F5F7] text-xs" accept="image/*" />
            </div>
            <Button onClick={handleUpdate} className="w-full h-11 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm shadow-[0_1px_3px_rgba(0,113,227,0.3)] transition-[background-color,box-shadow]">
              {t('editDialog.updateAndSync')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};
