import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { BookOpen, Video, Image as ImageIcon, FileArrowUp, PencilSimple, Trash, Plus, Check, X, DotsSixVertical } from '@phosphor-icons/react';
import { MarkdownEditor } from '@/components/MarkdownEditor';
import { TagAutocomplete } from '@/components/TagAutocomplete';
import { QuickCreateKPDialog } from './QuickCreateKPDialog';
import { QuickCreateAlbumDialog } from './QuickCreateAlbumDialog';
import { createCourseWithSmartUpload } from '@/lib/chunkedUpload';
import { useUploadStore } from '@/store/useUploadStore';
import { Pagination } from '@/components/Pagination';
import api from '@/lib/api';
import { formatApiErrorToast } from '@/lib/apiError';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { useConfirm } from '@/components/useConfirm';

export const CourseSection: React.FC = () => {
  const { confirm, Dialog: ConfirmDialog } = useConfirm();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [kpList, setKpList] = useState<any[]>([]);
  const [albumList, setAlbumList] = useState<any[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [editingItem, setEditingItem] = useState<any | null>(null);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [showNewKP, setShowNewKP] = useState(false);
  const [showNewAlbum, setShowNewAlbum] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const sortBy = 'sort_order';
  const [dragIdx, setDragIdx] = useState<number | null>(null);
  // 拖拽顺序用 ref 同步维护：dragOver/dragEnd 是连续事件，React 渲染可能滞后，
  // 直接读 state 闭包会拿到旧顺序，导致提交的排序不是用户看到的结果
  const itemsRef = useRef<any[]>([]);
  const dragIdxRef = useRef<number | null>(null);
  const [form, setForm] = useState({
    title: '', album_obj: '0', desc: '', elo_reward: 50,
    knowledge_point: '0', video: null as File | null,
    cover: null as File | null, courseware: null as File | null,
    tags: [] as string[],
  });

  const fetchData = useCallback(async (p = 1) => {
    try {
      const [c, k, a] = await Promise.all([
        api.get('/courses/', { params: { page: p, page_size: 100, ordering: sortBy } }),
        api.get('/quizzes/knowledge-points/'),
        api.get('/courses/albums/'),
      ]);
      setItems(c.data.items || c.data);
      itemsRef.current = c.data.items || c.data;
      setTotal(c.data.total ?? c.data.length ?? 0);
      setTotalPages(c.data.total_pages ?? 1);
      setKpList(k.data);
      setAlbumList(a.data);
    } catch (e) { console.debug('[CourseSection] fetch failed:', e); }
    finally { setLoading(false); }
  }, [sortBy]);

  useEffect(() => { fetchData(page); }, [fetchData, page]);

  const handleDragStart = (idx: number) => {
    dragIdxRef.current = idx;
    setDragIdx(idx);
  };

  const handleDragOver = (e: React.DragEvent, idx: number) => {
    e.preventDefault();
    const from = dragIdxRef.current;
    if (from === null || from === idx) return;
    const reordered = [...itemsRef.current];
    const [moved] = reordered.splice(from, 1);
    reordered.splice(idx, 0, moved);
    itemsRef.current = reordered;
    dragIdxRef.current = idx;
    setItems(reordered);
    setDragIdx(idx);
  };

  const handleDragEnd = async () => {
    dragIdxRef.current = null;
    setDragIdx(null);
    const updated = itemsRef.current.map((item: any, i: number) => ({ id: item.id, sort_order: i }));
    try {
      await api.post('/courses/reorder/', { items: updated });
    } catch {
      toast.error('排序保存失败，请重试');
      fetchData(page);
    }
  };

  const resetForm = () => setForm({
    title: '', album_obj: '0', desc: '', elo_reward: 50,
    knowledge_point: '0', video: null, cover: null, courseware: null, tags: [],
  });

  const handleVideoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    if (!file) return setForm({ ...form, video: null });
    setForm({ ...form, video: file });
  };

  const handleCreate = async () => {
    if (!form.title || !form.video) return toast.error('核心信息不全');
    setIsSubmitting(true);

    const file = form.video;
    const title = form.title;
    const desc = form.desc;
    const eloReward = form.elo_reward;
    const albumObj = form.album_obj;
    const knowledgePoint = form.knowledge_point;
    const cover = form.cover;
    const courseware = form.courseware;
    const tags = form.tags;

    const controller = new AbortController();
    const uploadId = `${Date.now()}-${file.name}`;
    const { addTask, updateProgress, setStatus } = useUploadStore.getState();
    addTask({ id: uploadId, fileName: file.name, progress: 0, status: 'uploading', controller });

    resetForm();
    setShowCreate(false);
    setIsSubmitting(false);

    try {
      await createCourseWithSmartUpload({
        title,
        description: desc,
        eloReward,
        albumObj: albumObj !== '0' ? albumObj : undefined,
        knowledgePoint: knowledgePoint !== '0' ? knowledgePoint : undefined,
        tags,
        video: file,
        cover,
        courseware,
        signal: controller.signal,
        onProgress: (p) => {
          updateProgress(uploadId, p);
          if (p >= 95) setStatus(uploadId, 'processing');
        },
      });
      setStatus(uploadId, 'completed');
      toast.success('课程已发布');
      fetchData();
    } catch (e: any) {
      if (e?.name === 'AbortError' || e?.code === 'ERR_CANCELED') return;
      const message = formatApiErrorToast(e, '发布失败');
      toast.error(message);
      setStatus(uploadId, 'failed', message);
    }
  };

  const handleUpdate = async () => {
    if (!editingItem) return;
    const fd = new FormData();
    Object.keys(editingItem).forEach(key => {
      if (editingItem[key] instanceof File) fd.append(key, editingItem[key]);
      else if (editingItem[key] !== null && editingItem[key] !== undefined) {
        if (['video_file', 'cover_image', 'courseware'].includes(key) && typeof editingItem[key] === 'string') return;
        fd.append(key, String(editingItem[key]));
      }
    });
    try {
      await api.patch(`/courses/${editingItem.id}/`, fd);
      toast.success('核心配置已同步');
      setEditingItem(null);
      fetchData();
    } catch { toast.error('更新失败'); }
  };

  const handleDelete = async (id: number, title: string) => {
    if (!(await confirm(`删除课程「${title}」？此操作不可撤销。`))) return;
    try {
      await api.delete(`/courses/${id}/`);
      toast.success('已删除');
      fetchData();
    } catch { toast.error('删除失败'); }
  };

  const onKPCreated = (kpId: string) => {
    setForm(prev => ({ ...prev, knowledge_point: kpId }));
  };

  const onAlbumCreated = (albumId: string) => {
    setForm(prev => ({ ...prev, album_obj: albumId }));
  };

  if (loading) return null;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <a href="/courses" className="p-1 -ml-1 rounded-lg hover:bg-[#F5F5F7] transition-colors text-[#6E6E73] hover:text-[#1D1D1F]" title="返回课程列表">
            <svg width="16" height="16" viewBox="0 0 256 256" fill="currentColor"><path d="M224 128a8 8 0 0 1-8 8H59.31l58.35 58.34a8 8 0 0 1-11.32 11.32l-72-72a8 8 0 0 1 0-11.32l72-72a8 8 0 0 1 11.32 11.32L59.31 120H216a8 8 0 0 1 8 8Z"/></svg>
          </a>
          <BookOpen className="h-5 w-5 text-[#6E6E73]" />
          <h3 className="text-lg font-semibold tracking-tight">课程管理</h3>
          <Badge variant="secondary" className="text-[11px] rounded-full bg-[#F5F5F7] text-[#6E6E73] hover:bg-[#F5F5F7]">{total}</Badge>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={() => { resetForm(); setShowCreate(true); }} className="h-10 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm px-5 shadow-[0_1px_3px_rgba(0,113,227,0.3)] transition-[background-color,box-shadow] gap-2">
            <Plus className="w-4 h-4" />
            上传课程
          </Button>
        </div>
      </div>

      {items.length === 0 ? (
        <Card className="p-16 bg-white rounded-2xl border border-black/[0.04] shadow-[0_1px_2px_rgba(0,0,0,0.02),0_4px_16px_rgba(0,0,0,0.03)] text-center">
          <BookOpen className="h-10 w-10 text-[#AEAEB2] mx-auto mb-4 opacity-30" />
          <p className="text-sm text-[#8E8E93] font-medium">暂无课程</p>
          <p className="text-xs text-[#AEAEB2] mt-1">点击上方按钮上传第一门课程</p>
        </Card>
      ) : (
        <>
        <Card className="bg-white rounded-2xl border border-black/[0.04] shadow-[0_1px_2px_rgba(0,0,0,0.02),0_4px_16px_rgba(0,0,0,0.03)] overflow-hidden">
          <ScrollArea className="h-[560px]">
            <div className="divide-y divide-black/[0.04]">
              {items.map((item: any, idx: number) => (
                <div key={item.id}
                  draggable
                  onDragStart={() => handleDragStart(idx)}
                  onDragOver={(e) => handleDragOver(e, idx)}
                  onDragEnd={handleDragEnd}
                  className={cn(
                    "p-4 hover:bg-[#F5F5F7]/50 transition-colors group",
                    dragIdx === idx && "opacity-50 bg-[#F5F5F7]"
                  )}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-start gap-3 min-w-0 flex-1">
                      <div className="cursor-grab active:cursor-grabbing pt-0.5 text-[#AEAEB2] hover:text-[#6E6E73] shrink-0" title="拖动排序">
                        <DotsSixVertical className="w-4 h-4" />
                      </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold truncate">{item.title}</p>
                      <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                        {item.album_name && <Badge variant="secondary" className="text-[10px] rounded-lg bg-[#F5F5F7] text-[#8E8E93] font-medium hover:bg-[#F5F5F7]">{item.album_name}</Badge>}
                        {item.knowledge_point_name && <Badge className="text-[10px] bg-[#0071E3]/10 text-[#0071E3] hover:bg-[#0071E3]/20 rounded-lg font-medium">{item.knowledge_point_name}</Badge>}
                        {item.tags?.map((tag: any, i: number) => (
                          <Badge key={i} className="text-[10px] bg-black text-white hover:bg-black/80 rounded-lg">{tag.name ?? tag}</Badge>
                        ))}
                      </div>
                      <div className="flex items-center gap-3 mt-2">
                        <span className="text-[11px] text-[#AEAEB2] font-medium">ELO: {item.elo_reward ?? 50}</span>
                        <span className="text-[11px] flex items-center gap-1 font-medium">
                          {item.video_file ? <Check className="w-3 h-3 text-emerald-500" /> : <X className="w-3 h-3 text-red-300" />}
                          <span className={item.video_file ? 'text-emerald-600' : 'text-[#AEAEB2]'}>视频</span>
                        </span>
                        <span className="text-[11px] flex items-center gap-1 font-medium">
                          {item.cover_image ? <Check className="w-3 h-3 text-emerald-500" /> : <X className="w-3 h-3 text-red-300" />}
                          <span className={item.cover_image ? 'text-emerald-600' : 'text-[#AEAEB2]'}>封面</span>
                        </span>
                        <span className="text-[11px] flex items-center gap-1 font-medium">
                          {item.courseware ? <Check className="w-3 h-3 text-emerald-500" /> : <X className="w-3 h-3 text-red-300" />}
                          <span className={item.courseware ? 'text-emerald-600' : 'text-[#AEAEB2]'}>课件</span>
                        </span>
                      </div>
                      <p className="text-[11px] text-[#AEAEB2] mt-1.5">
                        {item.created_at ? new Date(item.created_at).toLocaleDateString() : ''}
                        {item.updated_at && item.updated_at !== item.created_at ? ` · 更新 ${new Date(item.updated_at).toLocaleDateString()}` : ''}
                      </p>
                    </div>
                    </div>
                    <div className="flex gap-1 shrink-0 items-center">
                      <Button onClick={() => setEditingItem({ ...item })} variant="ghost" size="icon" className="h-8 w-8 text-[#6E6E73] hover:bg-[#F5F5F7] rounded-lg">
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
        <DialogContent className="sm:max-w-[900px] max-h-[90vh] overflow-y-auto rounded-3xl p-8 border-none shadow-[0_0_0_1px_rgba(0,0,0,0.04),0_4px_8px_rgba(0,0,0,0.04),0_16px_32px_rgba(0,0,0,0.08),0_32px_64px_rgba(0,0,0,0.04)] bg-white text-left">
          <DialogHeader>
            <DialogTitle className="text-lg font-semibold flex items-center gap-3">
              <BookOpen className="h-5 w-5 text-[#6E6E73]" /> 上传课程
            </DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 pt-4">
            {/* Left column: metadata */}
            <div className="lg:col-span-8 space-y-5">
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-[#6E6E73] ml-1">课程标题</Label>
                <Input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} className="bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 h-11 rounded-xl px-4 text-sm font-medium" />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium text-[#6E6E73] ml-1">所属专辑</Label>
                  <Select value={form.album_obj} onValueChange={v => v === 'NEW_ALBUM' ? setShowNewAlbum(true) : setForm({ ...form, album_obj: v })}>
                    <SelectTrigger className="h-10 rounded-xl bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 font-medium px-4 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="0">不挂载</SelectItem>
                      <SelectItem value="NEW_ALBUM" className="text-[#0071E3] font-semibold">+ 新建专辑</SelectItem>
                      {albumList.map(al => <SelectItem key={al.id} value={al.id.toString()}>{al.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium text-[#6E6E73] ml-1">关联知识点</Label>
                  <Select value={form.knowledge_point} onValueChange={v => v === 'NEW_KP' ? setShowNewKP(true) : setForm({ ...form, knowledge_point: v })}>
                    <SelectTrigger className="h-10 rounded-xl bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 font-medium px-4 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="0">不挂载</SelectItem>
                      <SelectItem value="NEW_KP" className="text-[#0071E3] font-semibold">+ 新建知识点</SelectItem>
                      {kpList.map(kp => <SelectItem key={kp.id} value={kp.id.toString()}>{kp.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-[#6E6E73] ml-1">详细描述</Label>
                <MarkdownEditor content={form.desc} onChange={v => setForm({ ...form, desc: v })} />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-[#6E6E73] ml-1">标签</Label>
                <TagAutocomplete tags={form.tags} setTags={(tg: string[]) => setForm({ ...form, tags: tg })} />
              </div>
            </div>
            {/* Right column: files + ELO */}
            <div className="lg:col-span-4 space-y-5">
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-[#6E6E73] ml-1">奖励设定</Label>
                <div className="flex items-center gap-3">
                  <Input type="number" value={form.elo_reward} onChange={e => setForm({ ...form, elo_reward: parseInt(e.target.value) || 0 })} className="bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 h-10 rounded-xl font-medium w-20 text-center text-sm" />
                  <span className="text-xs font-medium text-[#6E6E73]">ELO Reward</span>
                </div>
              </div>
              <div className="space-y-2">
                <Label className="text-xs font-medium text-[#6E6E73] ml-1">媒体附件</Label>
                <div className="relative">
                  <Button variant="outline" className="w-full h-12 rounded-xl border-dashed border-2 border-black/[0.06] hover:border-[#0071E3]/30 bg-[#F5F5F7]/50 hover:bg-[#F5F5F7] px-4 font-medium text-xs text-[#6E6E73] hover:text-[#1D1D1F] transition-[border-color,background-color,color] justify-between" type="button">
                    <span>{form.video ? form.video.name : '上传视频'}</span>
                    <Video className="w-4 h-4 opacity-30" />
                  </Button>
                  <input type="file" onChange={handleVideoChange} className="absolute inset-0 opacity-0 cursor-pointer" accept="video/*" />
                </div>
                <div className="relative">
                  <Button variant="outline" className="w-full h-12 rounded-xl border-dashed border-2 border-black/[0.06] hover:border-[#0071E3]/30 bg-[#F5F5F7]/50 hover:bg-[#F5F5F7] px-4 font-medium text-xs text-[#6E6E73] hover:text-[#1D1D1F] transition-[border-color,background-color,color] justify-between" type="button">
                    <span>{form.cover ? form.cover.name : '上传封面'}</span>
                    <ImageIcon className="w-4 h-4 opacity-30" />
                  </Button>
                  <input type="file" onChange={e => setForm({ ...form, cover: e.target.files?.[0] || null })} className="absolute inset-0 opacity-0 cursor-pointer" accept="image/*" />
                </div>
                <div className="relative">
                  <Button variant="outline" className="w-full h-12 rounded-xl border-dashed border-2 border-black/[0.06] hover:border-[#0071E3]/30 bg-[#F5F5F7]/50 hover:bg-[#F5F5F7] px-4 font-medium text-xs text-[#6E6E73] hover:text-[#1D1D1F] transition-[border-color,background-color,color] justify-between" type="button">
                    <span>{form.courseware ? form.courseware.name : '上传课件'}</span>
                    <FileArrowUp className="w-4 h-4 opacity-30" />
                  </Button>
                  <input type="file" onChange={e => setForm({ ...form, courseware: e.target.files?.[0] || null })} className="absolute inset-0 opacity-0 cursor-pointer" accept=".pdf" />
                </div>
              </div>
              <Button onClick={handleCreate} disabled={isSubmitting} className="w-full h-11 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm shadow-[0_1px_3px_rgba(0,113,227,0.3)] transition-[background-color,box-shadow]">
                Publish Academy
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={!!editingItem} onOpenChange={open => !open && setEditingItem(null)}>
        <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto rounded-3xl p-8 border-none shadow-[0_0_0_1px_rgba(0,0,0,0.04),0_4px_8px_rgba(0,0,0,0.04),0_16px_32px_rgba(0,0,0,0.08),0_32px_64px_rgba(0,0,0,0.04)] bg-white text-left">
          <DialogHeader>
            <DialogTitle className="text-lg font-semibold">属性核心配置</DialogTitle>
          </DialogHeader>
          <div className="space-y-5 pt-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-[#6E6E73] ml-1">标题</Label>
                <Input value={editingItem?.title || ''} onChange={e => setEditingItem({ ...editingItem, title: e.target.value })} className="bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 h-11 rounded-xl px-4 text-sm font-medium" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-[#6E6E73] ml-1">ELO 奖励</Label>
                <Input type="number" value={editingItem?.elo_reward || 0} onChange={e => setEditingItem({ ...editingItem, elo_reward: e.target.value })} className="bg-[#F5F5F7] border-transparent focus-visible:ring-1 focus-visible:ring-[#0071E3]/20 focus-visible:ring-offset-0 focus-visible:border-[#0071E3]/30 h-11 rounded-xl px-4 text-sm font-medium" />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium text-[#6E6E73] ml-1">描述</Label>
              <MarkdownEditor content={editingItem?.description || ''} onChange={v => setEditingItem({ ...editingItem, description: v })} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-[#6E6E73] ml-1">更新视频</Label>
                <Input type="file" onChange={e => setEditingItem({ ...editingItem, video_file: e.target.files?.[0] })} className="rounded-xl h-10 bg-[#F5F5F7] text-xs" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-medium text-[#6E6E73] ml-1">更新封面</Label>
                <Input type="file" onChange={e => setEditingItem({ ...editingItem, cover_image: e.target.files?.[0] })} className="rounded-xl h-10 bg-[#F5F5F7] text-xs" />
              </div>
            </div>
            <Button onClick={handleUpdate} className="w-full h-11 rounded-xl bg-[#0071E3] hover:bg-[#0077ED] text-white font-medium text-sm shadow-[0_1px_3px_rgba(0,113,227,0.3)] transition-[background-color,box-shadow]">
              Update & Sync
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Quick Create Dialogs */}
      <QuickCreateKPDialog open={showNewKP} onOpenChange={setShowNewKP} kpList={kpList} onCreated={onKPCreated} onRefresh={fetchData} />
      <QuickCreateAlbumDialog open={showNewAlbum} onOpenChange={setShowNewAlbum} onCreated={onAlbumCreated} onRefresh={fetchData} />
      {ConfirmDialog}
    </div>
  );
};
