import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Tag, Plus, Trash2, ChevronDown, ChevronRight, Image as ImageIcon } from 'lucide-react';
import api from '@/lib/api';
import { toast } from 'sonner';
import { useConfirm } from '@/components/useConfirm';

export const TagSection: React.FC = () => {
  useTranslation('maintenance');
  const { confirm, Dialog: ConfirmDialog } = useConfirm();
  const [tags, setTags] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [newTagName, setNewTagName] = useState('');

  const fetchTags = useCallback(async () => {
    try {
      const res = await api.get('/courses/tags/');
      setTags(res.data);
    } catch (e) { console.debug('[TagSection] fetch failed:', e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchTags(); }, [fetchTags]);

  const handleCreate = async () => {
    if (!newTagName.trim()) return toast.error('请输入标签名');
    try {
      await api.post('/courses/tags/', { name: newTagName.trim() });
      toast.success('标签已创建');
      setNewTagName('');
      setShowCreate(false);
      fetchTags();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '创建失败');
    }
  };

  const handleDelete = async (tag: any) => {
    if (!(await confirm(`删除标签「${tag.name}」？此操作仅解除关联，不影响课程。`))) return;
    try {
      await api.delete(`/courses/tags/${tag.id}/`);
      toast.success('已移除');
      fetchTags();
    } catch { toast.error('删除失败'); }
  };

  if (loading) return null;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Tag className="h-5 w-5 text-[#6E6E73]" />
          <h3 className="text-lg font-semibold tracking-tight">标签管理</h3>
          <Badge variant="secondary" className="text-[11px] rounded-full bg-[#F5F5F7] text-[#6E6E73] hover:bg-[#F5F5F7]">{tags.length}</Badge>
        </div>
        <Button onClick={() => setShowCreate(true)} className="h-10 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm px-5 shadow-[0_1px_3px_rgba(0,113,227,0.3)] transition-[background-color,box-shadow] gap-2">
          <Plus className="w-4 h-4" />
          新建标签
        </Button>
      </div>

      {/* List */}
      {tags.length === 0 ? (
        <Card className="p-16 bg-white rounded-2xl border border-black/[0.04] shadow-[0_1px_2px_rgba(0,0,0,0.02),0_4px_16px_rgba(0,0,0,0.03)] text-center">
          <Tag className="h-10 w-10 text-[#AEAEB2] mx-auto mb-4 opacity-30" />
          <p className="text-sm text-[#8E8E93] font-medium">暂无标签</p>
          <p className="text-xs text-[#AEAEB2] mt-1">点击上方按钮创建第一个标签</p>
        </Card>
      ) : (
        <Card className="bg-white rounded-2xl border border-black/[0.04] shadow-[0_1px_2px_rgba(0,0,0,0.02),0_4px_16px_rgba(0,0,0,0.03)] overflow-hidden">
          <ScrollArea className="h-[560px]">
            <div className="divide-y divide-black/[0.04]">
              {tags.map((tag: any) => {
                const isExpanded = expandedId === tag.id;
                return (
                  <div key={tag.id}>
                    <div
                      className="flex items-center justify-between p-4 hover:bg-[#F5F5F7]/50 transition-colors group cursor-pointer"
                      onClick={() => setExpandedId(isExpanded ? null : tag.id)}
                    >
                      <div className="flex items-center gap-3">
                        {isExpanded ? (
                          <ChevronDown className="h-4 w-4 text-[#AEAEB2] shrink-0" />
                        ) : (
                          <ChevronRight className="h-4 w-4 text-[#AEAEB2] shrink-0" />
                        )}
                        <span className="text-sm font-medium">{tag.name}</span>
                        <Badge variant="secondary" className="text-[11px] rounded-full bg-[#F5F5F7] text-[#8E8E93] font-medium hover:bg-[#F5F5F7]">
                          {tag.course_count ?? 0} 个课程
                        </Badge>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 rounded-lg opacity-0 group-hover:opacity-100 hover:bg-red-50 transition-all"
                        onClick={(e) => { e.stopPropagation(); handleDelete(tag); }}
                      >
                        <Trash2 className="w-3.5 h-3.5 text-red-500" />
                      </Button>
                    </div>
                    {isExpanded && tag.courses && tag.courses.length > 0 && (
                      <div className="px-4 pb-4 pl-14">
                        <div className="rounded-xl bg-[#F5F5F7]/60 p-3 space-y-1.5">
                          {tag.courses.map((c: any) => (
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
                    {isExpanded && (!tag.courses || tag.courses.length === 0) && (
                      <div className="px-4 pb-4 pl-14">
                        <p className="text-xs text-[#AEAEB2] font-medium py-2">暂无关联课程</p>
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
        <DialogContent className="sm:max-w-[440px] rounded-3xl p-8 border-none shadow-[0_0_0_1px_rgba(0,0,0,0.04),0_4px_8px_rgba(0,0,0,0.04),0_16px_32px_rgba(0,0,0,0.08),0_32px_64px_rgba(0,0,0,0.04)] bg-white text-left">
          <DialogHeader>
            <DialogTitle className="text-lg font-semibold flex items-center gap-3">
              <Tag className="h-5 w-5 text-[#6E6E73]" /> 新建标签
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-5 pt-4">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">标签名称</Label>
              <Input
                value={newTagName}
                onChange={e => setNewTagName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleCreate()}
                placeholder="输入标签名…"
                className="bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 h-11 rounded-xl px-4 text-sm font-medium"
              />
            </div>
            <Button onClick={handleCreate} className="w-full h-11 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm shadow-[0_1px_3px_rgba(0,113,227,0.3)] transition-[background-color,box-shadow]">
              创建
            </Button>
          </div>
        </DialogContent>
      </Dialog>
      {ConfirmDialog}
    </div>
  );
};
