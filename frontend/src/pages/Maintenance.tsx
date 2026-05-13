import React, { useState, useEffect, useMemo, useRef } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  BookOpen, FileText, Target, Video, Image as ImageIcon,
  Upload, Trash2, Edit3, Settings2, Bot, Sparkles, Bell, Send, Loader2,
  RefreshCcw, BrainCircuit, X, Layers, FileUp, CheckCircle2, Rocket, ShieldCheck, BarChart3
} from 'lucide-react';
import api from '@/lib/api';
import { toast } from 'sonner';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ScrollArea } from '@/components/ui/scroll-area';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { MarkdownEditor } from '@/components/MarkdownEditor';

// Sub-components
import { TagInput, KPTreeNode } from './maintenance/MaintenanceComponents';
import { QuestionBankPanel } from './maintenance/QuestionBankPanel';
import { InsightsPanel } from './maintenance/InsightsPanel';
import { MembershipPanel } from './maintenance/MembershipPanel';
import { AuditPanel } from './maintenance/AuditPanel';
import { PipelinePanel } from './maintenance/PipelinePanel';
import { PromptTemplatesPanel } from './maintenance/PromptTemplatesPanel';

export const Maintenance: React.FC = () => {
  const CHUNKED_UPLOAD_THRESHOLD_BYTES = 100 * 1024 * 1024;
  const CHUNK_SIZE_BYTES = 10 * 1024 * 1024;
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  // Data Lists
  const [courseList, setCourseList] = useState<any[]>([]);
  const [articleList, setArticleList] = useState<any[]>([]);
  const [botList, setBotList] = useState<any[]>([]);
  const [kpList, setKpList] = useState<any[]>([]);
  const [albumList, setAlbumList] = useState<any[]>([]);
  const [smList, setSmList] = useState<any[]>([]);

  // UI State
  const [auditMode, setAuditMode] = useState<'hub' | 'courses' | 'articles' | 'kp' | 'sm'>('hub');
  const [qSearch, setQSearch] = useState('');
  const [editingItem, setEditingItem] = useState<{ type: string, data: any } | null>(null);

  // KP Creation Logic
  const [showNewKPDialog, setShowNewKPDialog] = useState(false);
  const [newKPForm, setNewKPForm] = useState({ name: '', description: '', parent: '0' });
  const [kpCreationTarget, setKPCreationTarget] = useState<'course' | 'article' | 'none'>('course');

  // AI Workshop State
  const [showAIWorkstation, setShowAIWorkstation] = useState(false);
  const [aiInputText, setAiInputText] = useState('');
  const [aiFile, setAiFile] = useState<File | null>(null);
  const [aiTargetKP, setAiTargetKP] = useState('0');
  const [aiPreviewData, setAiPreviewData] = useState<any[] | null>(null);
  const [isParsing, setIsParsing] = useState(false);
  const [parseProgress, setParseProgress] = useState("");

  // Forms
  const [courseForm, setCourseForm] = useState({ title: '', album_obj: '0', desc: '', elo_reward: 50, knowledge_point: '0', video: null as File | null, cover: null as File | null, courseware: null as File | null });
  const [articleForm, setArticleForm] = useState({ title: '', content: '', author_display_name: '', tags: [] as string[], knowledge_point: '0' });
  const [botForm, setBotForm] = useState({ name: '', prompt: '', avatar: null as File | null, is_exclusive: false });
  const [albumForm, setAlbumForm] = useState({ name: '', description: '', cover: null as File | null });
  const [quizForm, setQuizForm] = useState({ text: '', q_type: 'objective', subjective_type: 'noun', grading_points: '', knowledge_point: '0', options: ['', '', '', ''], answer: '', difficulty_level: 'normal' });
  const [kpForm, setKpForm] = useState({ name: '', description: '', parent: '0' });
  const [smForm, setSmForm] = useState({ name: '', description: '', file: null as File | null });
  const [notifForm, setNotifForm] = useState({ title: '', content: '', link: '' });
  const [isSendingNotif, setIsSendingNotif] = useState(false);

  // BI & Codes
  const [codes, setCodes] = useState<any[]>([]);
  const [newCodeCount, setNewCodeCount] = useState(1);
  const [isGeneratingCodes, setIsGeneratingCodes] = useState(false);
  const [biData, setBIData] = useState<any>(null);
  const [isLoadingBI, setIsLoadingBI] = useState(false);

  const fetchLists = async () => {
    try {
      const [c, a, b, k, al, sm] = await Promise.all([
        api.get('/courses/'), api.get('/articles/'), api.get('/ai/bots/'),
        api.get('/quizzes/knowledge-points/'), api.get('/courses/albums/'), api.get('/courses/startup-materials/')
      ]);
      setCourseList(c.data); setArticleList(a.data.articles || []); setBotList(b.data); setKpList(k.data); setAlbumList(al.data); setSmList(sm.data);
    } catch (e) { }
  };

  const fetchBI = async () => {
    setIsLoadingBI(true);
    try { const res = await api.get('/users/admin/bi/'); setBIData(res.data); } catch (e) { toast.error("分析数据同步失败"); }
    finally { setIsLoadingBI(false); }
  };

  const fetchCodes = async () => { try { const res = await api.get('/users/admin/codes/'); setCodes(res.data); } catch (e) {} };

  useEffect(() => { fetchLists(); fetchCodes(); fetchBI(); }, []);

  const handleDelete = async (type: string, id: number) => {
    try {
      let endpoint = `/${type}/${id}/`;
      if (type === 'kp') endpoint = `/quizzes/knowledge-points/${id}/`;
      if (type === 'quizzes') endpoint = `/quizzes/questions/${id}/`;
      if (type === 'sm') endpoint = `/courses/startup-materials/${id}/`;
      await api.delete(endpoint);
      toast.success("已移除"); fetchLists();
    } catch (e) { toast.error("删除失败"); }
  };

  const handleCreateCourse = async () => {
    if (!courseForm.title || !courseForm.video) return toast.error("核心信息不全");
    setIsSubmitting(true); setUploadProgress(2);
    const file = courseForm.video;

    try {
      if (file.size <= CHUNKED_UPLOAD_THRESHOLD_BYTES) {
        const fd = new FormData();
        fd.append('title', courseForm.title);
        fd.append('description', courseForm.desc);
        fd.append('elo_reward', courseForm.elo_reward.toString());
        if (courseForm.album_obj !== '0') fd.append('album_obj', courseForm.album_obj);
        if (courseForm.knowledge_point !== '0') fd.append('knowledge_point', courseForm.knowledge_point);
        fd.append('video_file', file);
        if (courseForm.cover) fd.append('cover_image', courseForm.cover);
        if (courseForm.courseware) fd.append('courseware', courseForm.courseware);
        await api.post('/courses/', fd, {
          onUploadProgress: p => p.total && setUploadProgress(Math.round((p.loaded / p.total) * 100)),
        });
      } else {
        const totalChunks = Math.ceil(file.size / CHUNK_SIZE_BYTES);
        const initRes = await api.post('/courses/chunked/init/', {
          file_name: file.name,
          total_size: file.size,
          chunk_size: CHUNK_SIZE_BYTES,
          total_chunks: totalChunks,
          mime_type: file.type || 'application/octet-stream',
        });
        const uploadId = initRes.data?.upload_id;
        if (!uploadId) throw new Error('missing upload id');

        for (let i = 0; i < totalChunks; i++) {
          const start = i * CHUNK_SIZE_BYTES;
          const end = Math.min(start + CHUNK_SIZE_BYTES, file.size);
          const chunkBlob = file.slice(start, end);
          const chunkFd = new FormData();
          chunkFd.append('chunk_index', i.toString());
          chunkFd.append('chunk', chunkBlob, `${file.name}.part${i}`);
          await api.post(`/courses/chunked/${uploadId}/chunk/`, chunkFd);
          setUploadProgress(Math.floor(((i + 1) / totalChunks) * 95));
        }

        const completeFd = new FormData();
        completeFd.append('title', courseForm.title);
        completeFd.append('description', courseForm.desc);
        completeFd.append('elo_reward', courseForm.elo_reward.toString());
        if (courseForm.album_obj !== '0') completeFd.append('album_obj', courseForm.album_obj);
        if (courseForm.knowledge_point !== '0') completeFd.append('knowledge_point', courseForm.knowledge_point);
        if (courseForm.cover) completeFd.append('cover_image', courseForm.cover);
        if (courseForm.courseware) completeFd.append('courseware', courseForm.courseware);
        await api.post(`/courses/chunked/${uploadId}/complete/`, completeFd);
        setUploadProgress(100);
      }

      toast.success("课程已发布");
      fetchLists();
    } catch (e: any) {
      const status = e?.response?.status;
      const detail = e?.response?.data?.detail || e?.response?.data?.error || e?.response?.data?.message;
      if (status === 403) toast.error("当前账号无管理员权限，无法发布课程");
      else if (typeof detail === 'string' && detail.trim()) toast.error(detail);
      else toast.error("发布失败");
    } finally {
      setIsSubmitting(false);
      setUploadProgress(0);
    }
  };

  const handleVideoFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    if (!file) return setCourseForm({ ...courseForm, video: null });
    if (file.size > CHUNKED_UPLOAD_THRESHOLD_BYTES) toast.message("大文件将自动启用分片上传");
    setCourseForm({ ...courseForm, video: file });
  };

  const handleCreateQuiz = async () => {
    if (!quizForm.text) return toast.error("题目缺失");
    try {
      await api.post('/quizzes/questions/', {
        text: quizForm.text, q_type: quizForm.q_type, subjective_type: quizForm.subjective_type,
        grading_points: quizForm.grading_points, knowledge_point: quizForm.knowledge_point === "0" ? null : quizForm.knowledge_point,
        options: quizForm.q_type === 'objective' ? quizForm.options : null, correct_answer: quizForm.answer, 
        difficulty_level: quizForm.difficulty_level
      });
      toast.success("题目已入库"); fetchLists();
    } catch (e) { toast.error("入库失败"); }
  };

  const handleCreateBot = async () => {
    if (!botForm.name || !botForm.prompt) return toast.error("信息不完整");
    const fd = new FormData(); fd.append('name', botForm.name); fd.append('system_prompt', botForm.prompt); fd.append('is_exclusive', String(botForm.is_exclusive)); if (botForm.avatar) fd.append('avatar', botForm.avatar);
    try {
      const res = await api.post('/ai/bots/', fd);
      const templateName = res.data?.prompt_template_name;
      toast.success(templateName ? `助教已上线，并创建 Prompt：${templateName}` : "助教已上线");
      setBotForm({ name: '', prompt: '', avatar: null, is_exclusive: false });
      fetchLists();
    }
    catch (e) { toast.error("发布失败"); }
  };

  const handleCreateAlbum = async () => {
    if (!albumForm.name) return toast.error("专辑名称必填");
    const fd = new FormData(); fd.append('name', albumForm.name); fd.append('description', albumForm.description); if (albumForm.cover) fd.append('cover_image', albumForm.cover);
    try { await api.post('/courses/albums/', fd); toast.success("专辑已创建"); setAlbumForm({ name: '', description: '', cover: null }); fetchLists(); }
    catch (e) { toast.error("失败"); }
  };

  const handleGenerateCodes = async () => {
    setIsGeneratingCodes(true);
    try {
      for (let i = 0; i < newCodeCount; i++) {
        const randomCode = Math.random().toString(36).substring(2, 10).toUpperCase();
        await api.post('/users/admin/codes/', { code: randomCode });
      }
      toast.success(`已生成 ${newCodeCount} 个激活码`); fetchCodes();
    } catch (e) { toast.error("生成失败"); } finally { setIsGeneratingCodes(false); }
  };

  const handleDeleteCode = async (id: number) => {
    if (!confirm("确定收回此激活码吗？")) return;
    try { await api.delete(`/users/admin/codes/${id}/`); toast.success("已收回"); fetchCodes(); } catch (e) { toast.error("操作失败"); }
  };

  const handleCreateSM = async () => {
    if (!smForm.name || !smForm.file) return toast.error("信息不全");
    setIsSubmitting(true); setUploadProgress(10);
    const fd = new FormData(); fd.append('name', smForm.name); fd.append('description', smForm.description); fd.append('file', smForm.file);
    try { await api.post('/courses/startup-materials/', fd, { onUploadProgress: p => p.total && setUploadProgress(Math.round((p.loaded / p.total) * 100)) }); toast.success("资料已上传"); setSmForm({ name: '', description: '', file: null }); fetchLists(); }
    catch (e) { toast.error("上传失败"); } finally { setIsSubmitting(false); setUploadProgress(0); }
  };

  const handleBroadcast = async () => {
    if (!notifForm.title || !notifForm.content) return toast.error("内容必填");
    setIsSendingNotif(true);
    try { await api.post('/notifications/broadcast/', notifForm); toast.success("通知已全站广播"); setNotifForm({ title: '', content: '', link: '' }); } 
    catch (e) { toast.error("发送失败"); } finally { setIsSendingNotif(false); }
  };

  const handleQuickCreateKP = async () => {
    if (!newKPForm.name) return toast.error("名称必填");
    try {
      const res = await api.post('/quizzes/knowledge-points/', { ...newKPForm, parent: newKPForm.parent === "0" ? null : newKPForm.parent });
      const newKPId = res.data.id.toString(); await fetchLists();
      if (kpCreationTarget === 'course') setCourseForm(prev => ({ ...prev, knowledge_point: newKPId }));
      else if (kpCreationTarget === 'article') setArticleForm(prev => ({ ...prev, knowledge_point: newKPId }));
      setShowNewKPDialog(false); setNewKPForm({ name: '', description: '', parent: '0' });
    } catch (e) { toast.error("创建失败"); }
  };

  const handleSaveEdit = async () => {
    if (!editingItem) return;
    const { type, data } = editingItem;
    let endpoint = `/${type}/${data.id}/`;
    if (type === 'kp') endpoint = `/quizzes/knowledge-points/${data.id}/`;
    if (type === 'quizzes') endpoint = `/quizzes/questions/${data.id}/`;
    if (type === 'sm') endpoint = `/courses/startup-materials/${data.id}/`;

    try {
      if (['courses', 'albums', 'bots', 'sm'].includes(type)) {
        const fd = new FormData();
        Object.keys(data).forEach(key => {
          if (data[key] instanceof File) fd.append(key, data[key]);
          else if (data[key] !== null) {
            if (['video_file', 'cover_image', 'avatar', 'courseware', 'file'].includes(key) && typeof data[key] === 'string') return;
            fd.append(key, String(data[key]));
          }
        });
        await api.patch(endpoint, fd);
      } else { await api.patch(endpoint, data); }
      toast.success("核心配置已同步"); setEditingItem(null); fetchLists();
    } catch (e: any) { toast.error("更新失败"); }
  };

  // AI Logic
  const handleAIParse = async () => {
    if (!aiInputText.trim() && !aiFile) return toast.error("未提供语料");
    setIsParsing(true); setParseProgress("初始化 AI 引擎...");
    const fd = new FormData();
    if (aiInputText) fd.append('raw_text', aiInputText);
    if (aiFile) fd.append('file', aiFile);
    try {
      const res = await api.post('/quizzes/ai-parse-raw-text/', fd);
      const taskId = res.data.task_id;
      const poll = setInterval(async () => {
        try {
          const checkRes = await api.get(`/quizzes/ai-parse-raw-text/?task_id=${taskId}`);
          if (checkRes.data.progress) setParseProgress(`正在深度解析: 分片 ${checkRes.data.progress}`);
          if (checkRes.data.status === 'completed') {
            clearInterval(poll); setAiPreviewData(checkRes.data.data);
            toast.success(`解析完成，共发现 ${checkRes.data.data.length} 道题目`);
            setIsParsing(false); setParseProgress("");
          }
        } catch (e) { clearInterval(poll); setIsParsing(false); setParseProgress(""); }
      }, 3000);
    } catch (e) { setIsParsing(false); setParseProgress(""); }
  };

  const handleAIImport = async () => {
    if (!aiPreviewData) return;
    try {
      await api.post('/quizzes/ai-bulk-import/', { questions: aiPreviewData, kp_id: aiTargetKP === '0' ? null : aiTargetKP });
      toast.success("成功导入题库"); setAiPreviewData(null); setShowAIWorkstation(false); fetchLists();
    } catch (e) { toast.error("导入失败"); }
  };

  const roots = useMemo(() => kpList.filter(kp => !kp.parent), [kpList]);

  return (
    <div className="p-6 space-y-6 animate-in fade-in duration-500 max-w-[1600px] mx-auto overflow-hidden text-left">
      <Button onClick={() => setShowAIWorkstation(true)} className="fixed bottom-10 right-10 h-12 w-12 rounded-full bg-emerald-500 text-white shadow-2xl hover:scale-110 transition-all z-[60] animate-pulse"><Sparkles className="w-5 h-5" /></Button>

      <Tabs defaultValue="courses" className="space-y-6">
        <TabsList className="bg-white/50 backdrop-blur-md p-1.5 rounded-2xl border border-black/5 h-auto flex flex-wrap gap-1.5 shadow-sm w-fit mx-auto">
          <TabsTrigger value="courses" className="rounded-xl px-4 py-2 text-[11px] font-bold uppercase"><BookOpen className="w-3.5 h-3.5 mr-2" />课程上传</TabsTrigger>
          <TabsTrigger value="articles" className="rounded-xl px-4 py-2 text-[11px] font-bold uppercase"><FileText className="w-3.5 h-3.5 mr-2" />发布文章</TabsTrigger>
          <TabsTrigger value="quizzes" className="rounded-xl px-4 py-2 text-[11px] font-bold uppercase"><Target className="w-3.5 h-3.5 mr-2" />智能题库</TabsTrigger>
          <TabsTrigger value="kp" className="rounded-xl px-4 py-2 text-[11px] font-bold uppercase"><BrainCircuit className="w-3.5 h-3.5 mr-2" />知识体系</TabsTrigger>
          <TabsTrigger value="albums" className="rounded-xl px-4 py-2 text-[11px] font-bold uppercase"><Layers className="w-3.5 h-3.5 mr-2" />专辑管理</TabsTrigger>
          <TabsTrigger value="bots" className="rounded-xl px-4 py-2 text-[11px] font-bold uppercase"><Bot className="w-3.5 h-3.5 mr-2" />AI 机器人</TabsTrigger>
          <TabsTrigger value="sm" className="rounded-xl px-4 py-2 text-[11px] font-bold uppercase"><Rocket className="w-3.5 h-3.5 mr-2" />启动资料</TabsTrigger>
          <TabsTrigger value="notifications" className="rounded-xl px-4 py-2 text-[11px] font-bold uppercase"><Bell className="w-3.5 h-3.5 mr-2" />全站广播</TabsTrigger>
          <TabsTrigger value="membership" className="rounded-xl px-4 py-2 text-[11px] font-bold uppercase"><ShieldCheck className="h-3.5 w-3.5 mr-2" />激活码</TabsTrigger>
          <TabsTrigger value="insights" className="rounded-xl px-4 py-2 text-[11px] font-bold uppercase"><BarChart3 className="w-3.5 h-3.5 mr-2" />数据洞察</TabsTrigger>
          <TabsTrigger value="manage" className="rounded-xl px-4 py-2 text-[11px] font-bold uppercase"><Settings2 className="w-3.5 h-3.5 mr-2" />资源审计</TabsTrigger>
          <TabsTrigger value="pipeline" className="rounded-xl px-4 py-2 text-[11px] font-bold uppercase"><Sparkles className="w-3.5 h-3.5 mr-2" />AI出题中心</TabsTrigger>
          <TabsTrigger value="prompts" className="rounded-xl px-4 py-2 text-[11px] font-bold uppercase"><FileText className="w-3.5 h-3.5 mr-2" />Prompt模板</TabsTrigger>
        </TabsList>

        <TabsContent value="courses">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <Card className="lg:col-span-8 p-8 bg-white rounded-3xl border-none shadow-sm space-y-6">
              <div className="space-y-2.5"><Label className="text-[11px] font-bold uppercase opacity-40 ml-1">课程标题</Label><Input value={courseForm.title} onChange={e => setCourseForm({ ...courseForm, title: e.target.value })} className="bg-[#F5F5F7] border-none h-12 rounded-xl font-bold px-5" /></div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2"><Label className="text-[11px] font-bold uppercase opacity-40 ml-1">所属专辑</Label><Select value={courseForm.album_obj} onValueChange={v => setCourseForm({ ...courseForm, album_obj: v })}><SelectTrigger className="h-10 rounded-xl bg-[#F5F5F7] border-none font-bold px-4 text-xs"><SelectValue /></SelectTrigger><SelectContent>{albumList.map(al => <SelectItem key={al.id} value={al.id.toString()}>{al.name}</SelectItem>)}</SelectContent></Select></div>
                <div className="space-y-2"><Label className="text-[11px] font-bold uppercase opacity-40 ml-1">关联知识点</Label><Select value={courseForm.knowledge_point} onValueChange={v => v === 'NEW_KP' ? (setKPCreationTarget('course'), setShowNewKPDialog(true)) : setCourseForm({ ...courseForm, knowledge_point: v })}><SelectTrigger className="h-10 rounded-xl bg-[#F5F5F7] border-none font-bold px-4 text-xs"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="0">不挂载</SelectItem><SelectItem value="NEW_KP" className="text-indigo-600 font-bold">+ 新建知识点</SelectItem>{kpList.map(kp => <SelectItem key={kp.id} value={kp.id.toString()}>{kp.name}</SelectItem>)}</SelectContent></Select></div>
              </div>
              <div className="space-y-2"><Label className="text-[11px] font-bold uppercase opacity-40 ml-1">详细描述</Label><MarkdownEditor content={courseForm.desc} onChange={v => setCourseForm({ ...courseForm, desc: v })} /></div>
            </Card>
            <Card className="lg:col-span-4 p-8 bg-white rounded-3xl border-none shadow-sm space-y-6">
              <div className="space-y-3"><Label className="text-[11px] font-bold uppercase opacity-40">奖励设定</Label><div className="flex items-center gap-3"><Input type="number" value={courseForm.elo_reward} onChange={e => setCourseForm({ ...courseForm, elo_reward: parseInt(e.target.value) || 0 })} className="bg-[#F5F5F7] border-none h-10 rounded-xl font-bold w-20 text-center" /><span className="text-[11px] font-bold opacity-40 uppercase">ELO Reward</span></div></div>
              <div className="space-y-4"><Label className="text-[11px] font-bold uppercase opacity-40">媒体附件</Label>
                <div className="relative"><Button variant="outline" className="w-full h-12 rounded-xl border-dashed border-2 px-4 font-bold text-[11px]"><span>{courseForm.video ? "视频已就绪" : "上传视频"}</span><Video className="w-4 h-4 opacity-20" /></Button><input type="file" onChange={handleVideoFileChange} className="absolute inset-0 opacity-0 cursor-pointer" accept="video/*" /></div>
                <div className="relative"><Button variant="outline" className="w-full h-12 rounded-xl border-dashed border-2 px-4 font-bold text-[11px]"><span>{courseForm.cover ? "封面已就绪" : "上传封面"}</span><ImageIcon className="w-4 h-4 opacity-20" /></Button><input type="file" onChange={e => setCourseForm({ ...courseForm, cover: e.target.files?.[0] || null })} className="absolute inset-0 opacity-0 cursor-pointer" accept="image/*" /></div>
                <div className="relative"><Button variant="outline" className="w-full h-12 rounded-xl border-dashed border-2 px-4 font-bold text-[11px]"><span>{courseForm.courseware ? "PDF已就绪" : "上传课件"}</span><FileUp className="w-4 h-4 opacity-20" /></Button><input type="file" onChange={e => setCourseForm({ ...courseForm, courseware: e.target.files?.[0] || null })} className="absolute inset-0 opacity-0 cursor-pointer" accept=".pdf" /></div>
              </div>
              <Button onClick={handleCreateCourse} disabled={isSubmitting} className="w-full h-14 rounded-2xl bg-black text-white font-bold uppercase tracking-widest text-[11px]">Publish Academy</Button>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="articles">
          <Card className="max-w-5xl mx-auto p-10 bg-white rounded-[2rem] border-none shadow-sm space-y-6">
            <div className="flex items-center gap-3"><FileText className="h-5 w-5 text-orange-600" /><h3 className="text-lg font-bold tracking-tight">撰写深度文章</h3></div>
            <div className="space-y-4">
              <Input value={articleForm.title} onChange={e => setArticleForm({ ...articleForm, title: e.target.value })} className="bg-[#F5F5F7] border-none h-14 rounded-xl font-black px-5 text-2xl tracking-tighter" placeholder="文章标题" />
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Select value={articleForm.knowledge_point} onValueChange={v => v === 'NEW_KP' ? (setKPCreationTarget('article'), setShowNewKPDialog(true)) : setArticleForm({ ...articleForm, knowledge_point: v })}><SelectTrigger className="h-10 rounded-xl bg-[#F5F5F7] border-none font-bold px-4 text-xs"><SelectValue placeholder="关联知识点" /></SelectTrigger><SelectContent><SelectItem value="0">不挂载</SelectItem><SelectItem value="NEW_KP" className="text-indigo-600 font-bold">+ 新建知识点</SelectItem>{kpList.map(kp => <SelectItem key={kp.id} value={kp.id.toString()}>{kp.name}</SelectItem>)}</SelectContent></Select>
                <Input value={articleForm.author_display_name} onChange={e => setArticleForm({ ...articleForm, author_display_name: e.target.value })} className="bg-[#F5F5F7] border-none h-10 rounded-xl font-bold px-5 text-[11px]" placeholder="作者署名" />
                <TagInput tags={articleForm.tags} setTags={t => setArticleForm({ ...articleForm, tags: t })} compact />
              </div>
              <MarkdownEditor content={articleForm.content} onChange={v => setArticleForm({ ...articleForm, content: v })} />
              <Button onClick={async () => { try { await api.post('/articles/', { ...articleForm, knowledge_point: articleForm.knowledge_point === "0" ? null : articleForm.knowledge_point }); toast.success("文章已发布"); setArticleForm({ title: '', content: '', author_display_name: '', tags: [], knowledge_point: '0' }); fetchLists(); } catch (e) { toast.error("失败"); } }} className="w-full h-12 rounded-xl bg-black text-white font-bold text-[11px] uppercase tracking-widest">Publish Article</Button>
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="quizzes">
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 items-start">
            <Card className="p-8 bg-white rounded-[2rem] border-none shadow-sm space-y-6">
              <div className="flex items-center gap-3"><Target className="h-6 w-6 text-blue-600" /><h3 className="text-xl font-bold tracking-tight">录入题目</h3></div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <Select value={quizForm.q_type} onValueChange={v => setQuizForm({ ...quizForm, q_type: v })}><SelectTrigger className="h-10 rounded-xl bg-[#F5F5F7] border-none font-bold text-xs"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="objective">客观题</SelectItem><SelectItem value="subjective">主观题</SelectItem></SelectContent></Select>
                {quizForm.q_type === 'subjective' && <Select value={quizForm.subjective_type} onValueChange={v => setQuizForm({ ...quizForm, subjective_type: v })}><SelectTrigger className="h-10 rounded-xl bg-[#F5F5F7] border-none font-bold text-xs"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="noun">名词解释</SelectItem><SelectItem value="short">简答</SelectItem><SelectItem value="essay">论述</SelectItem></SelectContent></Select>}
                <Select value={quizForm.knowledge_point} onValueChange={v => setQuizForm({ ...quizForm, knowledge_point: v })}><SelectTrigger className="h-10 rounded-xl bg-[#F5F5F7] border-none font-bold text-xs px-4"><SelectValue placeholder="知识点" /></SelectTrigger><SelectContent><SelectItem value="0">不挂载</SelectItem>{kpList.map(kp => <SelectItem key={kp.id} value={kp.id.toString()}>{kp.name}</SelectItem>)}</SelectContent></Select>
                <Select value={quizForm.difficulty_level} onValueChange={v => setQuizForm({ ...quizForm, difficulty_level: v })}><SelectTrigger className="h-10 rounded-xl bg-[#F5F5F7] border-none font-bold text-xs"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="entry">入门</SelectItem><SelectItem value="easy">简单</SelectItem><SelectItem value="normal">适当</SelectItem><SelectItem value="hard">困难</SelectItem><SelectItem value="extreme">极限</SelectItem></SelectContent></Select>
              </div>
              <textarea value={quizForm.text} onChange={e => setQuizForm({ ...quizForm, text: e.target.value })} className="w-full bg-[#F5F5F7] border-none rounded-2xl p-6 min-h-[100px] font-bold text-sm" placeholder="题目文本..." />
              {quizForm.q_type === 'objective' ? (
                <div className="space-y-4"><Label className="text-[11px] font-bold uppercase opacity-40 ml-1">选项</Label><div className="grid grid-cols-2 gap-3">{quizForm.options.map((opt, i) => (<div key={i} className="flex gap-2"><div className="h-10 w-10 rounded-xl bg-black text-white flex items-center justify-center font-bold shrink-0">{String.fromCharCode(65 + i)}</div><Input value={opt} onChange={e => { const no = [...quizForm.options]; no[i] = e.target.value; setQuizForm({ ...quizForm, options: no }); }} className="h-10 rounded-xl bg-[#F5F5F7] border-none font-bold text-xs px-4" /></div>))}</div><Input value={quizForm.answer} onChange={e => setQuizForm({ ...quizForm, answer: e.target.value })} placeholder="正确答案字母" className="h-11 rounded-xl bg-[#F5F5F7] border-none font-bold text-xs px-5" /></div>
              ) : (
                <div className="space-y-4"><textarea value={quizForm.grading_points} onChange={e => setQuizForm({ ...quizForm, grading_points: e.target.value })} className="w-full bg-[#F5F5F7] border-none rounded-xl p-4 min-h-[80px] font-bold text-sm" placeholder="判分点..." /><textarea value={quizForm.answer} onChange={e => setQuizForm({ ...quizForm, answer: e.target.value })} className="w-full bg-[#F5F5F7] border-none rounded-xl p-4 min-h-[80px] font-bold text-sm" placeholder="参考答案..." /></div>
              )}
              <Button onClick={handleCreateQuiz} className="w-full h-14 rounded-2xl bg-black text-white font-bold uppercase text-[11px] tracking-widest">Entry Bank</Button>
            </Card>
            <QuestionBankPanel kpList={kpList} onEdit={q => setEditingItem({ type: 'quizzes', data: { ...q } })} onDelete={id => handleDelete('quizzes/questions', id)} />
          </div>
        </TabsContent>

        <TabsContent value="kp">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            <Card className="lg:col-span-5 p-8 bg-white rounded-3xl border-none shadow-sm space-y-6">
              <div className="flex items-center gap-3"><BrainCircuit className="h-5 w-5 text-purple-600" /><h3 className="text-lg font-bold tracking-tight">建立拓扑节点</h3></div>
              <div className="space-y-1.5"><Label className="text-[11px] font-bold uppercase opacity-40 ml-1">节点名称</Label><Input value={kpForm.name} onChange={e => setKpForm({ ...kpForm, name: e.target.value })} className="bg-[#F5F5F7] border-none h-10 rounded-xl font-bold px-4 text-xs" /></div>
              <div className="space-y-1.5"><Label className="text-[11px] font-bold uppercase opacity-40 ml-1">隶属父级</Label><Select value={kpForm.parent} onValueChange={v => setKpForm({ ...kpForm, parent: v })}><SelectTrigger className="h-10 rounded-xl bg-[#F5F5F7] border-none font-bold text-[11px] px-4"><SelectValue placeholder="顶级节点" /></SelectTrigger><SelectContent>{kpList.map(kp => <SelectItem key={kp.id} value={kp.id.toString()} className="text-xs">{kp.name}</SelectItem>)}</SelectContent></Select></div>
              <textarea value={kpForm.description} onChange={e => setKpForm({ ...kpForm, description: e.target.value })} className="w-full bg-[#F5F5F7] border-none rounded-xl p-4 min-h-[80px] font-bold text-xs" placeholder="描述..." />
              <Button onClick={async () => { try { await api.post('/quizzes/knowledge-points/', { ...kpForm, parent: kpForm.parent === "0" ? null : kpForm.parent }); toast.success("已保存"); setKpForm({ name: '', description: '', parent: '0' }); fetchLists(); } catch (e) { toast.error("失败"); } }} className="w-full h-12 rounded-xl bg-black text-white font-bold text-[11px] uppercase tracking-widest">Save Node</Button>
            </Card>
            <Card className="lg:col-span-7 p-8 bg-[#F5F5F7]/50 rounded-3xl border-none shadow-sm space-y-6">
              <div className="flex items-center justify-between"><h3 className="text-[11px] font-bold uppercase tracking-widest opacity-40">树状结构预览</h3><Button variant="ghost" size="icon" onClick={fetchLists}><RefreshCcw className="w-3.5 h-3.5 opacity-40" /></Button></div>
              <ScrollArea className="h-[500px]"><div className="pr-4">{roots.map(root => (<KPTreeNode key={root.id} node={root} allNodes={kpList} onDelete={id => handleDelete('kp', id)} onEdit={node => setEditingItem({ type: 'kp', data: node })} />))}</div></ScrollArea>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="albums">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
            <Card className="p-10 bg-white rounded-3xl border-none shadow-sm space-y-8">
              <div className="flex items-center gap-3"><Layers className="h-6 w-6 text-emerald-600" /><h3 className="text-xl font-bold tracking-tight">新建课程专辑</h3></div>
              <Input value={albumForm.name} onChange={e => setAlbumForm({ ...albumForm, name: e.target.value })} className="bg-[#F5F5F7] border-none h-12 rounded-xl font-bold px-5" placeholder="专辑名称" />
              <textarea value={albumForm.description} onChange={e => setAlbumForm({ ...albumForm, description: e.target.value })} className="w-full bg-[#F5F5F7] border-none rounded-2xl p-6 min-h-[100px] font-bold text-sm" placeholder="描述..." />
              <div className="relative"><Button variant="outline" className="w-full h-16 rounded-2xl border-dashed border-2 px-6 font-bold"><span>{albumForm.cover ? "封面已就绪" : "上传封面图"}</span><Upload className="w-4 h-4 opacity-20" /></Button><input type="file" onChange={e => setAlbumForm({ ...albumForm, cover: e.target.files?.[0] || null })} className="absolute inset-0 opacity-0 cursor-pointer" accept="image/*" /></div>
              <Button onClick={handleCreateAlbum} className="w-full h-14 rounded-2xl bg-black text-white font-bold uppercase text-xs tracking-widest">Create Album</Button>
            </Card>
            <Card className="p-10 bg-[#F5F5F7]/50 rounded-3xl border-none shadow-sm space-y-6"><h3 className="text-sm font-bold uppercase tracking-widest opacity-40">现有专辑矩阵</h3><ScrollArea className="h-[520px]"><div className="grid gap-3 pr-4">{albumList.map(al => (<div key={al.id} className="p-5 bg-white rounded-2xl flex items-center justify-between group"><p className="text-sm font-bold">{al.name}</p><div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity"><Button onClick={() => setEditingItem({ type: 'albums', data: { ...al } })} variant="ghost" size="icon" className="h-8 w-8 text-blue-600"><Edit3 className="w-3.5 h-3.5" /></Button><Button onClick={() => handleDelete('courses/albums', al.id)} variant="ghost" size="icon" className="h-8 w-8 text-red-500"><Trash2 className="w-3.5 h-3.5" /></Button></div></div>))}</div></ScrollArea></Card>
          </div>
        </TabsContent>

        <TabsContent value="bots">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
            <Card className="p-10 bg-white rounded-3xl border-none shadow-sm space-y-8">
              <div className="flex items-center gap-3"><Bot className="h-6 w-6 text-emerald-600" /><h3 className="text-xl font-bold tracking-tight">部署 AI 助教</h3></div>
              <div className="flex items-center gap-6"><div className="relative group shrink-0"><Avatar className="h-20 w-20 border-4 border-white shadow-xl overflow-hidden">{botForm.avatar ? <AvatarImage src={URL.createObjectURL(botForm.avatar)} /> : <AvatarFallback className="text-[11px] font-bold">INIT</AvatarFallback>}</Avatar><div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity rounded-full flex items-center justify-center cursor-pointer"><Upload className="w-4 h-4 text-white" /><input type="file" onChange={e => setBotForm({ ...botForm, avatar: e.target.files?.[0] || null })} className="absolute inset-0 opacity-0 cursor-pointer" accept="image/*" /></div></div><div className="flex-1 space-y-3"><Label className="text-[11px] font-bold uppercase tracking-widest opacity-40 ml-1">昵称</Label><Input value={botForm.name} onChange={e => setBotForm({ ...botForm, name: e.target.value })} className="bg-[#F5F5F7] border-none h-12 rounded-2xl font-bold px-5" /></div></div>
              <textarea value={botForm.prompt} onChange={e => setBotForm({ ...botForm, prompt: e.target.value })} className="w-full bg-[#F5F5F7] border-none rounded-2xl p-6 min-h-[200px] font-bold text-sm" placeholder="引导词 (Prompt)..." />
              <Button onClick={handleCreateBot} className="w-full h-14 rounded-2xl bg-black text-white font-bold uppercase text-xs tracking-widest">Deploy Bot</Button>
            </Card>
            <Card className="p-10 bg-[#F5F5F7]/50 rounded-3xl border-none shadow-sm space-y-6">
              <h3 className="text-sm font-bold uppercase tracking-widest opacity-40">助教矩阵</h3>
              <ScrollArea className="h-[520px]">
                <div className="grid gap-3 pr-4">
                  {botList.map(b => (
                    <div key={b.id} className="flex items-center justify-between p-5 bg-white rounded-2xl group">
                      <div className="flex items-center gap-4 text-left">
                        <Avatar className="h-10 w-10">
                          <AvatarImage src={b.avatar} />
                          <AvatarFallback>{b.name[0]}</AvatarFallback>
                        </Avatar>
                        <div className="min-w-0">
                          <p className="text-sm font-bold truncate">{b.name}</p>
                          <p className="text-[10px] text-black/35 font-bold truncate">
                            {b.prompt_template_name || 'bots/bot_{id}_prompt.txt'} · {b.prompt_file_exists ? 'FILE OK' : 'FILE MISSING'}
                          </p>
                        </div>
                      </div>
                      <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <Button onClick={() => setEditingItem({ type: 'bots', data: { ...b } })} variant="ghost" size="icon" className="h-8 w-8 text-blue-600"><Edit3 className="w-3.5 h-3.5" /></Button>
                        <Button onClick={() => handleDelete('ai/bots', b.id)} variant="ghost" size="icon" className="h-8 w-8 text-red-500"><Trash2 className="w-3.5 h-3.5" /></Button>
                      </div>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="sm">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
            <Card className="p-10 bg-white rounded-3xl border-none shadow-sm space-y-8">
              <div className="flex items-center gap-3"><Rocket className="h-6 w-6 text-red-600" /><h3 className="text-xl font-bold tracking-tight">上传启动资料</h3></div>
              <Input value={smForm.name} onChange={e => setSmForm({ ...smForm, name: e.target.value })} className="bg-[#F5F5F7] border-none h-12 rounded-xl font-bold px-5" placeholder="资料名称" />
              <textarea value={smForm.description} onChange={e => setSmForm({ ...smForm, description: e.target.value })} className="w-full bg-[#F5F5F7] border-none rounded-2xl p-6 min-h-[100px] font-bold text-sm" placeholder="简介..." />
              <div className="relative"><Button variant="outline" className="w-full h-16 rounded-2xl border-dashed border-2 px-6 font-bold"><span>{smForm.file ? smForm.file.name : '上传文件'}</span><Upload className="w-4 h-4 opacity-20" /></Button><input type="file" onChange={e => setSmForm({ ...smForm, file: e.target.files?.[0] || null })} className="absolute inset-0 opacity-0 cursor-pointer" /></div>
              <Button onClick={handleCreateSM} disabled={isSubmitting} className="w-full bg-black text-white h-14 rounded-2xl font-bold text-xs tracking-widest uppercase">Upload Material</Button>
            </Card>
            <Card className="p-10 bg-[#F5F5F7]/50 rounded-3xl border-none shadow-sm space-y-6"><h3 className="text-sm font-bold uppercase tracking-widest opacity-40">已存资料</h3><ScrollArea className="h-[520px]"><div className="grid gap-3 pr-4">{smList.map(sm => (<div key={sm.id} className="p-5 bg-white rounded-2xl flex items-center justify-between group"><p className="text-sm font-bold">{sm.name}</p><div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity"><Button onClick={() => setEditingItem({ type: 'sm', data: { ...sm } })} variant="ghost" size="icon" className="h-8 w-8 text-blue-600"><Edit3 className="w-3.5 h-3.5" /></Button><Button onClick={() => handleDelete('sm', sm.id)} variant="ghost" size="icon" className="h-8 w-8 text-red-500"><Trash2 className="w-3.5 h-3.5" /></Button></div></div>))}</div></ScrollArea></Card>
          </div>
        </TabsContent>

        <TabsContent value="notifications">
          <Card className="max-w-2xl mx-auto p-10 bg-white rounded-[2rem] border-none shadow-sm space-y-8">
            <div className="flex items-center gap-3"><Bell className="h-6 w-6 text-indigo-600" /><h3 className="text-xl font-bold tracking-tight">全站广播</h3></div>
            <div className="space-y-6">
              <Input value={notifForm.title} onChange={e => setNotifForm({ ...notifForm, title: e.target.value })} placeholder="通知标题" className="bg-[#F5F5F7] border-none h-12 rounded-xl font-bold px-5" />
              <textarea value={notifForm.content} onChange={e => setNotifForm({ ...notifForm, content: e.target.value })} placeholder="内容内容 (50字以内)..." className="w-full bg-[#F5F5F7] border-none rounded-2xl p-6 min-h-[120px] font-bold text-sm" />
              <Button onClick={handleBroadcast} disabled={isSendingNotif} className="w-full h-14 rounded-2xl bg-black text-white font-bold uppercase text-xs tracking-widest gap-2">{isSendingNotif ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />} 发送广播</Button>
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="membership">
          <MembershipPanel codes={codes} newCodeCount={newCodeCount} setNewCodeCount={setNewCodeCount} isGeneratingCodes={isGeneratingCodes} handleGenerateCodes={handleGenerateCodes} handleDeleteCode={handleDeleteCode} fetchCodes={fetchCodes} />
        </TabsContent>

        <TabsContent value="insights">
          <InsightsPanel biData={biData} isLoadingBI={isLoadingBI} fetchBI={fetchBI} />
        </TabsContent>

        <TabsContent value="manage">
          <AuditPanel auditMode={auditMode} setAuditMode={setAuditMode} qSearch={qSearch} setQSearch={setQSearch} fetchLists={fetchLists} courseList={courseList} articleList={articleList} kpList={kpList} smList={smList} onEdit={(type, data) => setEditingItem({ type, data })} onDelete={handleDelete} />
        </TabsContent>

        <TabsContent value="pipeline">
          <PipelinePanel />
        </TabsContent>

        <TabsContent value="prompts">
          <PromptTemplatesPanel />
        </TabsContent>
      </Tabs>

      {/* --- Dialogs --- */}
      <Dialog open={!!editingItem} onOpenChange={open => !open && setEditingItem(null)}>
        <DialogContent className="sm:max-w-[850px] max-h-[90vh] overflow-y-auto rounded-[3rem] p-10 border-none shadow-2xl text-left bg-white">
          <DialogHeader className="text-left"><DialogTitle className="text-xl font-bold">属性核心配置</DialogTitle></DialogHeader>
          <div className="space-y-6 pt-6">
            {editingItem?.type === 'courses' && (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1.5"><Label className="text-[11px] font-bold uppercase opacity-40">标题</Label><Input value={editingItem.data.title} onChange={e => setEditingItem({ ...editingItem, data: { ...editingItem.data, title: e.target.value } })} className="rounded-xl bg-slate-50 border-none h-10 text-xs font-bold" /></div>
                  <div className="space-y-1.5"><Label className="text-[11px] font-bold uppercase opacity-40">ELO 奖励</Label><Input type="number" value={editingItem.data.elo_reward} onChange={e => setEditingItem({ ...editingItem, data: { ...editingItem.data, elo_reward: e.target.value } })} className="rounded-xl bg-slate-50 border-none h-10 text-xs font-bold" /></div>
                </div>
                <MarkdownEditor content={editingItem.data.description} onChange={v => setEditingItem({ ...editingItem, data: { ...editingItem.data, description: v } })} />
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1.5"><Label className="text-[11px] font-bold uppercase opacity-40 text-emerald-600">更新视频</Label><Input type="file" onChange={e => setEditingItem({ ...editingItem, data: { ...editingItem.data, video_file: e.target.files?.[0] } })} className="rounded-xl h-10 bg-slate-50 text-[11px]" /></div>
                  <div className="space-y-1.5"><Label className="text-[11px] font-bold uppercase opacity-40 text-blue-600">更新封面</Label><Input type="file" onChange={e => setEditingItem({ ...editingItem, data: { ...editingItem.data, cover_image: e.target.files?.[0] } })} className="rounded-xl h-10 bg-slate-50 text-[11px]" /></div>
                </div>
              </div>
            )}
            {editingItem?.type === 'articles' && (
              <div className="space-y-4">
                <Input value={editingItem.data.title} onChange={e => setEditingItem({ ...editingItem, data: { ...editingItem.data, title: e.target.value } })} className="rounded-xl bg-[#F5F5F7] border-none h-14 text-2xl font-black px-5" />
                <div className="grid grid-cols-2 gap-4">
                  <Input value={editingItem.data.author_display_name} onChange={e => setEditingItem({ ...editingItem, data: { ...editingItem.data, author_display_name: e.target.value } })} className="rounded-xl bg-slate-50 border-none h-10 text-xs font-bold" placeholder="署名" />
                  <Select value={editingItem.data.knowledge_point || "0"} onValueChange={v => setEditingItem({ ...editingItem, data: { ...editingItem.data, knowledge_point: v } })}><SelectTrigger className="h-10 rounded-xl bg-slate-50 border-none font-bold text-xs"><SelectValue /></SelectTrigger><SelectContent>{kpList.map(kp => <SelectItem key={kp.id} value={kp.id.toString()}>{kp.name}</SelectItem>)}</SelectContent></Select>
                </div>
                <TagInput tags={editingItem.data.tags || []} setTags={t => setEditingItem({ ...editingItem, data: { ...editingItem.data, tags: t } })} compact />
                <MarkdownEditor content={editingItem.data.content} onChange={v => setEditingItem({ ...editingItem, data: { ...editingItem.data, content: v } })} />
              </div>
            )}
            {editingItem?.type === 'bots' && (
              <div className="space-y-4">
                <div className="flex items-center justify-between gap-4"><Input value={editingItem.data.name} onChange={e => setEditingItem({ ...editingItem, data: { ...editingItem.data, name: e.target.value } })} className="rounded-xl bg-slate-50 border-none h-10 text-xs font-bold" /><div className="flex items-center gap-2 pt-4"><input type="checkbox" checked={editingItem.data.is_exclusive} onChange={e => setEditingItem({ ...editingItem, data: { ...editingItem.data, is_exclusive: e.target.checked } })} /><Label className="text-[11px] font-bold text-emerald-600">专属导师权限</Label></div></div>
                <Input value={editingItem.data.prompt_template_name || ''} readOnly className="rounded-xl bg-emerald-50/70 border-none h-10 text-[11px] font-bold text-emerald-700" />
                <textarea value={editingItem.data.system_prompt} onChange={e => setEditingItem({ ...editingItem, data: { ...editingItem.data, system_prompt: e.target.value } })} className="w-full min-h-[300px] p-4 rounded-xl bg-slate-50 border-none text-xs" />
              </div>
            )}
            {editingItem?.type === 'quizzes' && (
              <div className="space-y-4">
                <textarea value={editingItem.data.text} onChange={e => setEditingItem({ ...editingItem, data: { ...editingItem.data, text: e.target.value } })} className="w-full p-4 rounded-xl bg-slate-50 border-none text-xs font-bold min-h-[80px]" />
                <div className="grid grid-cols-2 gap-4">
                  <Select value={editingItem.data.knowledge_point || "0"} onValueChange={v => setEditingItem({ ...editingItem, data: { ...editingItem.data, knowledge_point: v } })}><SelectTrigger className="h-10 rounded-xl bg-slate-50 border-none font-bold text-xs"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="0">不挂载</SelectItem>{kpList.map(kp => <SelectItem key={kp.id} value={kp.id.toString()}>{kp.name}</SelectItem>)}</SelectContent></Select>
                  <Select value={editingItem.data.difficulty_level || "normal"} onValueChange={v => setEditingItem({ ...editingItem, data: { ...editingItem.data, difficulty_level: v } })}><SelectTrigger className="h-10 rounded-xl bg-slate-50 border-none font-bold text-xs"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="entry">入门</SelectItem><SelectItem value="easy">简单</SelectItem><SelectItem value="normal">适当</SelectItem><SelectItem value="hard">困难</SelectItem><SelectItem value="extreme">极限</SelectItem></SelectContent></Select>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <textarea value={editingItem.data.grading_points} onChange={e => setEditingItem({ ...editingItem, data: { ...editingItem.data, grading_points: e.target.value } })} className="w-full p-4 rounded-xl bg-slate-50 border-none text-[11px] h-24" placeholder="判分点" />
                  <textarea value={editingItem.data.correct_answer} onChange={e => setEditingItem({ ...editingItem, data: { ...editingItem.data, correct_answer: e.target.value } })} className="w-full p-4 rounded-xl bg-slate-50 border-none text-[11px] h-24" placeholder="答案" />
                </div>
              </div>
            )}
            <Button onClick={handleSaveEdit} className="w-full h-12 bg-black text-white rounded-xl font-bold text-[11px] uppercase tracking-widest">Update & Sync</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Dynamic KP Dialog & AI Workstation Dialog omitted for brevity but they are similar refactored blocks */}
      {/* ... (Keep AI Workstation and NewKPDialog as they were but clean) */}
      <Dialog open={showNewKPDialog} onOpenChange={setShowNewKPDialog}>
        <DialogContent className="sm:max-w-[500px] rounded-[2.5rem] p-10 border-none shadow-2xl bg-white text-left">
          <DialogHeader><DialogTitle className="text-xl font-black flex items-center gap-3"><BrainCircuit className="text-indigo-600 w-5 h-5" /> 快速新建知识点</DialogTitle></DialogHeader>
          <div className="space-y-5 pt-6">
            <div className="space-y-1.5"><Label className="text-[11px] font-bold uppercase opacity-40">节点名称</Label><Input value={newKPForm.name} onChange={e => setNewKPForm({ ...newKPForm, name: e.target.value })} placeholder="例如：博弈论基础" className="bg-[#F5F5F7] border-none h-11 rounded-xl font-bold px-4 text-sm" /></div>
            <div className="space-y-1.5"><Label className="text-[11px] font-bold uppercase opacity-40">隶属父级</Label><Select value={newKPForm.parent} onValueChange={v => setNewKPForm({ ...newKPForm, parent: v })}><SelectTrigger className="h-11 rounded-xl bg-[#F5F5F7] border-none font-bold text-xs px-4"><SelectValue placeholder="顶级节点" /></SelectTrigger><SelectContent>{kpList.map(kp => <SelectItem key={kp.id} value={kp.id.toString()} className="text-xs">{kp.name}</SelectItem>)}</SelectContent></Select></div>
            <textarea value={newKPForm.description} onChange={e => setNewKPForm({ ...newKPForm, description: e.target.value })} className="w-full bg-[#F5F5F7] border-none rounded-xl p-4 min-h-[100px] font-bold text-xs" placeholder="描述..." />
            <div className="flex gap-3 pt-2"><Button variant="outline" onClick={() => setShowNewKPDialog(false)} className="flex-1 h-12 rounded-xl font-bold text-xs">取消</Button><Button onClick={handleQuickCreateKP} className="flex-[2] h-12 rounded-xl bg-black text-white font-black shadow-xl text-xs uppercase tracking-widest">确认保存</Button></div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={showAIWorkstation} onOpenChange={setShowAIWorkstation}>
        <DialogContent className="sm:max-w-[1000px] rounded-[3rem] p-10 border-none shadow-2xl bg-white text-left overflow-hidden">
          <DialogHeader><DialogTitle className="text-xl font-bold flex items-center gap-3"><Sparkles className="text-emerald-500" /> AI 题目作业中心</DialogTitle></DialogHeader>
          <div className="space-y-6 pt-6">
            {!aiPreviewData ? (
              <div className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-12 gap-6 items-start">
                  <div className="md:col-span-8"><textarea value={aiInputText} onChange={e => setAiInputText(e.target.value)} className="w-full bg-[#F5F5F7] border-none rounded-[2rem] p-8 min-h-[350px] font-medium text-sm" placeholder="在此粘贴 5 万字以内的学术语料..." /></div>
                  <div className="md:col-span-4 space-y-4">
                    <div className="p-8 border-2 border-dashed border-black/10 rounded-[2rem] bg-slate-50 flex flex-col items-center justify-center text-center space-y-4 relative group hover:border-emerald-500/50 transition-all">
                      <div className="h-14 w-14 rounded-2xl bg-white shadow-sm flex items-center justify-center"><FileUp className="h-6 w-6 opacity-40 group-hover:text-emerald-500 transition-colors" /></div>
                      <div><p className="text-[11px] font-bold">拖动 Word 文件至此</p><p className="text-[11px] text-black/30 font-medium mt-1 uppercase">Supports .docx / .txt</p></div>
                      {aiFile && <Badge className="bg-emerald-500 text-white border-none">{aiFile.name}</Badge>}<input type="file" onChange={e => setAiFile(e.target.files?.[0] || null)} className="absolute inset-0 opacity-0 cursor-pointer" accept=".docx,.txt" />
                    </div>
                    <Card className="p-6 border-none bg-emerald-50/50 rounded-[1.5rem] space-y-2"><h5 className="text-[11px] font-bold text-emerald-700 uppercase tracking-widest flex items-center gap-2"><Sparkles className="w-3 h-3" /> 智能解析建议</h5><p className="text-[11px] text-emerald-900/60 font-medium leading-relaxed">对于超长文本，AI 将自动启动分片引擎并行作业。</p></Card>
                  </div>
                </div>
                <Button onClick={handleAIParse} disabled={isParsing} className="w-full h-14 rounded-2xl bg-black text-white font-bold shadow-xl transition-all hover:scale-[1.01]">{isParsing ? <><RefreshCcw className="mr-2 h-4 w-4 animate-spin" /> {parseProgress || 'AI 深度整理中...'}</> : "开始 AI 自动整理"}</Button>
              </div>
            ) : (
              <div className="space-y-6">
                <ScrollArea className="h-[450px] border rounded-[2rem] bg-slate-50/50 p-6 text-left">
                  <div className="space-y-4">{aiPreviewData.map((q, i) => (<Card key={i} className="p-5 bg-white rounded-2xl border-none shadow-sm space-y-3"><div className="flex justify-between items-start"><Badge className="bg-black text-white text-[11px]">{q.q_type}</Badge><Button variant="ghost" size="icon" onClick={() => setAiPreviewData(aiPreviewData.filter((_, idx) => idx !== i))} className="h-6 w-6 text-red-500"><X className="w-3 h-3" /></Button></div><textarea value={q.text} onChange={e => { const nd = [...aiPreviewData]; nd[i].text = e.target.value; setAiPreviewData(nd); }} className="w-full bg-[#F5F5F7] border-none rounded-xl p-3 text-xs font-bold min-h-[60px]" /><div className="grid grid-cols-2 gap-3 text-left"><div className="space-y-1.5"><Label className="text-[11px] uppercase opacity-40">答案</Label><textarea value={q.correct_answer} onChange={e => { const nd = [...aiPreviewData]; nd[i].correct_answer = e.target.value; setAiPreviewData(nd); }} className="w-full bg-[#F5F5F7] border-none rounded-lg p-2 text-[11px]" /></div><div className="space-y-1.5"><Label className="text-[11px] uppercase opacity-40">得分点/解析</Label><textarea value={q.grading_points || q.analysis} onChange={e => { const nd = [...aiPreviewData]; nd[i].grading_points = e.target.value; setAiPreviewData(nd); }} className="w-full bg-[#F5F5F7] border-none rounded-lg p-2 text-[11px]" /></div></div></Card>))}</div>
                </ScrollArea>
                <div className="grid grid-cols-2 gap-4 items-end">
                  <div className="space-y-2 text-left"><Label className="text-[11px] font-bold uppercase tracking-widest opacity-40 ml-1">批量挂载知识点</Label><Select value={aiTargetKP} onValueChange={setAiTargetKP}><SelectTrigger className="h-12 rounded-2xl bg-[#F5F5F7] border-none font-bold px-5 text-xs"><SelectValue placeholder="选择知识点" /></SelectTrigger><SelectContent>{kpList.map(kp => <SelectItem key={kp.id} value={kp.id.toString()}>{kp.name}</SelectItem>)}</SelectContent></Select></div>
                  <div className="flex gap-2"><Button variant="outline" onClick={() => setAiPreviewData(null)} className="flex-1 h-12 rounded-xl font-bold text-xs">取消重来</Button><Button onClick={handleAIImport} className="flex-[2] h-12 rounded-xl bg-emerald-500 text-white font-bold shadow-xl text-xs gap-2"><CheckCircle2 className="w-4 h-4" /> 确认导入</Button></div>
                </div>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {isSubmitting && (<div className="fixed bottom-10 right-10 z-[100]"><Card className="border-none shadow-2xl rounded-3xl bg-white p-6 w-80 flex items-center gap-5"><div className="relative h-12 w-12 shrink-0"><svg className="h-full w-full -rotate-90"><circle cx="24" cy="24" r="20" stroke="currentColor" strokeWidth="4" fill="transparent" className="text-slate-100" /><circle cx="24" cy="24" r="20" stroke="currentColor" strokeWidth="4" fill="transparent" strokeDasharray="125.6" strokeDashoffset={125.6 - (125.6 * uploadProgress) / 100} className="text-black transition-all duration-500" strokeLinecap="round" /></svg><div className="absolute inset-0 flex items-center justify-center text-[11px] font-bold">{uploadProgress}%</div></div><p className="text-xs font-bold text-[#1D1D1F]">资源同步中...</p></Card></div>)}
    </div>
  );
};
