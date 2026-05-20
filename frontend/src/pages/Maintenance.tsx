import React, { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  BookOpen, FileText, Target, Video, Image as ImageIcon,
  Upload, Trash2, Edit3, Settings2, Bot, Sparkles, Bell, Send, Loader2,
  BrainCircuit, Layers, FileUp, Rocket, BarChart3
} from 'lucide-react';
import api from '@/lib/api';
import { createCourseWithSmartUpload } from '@/lib/chunkedUpload';
import { useUploadStore } from '@/store/useUploadStore';
import { toast } from 'sonner';
import { useAuthStore } from '@/store/useAuthStore';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ScrollArea } from '@/components/ui/scroll-area';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";

import { cn } from '@/lib/utils';
import { MarkdownEditor } from '@/components/MarkdownEditor';

// Sub-components
import { TagInput } from './maintenance/MaintenanceComponents';
import { QuestionBankPanel } from './maintenance/QuestionBankPanel';
import { InsightsPanel } from './maintenance/InsightsPanel';
import { AuditPanel } from './maintenance/AuditPanel';
import { PipelinePanel } from './maintenance/PipelinePanel';
import { KnowledgeSystemPanel } from './maintenance/KnowledgeSystemPanel';

export const Maintenance: React.FC = () => {
  const { t } = useTranslation('maintenance');
  const CHUNKED_UPLOAD_THRESHOLD_BYTES = 100 * 1024 * 1024;
  const CHUNK_SIZE_BYTES = 10 * 1024 * 1024;
  const [isCourseSubmitting, setIsCourseSubmitting] = useState(false);
  const [isSMSubmitting, setIsSMSubmitting] = useState(false);

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

  // Quick Create Logic
  const [showNewKPDialog, setShowNewKPDialog] = useState(false);
  const [showNewAlbumDialog, setShowNewAlbumDialog] = useState(false);
  const [newAlbumName, setNewAlbumName] = useState('');
  const [newAlbumDesc, setNewAlbumDesc] = useState('');
  const [newKPForm, setNewKPForm] = useState({ name: '', description: '', parent: '0' });
  const [kpCreationTarget, setKPCreationTarget] = useState<'course' | 'article' | 'none'>('course');

  // Forms
  const [courseForm, setCourseForm] = useState({ title: '', album_obj: '0', desc: '', elo_reward: 50, knowledge_point: '0', video: null as File | null, cover: null as File | null, courseware: null as File | null });
  const [articleForm, setArticleForm] = useState({ title: '', content: '', author_display_name: '', tags: [] as string[], knowledge_point: '0' });
  const [botForm, setBotForm] = useState({ name: '', prompt: '', avatar: null as File | null, is_exclusive: false });
  const [albumForm, setAlbumForm] = useState({ name: '', description: '', cover: null as File | null });
  const [quizForm, setQuizForm] = useState({ text: '', q_type: 'objective', subjective_type: 'noun', grading_points: '', knowledge_point: '0', options: ['', '', '', ''], answer: '', difficulty_level: 'normal' });
  const [smForm, setSmForm] = useState({ name: '', description: '', file: null as File | null });
  const [notifForm, setNotifForm] = useState({ title: '', content: '', link: '' });
  const [isSendingNotif, setIsSendingNotif] = useState(false);

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

  const { user } = useAuthStore();

  const fetchBI = async () => {
    setIsLoadingBI(true);
    try { const res = await api.get('/users/admin/bi/'); setBIData(res.data); } catch (e) { toast.error(t('commonActions.biLoadFailed')); }
    finally { setIsLoadingBI(false); }
  };

  useEffect(() => { fetchLists(); fetchBI(); }, []);

  const handleDelete = async (type: string, id: number) => {
    try {
      let endpoint = `/${type}/${id}/`;
      if (type === 'kp') endpoint = `/quizzes/knowledge-points/${id}/`;
      if (type === 'quizzes') endpoint = `/quizzes/questions/${id}/`;
      if (type === 'sm') endpoint = `/courses/startup-materials/${id}/`;
      await api.delete(endpoint);
      toast.success(t('commonActions.removed')); fetchLists();
    } catch (e) { toast.error(t('commonActions.deleteFailed')); }
  };

  const handleCreateCourse = async () => {
    if (!courseForm.title || !courseForm.video) return toast.error(t('course.coreInfoIncomplete'));
    setIsCourseSubmitting(true);

    // 先捕获表单值，清空表单让用户立即准备下一个
    const file = courseForm.video;
    const title = courseForm.title;
    const desc = courseForm.desc;
    const eloReward = courseForm.elo_reward;
    const albumObj = courseForm.album_obj;
    const knowledgePoint = courseForm.knowledge_point;
    const cover = courseForm.cover;
    const courseware = courseForm.courseware;

    const controller = new AbortController();
    const uploadId = `${Date.now()}-${file.name}`;

    const { addTask, updateProgress, setStatus } = useUploadStore.getState();
    addTask({ id: uploadId, fileName: file.name, progress: 0, status: 'uploading', controller });

    setCourseForm({ title: '', album_obj: '0', desc: '', elo_reward: 50, knowledge_point: '0', video: null, cover: null, courseware: null });
    setIsCourseSubmitting(false);

    try {
      await createCourseWithSmartUpload({
        title,
        description: desc,
        eloReward,
        albumObj: albumObj !== '0' ? albumObj : undefined,
        knowledgePoint: knowledgePoint !== '0' ? knowledgePoint : undefined,
        video: file,
        cover,
        courseware,
        thresholdBytes: CHUNKED_UPLOAD_THRESHOLD_BYTES,
        chunkSizeBytes: CHUNK_SIZE_BYTES,
        signal: controller.signal,
        onProgress: (p) => {
          updateProgress(uploadId, p);
          if (p >= 95) setStatus(uploadId, 'processing');
        },
      });

      setStatus(uploadId, 'completed');
      toast.success(t('course.coursePublished'));
      fetchLists();
    } catch (e: any) {
      if (e?.name === 'AbortError' || e?.code === 'ERR_CANCELED') {
        // User cancelled — status already set by cancelTask
      } else {
        const status = e?.response?.status;
        const detail = e?.response?.data?.detail || e?.response?.data?.error || e?.response?.data?.message;
        if (status === 403) toast.error(t('course.noAdminPermission'));
        else if (typeof detail === 'string' && detail.trim()) toast.error(detail);
        else toast.error(t('course.publishFailed'));
        setStatus(uploadId, 'failed', t('course.publishFailed'));
      }
    }
  };

  const handleVideoFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    if (!file) return setCourseForm({ ...courseForm, video: null });
    if (file.size > CHUNKED_UPLOAD_THRESHOLD_BYTES) toast.message(t('course.largeFileNotice'));
    setCourseForm({ ...courseForm, video: file });
  };

  const handleCreateQuiz = async () => {
    if (!quizForm.text) return toast.error(t('quiz.questionMissing'));
    try {
      await api.post('/quizzes/questions/', {
        text: quizForm.text, q_type: quizForm.q_type, subjective_type: quizForm.subjective_type,
        grading_points: quizForm.grading_points, knowledge_point: quizForm.knowledge_point === "0" ? null : quizForm.knowledge_point,
        options: quizForm.q_type === 'objective' ? quizForm.options : null, correct_answer: quizForm.answer,
        difficulty_level: quizForm.difficulty_level
      });
      toast.success(t('quiz.questionStored')); fetchLists();
    } catch (e) { toast.error(t('quiz.storeFailed')); }
  };

  const handleCreateBot = async () => {
    if (!botForm.name || !botForm.prompt) return toast.error(t('bot.infoIncomplete'));
    const fd = new FormData(); fd.append('name', botForm.name); fd.append('system_prompt', botForm.prompt); fd.append('is_exclusive', String(botForm.is_exclusive)); if (botForm.avatar) fd.append('avatar', botForm.avatar);
    try {
      const res = await api.post('/ai/bots/', fd);
      const templateName = res.data?.prompt_template_name;
      toast.success(templateName ? t('bot.assistantOnline') + '，Prompt: ' + templateName : t('bot.assistantOnline'));
      setBotForm({ name: '', prompt: '', avatar: null, is_exclusive: false });
      fetchLists();
    }
    catch (e) { toast.error(t('bot.publishFailed')); }
  };

  const handleCreateAlbum = async () => {
    if (!albumForm.name) return toast.error(t('album.nameRequired'));
    const fd = new FormData(); fd.append('name', albumForm.name); fd.append('description', albumForm.description); if (albumForm.cover) fd.append('cover_image', albumForm.cover);
    try { await api.post('/courses/albums/', fd); toast.success(t('album.albumCreated')); setAlbumForm({ name: '', description: '', cover: null }); fetchLists(); }
    catch (e) { toast.error(t('album.failed')); }
  };

  const handleCreateSM = async () => {
    if (!smForm.name || !smForm.file) return toast.error(t('startupMaterial.infoIncomplete'));
    setIsSMSubmitting(true);

    const file = smForm.file;
    const name = smForm.name;
    const description = smForm.description;

    const controller = new AbortController();
    const uploadId = `${Date.now()}-${file.name}`;
    const { addTask, updateProgress, setStatus } = useUploadStore.getState();
    addTask({ id: uploadId, fileName: file.name, progress: 0, status: 'uploading', controller });

    setSmForm({ name: '', description: '', file: null });
    setIsSMSubmitting(false);

    const fd = new FormData(); fd.append('name', name); fd.append('description', description); fd.append('file', file);
    try {
      await api.post('/courses/startup-materials/', fd, {
        signal: controller.signal,
        onUploadProgress: p => {
          if (p.total) updateProgress(uploadId, Math.round((p.loaded / p.total) * 100));
        },
      });
      setStatus(uploadId, 'completed');
      toast.success(t('startupMaterial.materialUploaded'));
      fetchLists();
    } catch (e: any) {
      if (e?.name !== 'AbortError' && e?.code !== 'ERR_CANCELED') {
        toast.error(t('startupMaterial.uploadFailed'));
        setStatus(uploadId, 'failed', t('startupMaterial.uploadFailed'));
      }
    }
  };

  const handleBroadcast = async () => {
    if (!notifForm.title || !notifForm.content) return toast.error(t('notification.contentRequired'));
    setIsSendingNotif(true);
    try { await api.post('/notifications/broadcast/', notifForm); toast.success(t('notification.notificationSent')); setNotifForm({ title: '', content: '', link: '' }); }
    catch (e) { toast.error(t('notification.sendFailed')); } finally { setIsSendingNotif(false); }
  };

  const handleQuickCreateKP = async () => {
    if (!newKPForm.name) return toast.error(t('quickCreate.nameRequired'));
    try {
      const res = await api.post('/quizzes/knowledge-points/', { ...newKPForm, parent: newKPForm.parent === "0" ? null : newKPForm.parent });
      const newKPId = res.data.id.toString(); await fetchLists();
      if (kpCreationTarget === 'course') setCourseForm(prev => ({ ...prev, knowledge_point: newKPId }));
      else if (kpCreationTarget === 'article') setArticleForm(prev => ({ ...prev, knowledge_point: newKPId }));
      setShowNewKPDialog(false); setNewKPForm({ name: '', description: '', parent: '0' });
    } catch (e) { toast.error(t('quickCreate.createFailed')); }
  };

  const handleQuickCreateAlbum = async () => {
    if (!newAlbumName.trim()) return toast.error(t('quickCreate.nameRequired'));
    try {
      const res = await api.post('/courses/albums/', { name: newAlbumName.trim(), description: newAlbumDesc.trim() });
      const newId = res.data.id.toString();
      await fetchLists();
      setCourseForm(prev => ({ ...prev, album_obj: newId }));
      setShowNewAlbumDialog(false); setNewAlbumName(''); setNewAlbumDesc('');
      toast.success(t('album.albumCreated'));
    } catch (e) { toast.error(t('quickCreate.createFailed')); }
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
      toast.success(t('commonActions.coreConfigSynced')); setEditingItem(null); fetchLists();
    } catch (e: any) { toast.error(t('commonActions.updateFailed')); }
  };

  return (
    <div className="p-6 space-y-6 animate-in fade-in duration-500 max-w-[1600px] mx-auto overflow-hidden text-left">

      <Tabs defaultValue="courses" className="space-y-6">
        <TabsList className="bg-white/50 backdrop-blur-md p-1.5 rounded-2xl border border-black/5 h-auto flex flex-wrap gap-1.5 shadow-sm w-fit mx-auto">
          <TabsTrigger value="courses" className="rounded-xl px-4 py-2 text-[11px] font-bold uppercase"><BookOpen className="w-3.5 h-3.5 mr-2" />{t('tabs.courseUpload')}</TabsTrigger>
          <TabsTrigger value="articles" className="rounded-xl px-4 py-2 text-[11px] font-bold uppercase"><FileText className="w-3.5 h-3.5 mr-2" />{t('tabs.publishArticle')}</TabsTrigger>
          <TabsTrigger value="quizzes" className="rounded-xl px-4 py-2 text-[11px] font-bold uppercase"><Target className="w-3.5 h-3.5 mr-2" />{t('tabs.questionBank')}</TabsTrigger>
          <TabsTrigger value="kp" className="rounded-xl px-4 py-2 text-[11px] font-bold uppercase"><BrainCircuit className="w-3.5 h-3.5 mr-2" />{t('tabs.knowledgeSystem')}</TabsTrigger>
          <TabsTrigger value="albums" className="rounded-xl px-4 py-2 text-[11px] font-bold uppercase"><Layers className="w-3.5 h-3.5 mr-2" />{t('tabs.albumManager')}</TabsTrigger>
          <TabsTrigger value="bots" className="rounded-xl px-4 py-2 text-[11px] font-bold uppercase"><Bot className="w-3.5 h-3.5 mr-2" />{t('tabs.aiBot')}</TabsTrigger>
          <TabsTrigger value="sm" className="rounded-xl px-4 py-2 text-[11px] font-bold uppercase"><Rocket className="w-3.5 h-3.5 mr-2" />{t('tabs.startupMaterials')}</TabsTrigger>
          <TabsTrigger value="notifications" className="rounded-xl px-4 py-2 text-[11px] font-bold uppercase"><Bell className="w-3.5 h-3.5 mr-2" />{t('tabs.siteBroadcast')}</TabsTrigger>
          <TabsTrigger value="insights" className="rounded-xl px-4 py-2 text-[11px] font-bold uppercase"><BarChart3 className="w-3.5 h-3.5 mr-2" />{t('tabs.insights')}</TabsTrigger>
          <TabsTrigger value="manage" className="rounded-xl px-4 py-2 text-[11px] font-bold uppercase"><Settings2 className="w-3.5 h-3.5 mr-2" />{t('tabs.audit')}</TabsTrigger>
          <TabsTrigger value="pipeline" className="rounded-xl px-4 py-2 text-[11px] font-bold uppercase"><Sparkles className="w-3.5 h-3.5 mr-2" />{t('tabs.aiPipeline')}</TabsTrigger>
        </TabsList>

        <TabsContent value="courses">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <Card className="lg:col-span-8 p-8 bg-white rounded-3xl border-none shadow-sm space-y-6">
              <div className="space-y-2.5"><Label className="text-[11px] font-bold uppercase opacity-40 ml-1">{t('course.title')}</Label><Input value={courseForm.title} onChange={e => setCourseForm({ ...courseForm, title: e.target.value })} className="bg-unimind-bg-secondary border-none h-12 rounded-xl font-bold px-5" /></div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2"><Label className="text-[11px] font-bold uppercase opacity-40 ml-1">{t('course.album')}</Label><Select value={courseForm.album_obj} onValueChange={v => v === 'NEW_ALBUM' ? setShowNewAlbumDialog(true) : setCourseForm({ ...courseForm, album_obj: v })}><SelectTrigger className="h-10 rounded-xl bg-unimind-bg-secondary border-none font-bold px-4 text-xs"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="0">{t('course.noAlbum')}</SelectItem><SelectItem value="NEW_ALBUM" className="text-indigo-600 font-bold">{t('course.newAlbum')}</SelectItem>{albumList.map(al => <SelectItem key={al.id} value={al.id.toString()}>{al.name}</SelectItem>)}</SelectContent></Select></div>
                <div className="space-y-2"><Label className="text-[11px] font-bold uppercase opacity-40 ml-1">{t('course.knowledgePoint')}</Label><Select value={courseForm.knowledge_point} onValueChange={v => v === 'NEW_KP' ? (setKPCreationTarget('course'), setShowNewKPDialog(true)) : setCourseForm({ ...courseForm, knowledge_point: v })}><SelectTrigger className="h-10 rounded-xl bg-unimind-bg-secondary border-none font-bold px-4 text-xs"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="0">{t('course.noAlbum')}</SelectItem><SelectItem value="NEW_KP" className="text-indigo-600 font-bold">{t('course.newKnowledgePoint')}</SelectItem>{kpList.map(kp => <SelectItem key={kp.id} value={kp.id.toString()}>{kp.name}</SelectItem>)}</SelectContent></Select></div>
              </div>
              <div className="space-y-2"><Label className="text-[11px] font-bold uppercase opacity-40 ml-1">{t('course.description')}</Label><MarkdownEditor content={courseForm.desc} onChange={v => setCourseForm({ ...courseForm, desc: v })} /></div>
            </Card>
            <Card className="lg:col-span-4 p-8 bg-white rounded-3xl border-none shadow-sm space-y-6">
              <div className="space-y-3"><Label className="text-[11px] font-bold uppercase opacity-40">{t('course.rewardSetting')}</Label><div className="flex items-center gap-3"><Input type="number" value={courseForm.elo_reward} onChange={e => setCourseForm({ ...courseForm, elo_reward: parseInt(e.target.value) || 0 })} className="bg-unimind-bg-secondary border-none h-10 rounded-xl font-bold w-20 text-center" /><span className="text-[11px] font-bold opacity-40 uppercase">ELO Reward</span></div></div>
              <div className="space-y-4"><Label className="text-[11px] font-bold uppercase opacity-40">{t('course.mediaAttachment')}</Label>
                <div className="relative"><Button variant="outline" className="w-full h-12 rounded-xl border-dashed border-2 px-4 font-bold text-[11px]"><span>{t(courseForm.video ? 'course.videoReady' : 'course.uploadVideo')}</span><Video className="w-4 h-4 opacity-20" /></Button><input type="file" onChange={handleVideoFileChange} className="absolute inset-0 opacity-0 cursor-pointer" accept="video/*" /></div>
                <div className="relative"><Button variant="outline" className="w-full h-12 rounded-xl border-dashed border-2 px-4 font-bold text-[11px]"><span>{t(courseForm.cover ? 'course.coverReady' : 'course.uploadCover')}</span><ImageIcon className="w-4 h-4 opacity-20" /></Button><input type="file" onChange={e => setCourseForm({ ...courseForm, cover: e.target.files?.[0] || null })} className="absolute inset-0 opacity-0 cursor-pointer" accept="image/*" /></div>
                <div className="relative"><Button variant="outline" className="w-full h-12 rounded-xl border-dashed border-2 px-4 font-bold text-[11px]"><span>{t(courseForm.courseware ? 'course.pdfReady' : 'course.uploadCourseware')}</span><FileUp className="w-4 h-4 opacity-20" /></Button><input type="file" onChange={e => setCourseForm({ ...courseForm, courseware: e.target.files?.[0] || null })} className="absolute inset-0 opacity-0 cursor-pointer" accept=".pdf" /></div>
              </div>
              <Button onClick={handleCreateCourse} disabled={isCourseSubmitting} className="w-full h-14 rounded-2xl bg-black text-white font-bold uppercase tracking-widest text-[11px]">{t('course.publishAcademy')}</Button>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="articles">
          <Card className="max-w-5xl mx-auto p-10 bg-white rounded-[2rem] border-none shadow-sm space-y-6">
            <div className="flex items-center gap-3"><FileText className="h-5 w-5 text-orange-600" /><h3 className="text-lg font-bold tracking-tight">{t('article.writeDeepArticle')}</h3></div>
            <div className="space-y-4">
              <Input value={articleForm.title} onChange={e => setArticleForm({ ...articleForm, title: e.target.value })} className="bg-unimind-bg-secondary border-none h-14 rounded-xl font-black px-5 text-2xl tracking-tighter" placeholder={t('article.titlePlaceholder')} />
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Select value={articleForm.knowledge_point} onValueChange={v => v === 'NEW_KP' ? (setKPCreationTarget('article'), setShowNewKPDialog(true)) : setArticleForm({ ...articleForm, knowledge_point: v })}><SelectTrigger className="h-10 rounded-xl bg-unimind-bg-secondary border-none font-bold px-4 text-xs"><SelectValue placeholder={t('article.knowledgePoint')} /></SelectTrigger><SelectContent><SelectItem value="0">{t('quiz.noMount')}</SelectItem><SelectItem value="NEW_KP" className="text-indigo-600 font-bold">{t('course.newKnowledgePoint')}</SelectItem>{kpList.map(kp => <SelectItem key={kp.id} value={kp.id.toString()}>{kp.name}</SelectItem>)}</SelectContent></Select>
                <Input value={articleForm.author_display_name} onChange={e => setArticleForm({ ...articleForm, author_display_name: e.target.value })} className="bg-unimind-bg-secondary border-none h-10 rounded-xl font-bold px-5 text-[11px]" placeholder={t('article.authorSignature')} />
                <TagInput tags={articleForm.tags} setTags={t => setArticleForm({ ...articleForm, tags: t })} compact />
              </div>
              <MarkdownEditor content={articleForm.content} onChange={v => setArticleForm({ ...articleForm, content: v })} />
              <Button onClick={async () => { try { await api.post('/articles/', { ...articleForm, knowledge_point: articleForm.knowledge_point === "0" ? null : articleForm.knowledge_point }); toast.success(t('article.articlePublished')); setArticleForm({ title: '', content: '', author_display_name: '', tags: [], knowledge_point: '0' }); fetchLists(); } catch (e) { toast.error(t('article.failed')); } }} className="w-full h-12 rounded-xl bg-black text-white font-bold text-[11px] uppercase tracking-widest">Publish Article</Button>
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="quizzes">
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 items-start">
            <Card className="p-8 bg-white rounded-[2rem] border-none shadow-sm space-y-6">
              <div className="flex items-center gap-3"><Target className="h-6 w-6 text-blue-600" /><h3 className="text-xl font-bold tracking-tight">{t('quiz.entryTitle')}</h3></div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <Select value={quizForm.q_type} onValueChange={v => setQuizForm({ ...quizForm, q_type: v })}><SelectTrigger className="h-10 rounded-xl bg-unimind-bg-secondary border-none font-bold text-xs"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="objective">{t('quiz.objective')}</SelectItem><SelectItem value="subjective">{t('quiz.subjective')}</SelectItem></SelectContent></Select>
                {quizForm.q_type === 'subjective' && <Select value={quizForm.subjective_type} onValueChange={v => setQuizForm({ ...quizForm, subjective_type: v })}><SelectTrigger className="h-10 rounded-xl bg-unimind-bg-secondary border-none font-bold text-xs"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="noun">{t('quiz.noun')}</SelectItem><SelectItem value="short">{t('quiz.shortAnswer')}</SelectItem><SelectItem value="essay">{t('quiz.essay')}</SelectItem></SelectContent></Select>}
                <Select value={quizForm.knowledge_point} onValueChange={v => setQuizForm({ ...quizForm, knowledge_point: v })}><SelectTrigger className="h-10 rounded-xl bg-unimind-bg-secondary border-none font-bold text-xs px-4"><SelectValue placeholder={t('quiz.knowledgePoint')} /></SelectTrigger><SelectContent><SelectItem value="0">{t('quiz.noMount')}</SelectItem>{kpList.map(kp => <SelectItem key={kp.id} value={kp.id.toString()}>{kp.name}</SelectItem>)}</SelectContent></Select>
                <Select value={quizForm.difficulty_level} onValueChange={v => setQuizForm({ ...quizForm, difficulty_level: v })}><SelectTrigger className="h-10 rounded-xl bg-unimind-bg-secondary border-none font-bold text-xs"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="entry">{t('quiz.entry')}</SelectItem><SelectItem value="easy">{t('quiz.easy')}</SelectItem><SelectItem value="normal">{t('quiz.normal')}</SelectItem><SelectItem value="hard">{t('quiz.hard')}</SelectItem><SelectItem value="extreme">{t('quiz.extreme')}</SelectItem></SelectContent></Select>
              </div>
              <textarea value={quizForm.text} onChange={e => setQuizForm({ ...quizForm, text: e.target.value })} className="w-full bg-unimind-bg-secondary border-none rounded-2xl p-6 min-h-[100px] font-bold text-sm" placeholder={t('quiz.textPlaceholder')} />
              <p className="text-[10px] text-muted-foreground -mt-4 ml-1">支持 LaTeX 公式：<code className="text-[10px] bg-muted/30 px-1 rounded">$...$</code> 行内、<code className="text-[10px] bg-muted/30 px-1 rounded">$$...$$</code> 块级</p>
              {quizForm.q_type === 'objective' ? (
                <div className="space-y-4"><Label className="text-[11px] font-bold uppercase opacity-40 ml-1">{t('quiz.options')}</Label><div className="grid grid-cols-2 gap-3">{quizForm.options.map((opt, i) => (<div key={i} className="flex gap-2"><div className="h-10 w-10 rounded-xl bg-black text-white flex items-center justify-center font-bold shrink-0">{String.fromCharCode(65 + i)}</div><Input value={opt} onChange={e => { const no = [...quizForm.options]; no[i] = e.target.value; setQuizForm({ ...quizForm, options: no }); }} className="h-10 rounded-xl bg-unimind-bg-secondary border-none font-bold text-xs px-4" /></div>))}</div><Input value={quizForm.answer} onChange={e => setQuizForm({ ...quizForm, answer: e.target.value })} placeholder={t('quiz.correctAnswerLetter')} className="h-11 rounded-xl bg-unimind-bg-secondary border-none font-bold text-xs px-5" /></div>
              ) : (
                <div className="space-y-4"><textarea value={quizForm.grading_points} onChange={e => setQuizForm({ ...quizForm, grading_points: e.target.value })} className="w-full bg-unimind-bg-secondary border-none rounded-xl p-4 min-h-[80px] font-bold text-sm" placeholder={t('quiz.gradingPointsPlaceholder')} /><textarea value={quizForm.answer} onChange={e => setQuizForm({ ...quizForm, answer: e.target.value })} className="w-full bg-unimind-bg-secondary border-none rounded-xl p-4 min-h-[80px] font-bold text-sm" placeholder={t('quiz.referenceAnswerPlaceholder')} /></div>
              )}
              <Button onClick={handleCreateQuiz} className="w-full h-14 rounded-2xl bg-black text-white font-bold uppercase text-[11px] tracking-widest">{t('quiz.entryBank')}</Button>
            </Card>
            <QuestionBankPanel kpList={kpList} onEdit={q => setEditingItem({ type: 'quizzes', data: { ...q } })} onDelete={id => handleDelete('quizzes/questions', id)} />
          </div>
        </TabsContent>

        <TabsContent value="kp">
          <KnowledgeSystemPanel />
        </TabsContent>

        <TabsContent value="albums">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
            <Card className="p-10 bg-white rounded-3xl border-none shadow-sm space-y-8">
              <div className="flex items-center gap-3"><Layers className="h-6 w-6 text-emerald-600" /><h3 className="text-xl font-bold tracking-tight">{t('album.newAlbum')}</h3></div>
              <Input value={albumForm.name} onChange={e => setAlbumForm({ ...albumForm, name: e.target.value })} className="bg-unimind-bg-secondary border-none h-12 rounded-xl font-bold px-5" placeholder={t('album.namePlaceholder')} />
              <textarea value={albumForm.description} onChange={e => setAlbumForm({ ...albumForm, description: e.target.value })} className="w-full bg-unimind-bg-secondary border-none rounded-2xl p-6 min-h-[100px] font-bold text-sm" placeholder={t('album.descPlaceholder')} />
              <div className="relative"><Button variant="outline" className="w-full h-16 rounded-2xl border-dashed border-2 px-6 font-bold"><span>{t(albumForm.cover ? 'course.coverReady' : 'album.uploadCover')}</span><Upload className="w-4 h-4 opacity-20" /></Button><input type="file" onChange={e => setAlbumForm({ ...albumForm, cover: e.target.files?.[0] || null })} className="absolute inset-0 opacity-0 cursor-pointer" accept="image/*" /></div>
              <Button onClick={handleCreateAlbum} className="w-full h-14 rounded-2xl bg-black text-white font-bold uppercase text-xs tracking-widest">{t('album.createAlbum')}</Button>
            </Card>
            <Card className="p-10 bg-unimind-bg-secondary/50 rounded-3xl border-none shadow-sm space-y-6"><h3 className="text-sm font-bold uppercase tracking-widest opacity-40">{t('album.existingAlbums')}</h3><ScrollArea className="h-[520px]"><div className="grid gap-3 pr-4">{albumList.map(al => (<div key={al.id} className="p-5 bg-white rounded-2xl flex items-center justify-between group"><p className="text-sm font-bold">{al.name}</p><div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity"><Button onClick={() => setEditingItem({ type: 'albums', data: { ...al } })} variant="ghost" size="icon" className="h-8 w-8 text-blue-600"><Edit3 className="w-3.5 h-3.5" /></Button><Button onClick={() => handleDelete('courses/albums', al.id)} variant="ghost" size="icon" className="h-8 w-8 text-red-500"><Trash2 className="w-3.5 h-3.5" /></Button></div></div>))}</div></ScrollArea></Card>
          </div>
        </TabsContent>

        <TabsContent value="bots">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
            <Card className="p-10 bg-white rounded-3xl border-none shadow-sm space-y-8">
              <div className="flex items-center gap-3"><Bot className="h-6 w-6 text-emerald-600" /><h3 className="text-xl font-bold tracking-tight">{t('bot.deployAssistant')}</h3></div>
              <div className="flex items-center gap-6"><div className="relative group shrink-0"><Avatar className="h-20 w-20 border-4 border-white shadow-sm overflow-hidden">{botForm.avatar ? <AvatarImage src={URL.createObjectURL(botForm.avatar)} /> : <AvatarFallback className="text-[11px] font-bold">INIT</AvatarFallback>}</Avatar><div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity rounded-full flex items-center justify-center cursor-pointer"><Upload className="w-4 h-4 text-white" /><input type="file" onChange={e => setBotForm({ ...botForm, avatar: e.target.files?.[0] || null })} className="absolute inset-0 opacity-0 cursor-pointer" accept="image/*" /></div></div><div className="flex-1 space-y-3"><Label className="text-[11px] font-bold uppercase tracking-widest opacity-40 ml-1">{t('bot.nickname')}</Label><Input value={botForm.name} onChange={e => setBotForm({ ...botForm, name: e.target.value })} className="bg-unimind-bg-secondary border-none h-12 rounded-2xl font-bold px-5" /></div></div>
              <textarea value={botForm.prompt} onChange={e => setBotForm({ ...botForm, prompt: e.target.value })} className="w-full bg-unimind-bg-secondary border-none rounded-2xl p-6 min-h-[200px] font-bold text-sm" placeholder={t('bot.promptPlaceholder')} />
              <Button onClick={handleCreateBot} className="w-full h-14 rounded-2xl bg-black text-white font-bold uppercase text-xs tracking-widest">{t('bot.deployBot')}</Button>
            </Card>
            <Card className="p-10 bg-unimind-bg-secondary/50 rounded-3xl border-none shadow-sm space-y-6">
              <h3 className="text-sm font-bold uppercase tracking-widest opacity-40">{t('bot.botMatrix')}</h3>
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
              <div className="flex items-center gap-3"><Rocket className="h-6 w-6 text-red-600" /><h3 className="text-xl font-bold tracking-tight">{t('startupMaterial.uploadMaterial')}</h3></div>
              <Input value={smForm.name} onChange={e => setSmForm({ ...smForm, name: e.target.value })} className="bg-unimind-bg-secondary border-none h-12 rounded-xl font-bold px-5" placeholder={t('startupMaterial.namePlaceholder')} />
              <textarea value={smForm.description} onChange={e => setSmForm({ ...smForm, description: e.target.value })} className="w-full bg-unimind-bg-secondary border-none rounded-2xl p-6 min-h-[100px] font-bold text-sm" placeholder={t('startupMaterial.descPlaceholder')} />
              <div className="relative"><Button variant="outline" className="w-full h-16 rounded-2xl border-dashed border-2 px-6 font-bold"><span>{smForm.file ? smForm.file.name : t('startupMaterial.uploadFile')}</span><Upload className="w-4 h-4 opacity-20" /></Button><input type="file" onChange={e => setSmForm({ ...smForm, file: e.target.files?.[0] || null })} className="absolute inset-0 opacity-0 cursor-pointer" /></div>
              <Button onClick={handleCreateSM} disabled={isSMSubmitting} className="w-full bg-black text-white h-14 rounded-2xl font-bold text-xs tracking-widest uppercase">{t('startupMaterial.uploadMaterialBtn')}</Button>
            </Card>
            <Card className="p-10 bg-unimind-bg-secondary/50 rounded-3xl border-none shadow-sm space-y-6"><h3 className="text-sm font-bold uppercase tracking-widest opacity-40">{t('startupMaterial.existingMaterials')}</h3><ScrollArea className="h-[520px]"><div className="grid gap-3 pr-4">{smList.map(sm => (<div key={sm.id} className="p-5 bg-white rounded-2xl flex items-center justify-between group"><p className="text-sm font-bold">{sm.name}</p><div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity"><Button onClick={() => setEditingItem({ type: 'sm', data: { ...sm } })} variant="ghost" size="icon" className="h-8 w-8 text-blue-600"><Edit3 className="w-3.5 h-3.5" /></Button><Button onClick={() => handleDelete('sm', sm.id)} variant="ghost" size="icon" className="h-8 w-8 text-red-500"><Trash2 className="w-3.5 h-3.5" /></Button></div></div>))}</div></ScrollArea></Card>
          </div>
        </TabsContent>

        <TabsContent value="notifications">
          <Card className="max-w-2xl mx-auto p-10 bg-white rounded-[2rem] border-none shadow-sm space-y-8">
            <div className="flex items-center gap-3"><Bell className="h-6 w-6 text-indigo-600" /><h3 className="text-xl font-bold tracking-tight">{t('notification.siteBroadcast')}</h3></div>
            <div className="space-y-6">
              <Input value={notifForm.title} onChange={e => setNotifForm({ ...notifForm, title: e.target.value })} placeholder={t('notification.titlePlaceholder')} className="bg-unimind-bg-secondary border-none h-12 rounded-xl font-bold px-5" />
              <textarea value={notifForm.content} onChange={e => setNotifForm({ ...notifForm, content: e.target.value })} placeholder={t('notification.contentPlaceholder')} className="w-full bg-unimind-bg-secondary border-none rounded-2xl p-6 min-h-[120px] font-bold text-sm" />
              <Button onClick={handleBroadcast} disabled={isSendingNotif} className="w-full h-14 rounded-2xl bg-black text-white font-bold uppercase text-xs tracking-widest gap-2">{isSendingNotif ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />} {t('notification.sendBroadcast')}</Button>
            </div>
          </Card>
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
      </Tabs>

      {/* --- Dialogs --- */}
      <Dialog open={!!editingItem} onOpenChange={open => !open && setEditingItem(null)}>
        <DialogContent className="sm:max-w-[850px] max-h-[90vh] overflow-y-auto rounded-[3rem] p-10 border-none shadow-2xl text-left bg-white">
          <DialogHeader className="text-left"><DialogTitle className="text-xl font-bold">{t('editDialog.title')}</DialogTitle></DialogHeader>
          <div className="space-y-6 pt-6">
            {editingItem?.type === 'courses' && (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1.5"><Label className="text-[11px] font-bold uppercase opacity-40">{t('editDialog.titleLabel')}</Label><Input value={editingItem.data.title} onChange={e => setEditingItem({ ...editingItem, data: { ...editingItem.data, title: e.target.value } })} className="rounded-xl bg-slate-50 border-none h-10 text-xs font-bold" /></div>
                  <div className="space-y-1.5"><Label className="text-[11px] font-bold uppercase opacity-40">{t('editDialog.eloReward')}</Label><Input type="number" value={editingItem.data.elo_reward} onChange={e => setEditingItem({ ...editingItem, data: { ...editingItem.data, elo_reward: e.target.value } })} className="rounded-xl bg-slate-50 border-none h-10 text-xs font-bold" /></div>
                </div>
                <MarkdownEditor content={editingItem.data.description} onChange={v => setEditingItem({ ...editingItem, data: { ...editingItem.data, description: v } })} />
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1.5"><Label className="text-[11px] font-bold uppercase opacity-40 text-emerald-600">{t('editDialog.updateVideo')}</Label><Input type="file" onChange={e => setEditingItem({ ...editingItem, data: { ...editingItem.data, video_file: e.target.files?.[0] } })} className="rounded-xl h-10 bg-slate-50 text-[11px]" /></div>
                  <div className="space-y-1.5"><Label className="text-[11px] font-bold uppercase opacity-40 text-blue-600">{t('editDialog.updateCover')}</Label><Input type="file" onChange={e => setEditingItem({ ...editingItem, data: { ...editingItem.data, cover_image: e.target.files?.[0] } })} className="rounded-xl h-10 bg-slate-50 text-[11px]" /></div>
                </div>
              </div>
            )}
            {editingItem?.type === 'articles' && (
              <div className="space-y-4">
                <Input value={editingItem.data.title} onChange={e => setEditingItem({ ...editingItem, data: { ...editingItem.data, title: e.target.value } })} className="rounded-xl bg-unimind-bg-secondary border-none h-14 text-2xl font-black px-5" />
                <div className="grid grid-cols-2 gap-4">
                  <Input value={editingItem.data.author_display_name} onChange={e => setEditingItem({ ...editingItem, data: { ...editingItem.data, author_display_name: e.target.value } })} className="rounded-xl bg-slate-50 border-none h-10 text-xs font-bold" placeholder={t('editDialog.signature')} />
                  <Select value={editingItem.data.knowledge_point || "0"} onValueChange={v => setEditingItem({ ...editingItem, data: { ...editingItem.data, knowledge_point: v } })}><SelectTrigger className="h-10 rounded-xl bg-slate-50 border-none font-bold text-xs"><SelectValue /></SelectTrigger><SelectContent>{kpList.map(kp => <SelectItem key={kp.id} value={kp.id.toString()}>{kp.name}</SelectItem>)}</SelectContent></Select>
                </div>
                <TagInput tags={editingItem.data.tags || []} setTags={t => setEditingItem({ ...editingItem, data: { ...editingItem.data, tags: t } })} compact />
                <MarkdownEditor content={editingItem.data.content} onChange={v => setEditingItem({ ...editingItem, data: { ...editingItem.data, content: v } })} />
              </div>
            )}
            {editingItem?.type === 'bots' && (
              <div className="space-y-4">
                <div className="flex items-center justify-between gap-4"><Input value={editingItem.data.name} onChange={e => setEditingItem({ ...editingItem, data: { ...editingItem.data, name: e.target.value } })} className="rounded-xl bg-slate-50 border-none h-10 text-xs font-bold" /><div className="flex items-center gap-2 pt-4"><input type="checkbox" checked={editingItem.data.is_exclusive} onChange={e => setEditingItem({ ...editingItem, data: { ...editingItem.data, is_exclusive: e.target.checked } })} /><Label className="text-[11px] font-bold text-emerald-600">{t('editDialog.exclusiveMentorPermission')}</Label></div></div>
                <Input value={editingItem.data.prompt_template_name || ''} readOnly className="rounded-xl bg-emerald-50/70 border-none h-10 text-[11px] font-bold text-emerald-700" />
                <textarea value={editingItem.data.system_prompt} onChange={e => setEditingItem({ ...editingItem, data: { ...editingItem.data, system_prompt: e.target.value } })} className="w-full min-h-[300px] p-4 rounded-xl bg-slate-50 border-none text-xs" />
              </div>
            )}
            {editingItem?.type === 'quizzes' && (
              <div className="space-y-4">
                <textarea value={editingItem.data.text} onChange={e => setEditingItem({ ...editingItem, data: { ...editingItem.data, text: e.target.value } })} className="w-full p-4 rounded-xl bg-slate-50 border-none text-xs font-bold min-h-[80px]" />
                <div className="grid grid-cols-2 gap-4">
                  <Select value={editingItem.data.knowledge_point || "0"} onValueChange={v => setEditingItem({ ...editingItem, data: { ...editingItem.data, knowledge_point: v } })}><SelectTrigger className="h-10 rounded-xl bg-slate-50 border-none font-bold text-xs"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="0">{t('quiz.noMount')}</SelectItem>{kpList.map(kp => <SelectItem key={kp.id} value={kp.id.toString()}>{kp.name}</SelectItem>)}</SelectContent></Select>
                  <Select value={editingItem.data.difficulty_level || "normal"} onValueChange={v => setEditingItem({ ...editingItem, data: { ...editingItem.data, difficulty_level: v } })}><SelectTrigger className="h-10 rounded-xl bg-slate-50 border-none font-bold text-xs"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="entry">{t('quiz.entry')}</SelectItem><SelectItem value="easy">{t('quiz.easy')}</SelectItem><SelectItem value="normal">{t('quiz.normal')}</SelectItem><SelectItem value="hard">{t('quiz.hard')}</SelectItem><SelectItem value="extreme">{t('quiz.extreme')}</SelectItem></SelectContent></Select>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <textarea value={editingItem.data.grading_points} onChange={e => setEditingItem({ ...editingItem, data: { ...editingItem.data, grading_points: e.target.value } })} className="w-full p-4 rounded-xl bg-slate-50 border-none text-[11px] h-24" placeholder={t('editDialog.gradingPoints')} />
                  <textarea value={editingItem.data.correct_answer} onChange={e => setEditingItem({ ...editingItem, data: { ...editingItem.data, correct_answer: e.target.value } })} className="w-full p-4 rounded-xl bg-slate-50 border-none text-[11px] h-24" placeholder={t('editDialog.answer')} />
                </div>
              </div>
            )}
            <Button onClick={handleSaveEdit} className="w-full h-12 bg-black text-white rounded-xl font-bold text-[11px] uppercase tracking-widest">{t('editDialog.updateAndSync')}</Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={showNewAlbumDialog} onOpenChange={setShowNewAlbumDialog}>
        <DialogContent className="sm:max-w-[420px] rounded-[2.5rem] p-10 border-none shadow-2xl bg-white text-left">
          <DialogHeader><DialogTitle className="text-xl font-black flex items-center gap-3"><Layers className="text-emerald-600 w-5 h-5" /> {t('quickCreate.newAlbum')}</DialogTitle></DialogHeader>
          <div className="space-y-5 pt-6">
            <div className="space-y-1.5"><Label className="text-[11px] font-bold uppercase opacity-40">{t('quickCreate.albumName')}</Label><Input value={newAlbumName} onChange={e => setNewAlbumName(e.target.value)} placeholder={t('quickCreate.albumNamePlaceholder')} className="bg-unimind-bg-secondary border-none h-11 rounded-xl font-bold px-4 text-sm" /></div>
            <div className="space-y-1.5"><Label className="text-[11px] font-bold uppercase opacity-40">{t('quickCreate.albumDesc')}</Label><textarea value={newAlbumDesc} onChange={e => setNewAlbumDesc(e.target.value)} className="w-full bg-unimind-bg-secondary border-none rounded-xl p-4 min-h-[80px] font-bold text-xs" placeholder={t('quickCreate.albumDescPlaceholder')} /></div>
            <div className="flex gap-3 pt-2"><Button variant="outline" onClick={() => setShowNewAlbumDialog(false)} className="flex-1 h-12 rounded-xl font-bold text-xs">{t('quickCreate.cancel')}</Button><Button onClick={handleQuickCreateAlbum} className="flex-[2] h-12 rounded-xl bg-black text-white font-black shadow text-xs uppercase tracking-widest">{t('quickCreate.confirmCreate')}</Button></div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={showNewKPDialog} onOpenChange={setShowNewKPDialog}>
        <DialogContent className="sm:max-w-[500px] rounded-[2.5rem] p-10 border-none shadow-2xl bg-white text-left">
          <DialogHeader><DialogTitle className="text-xl font-black flex items-center gap-3"><BrainCircuit className="text-indigo-600 w-5 h-5" /> {t('quickCreate.newKnowledgePoint')}</DialogTitle></DialogHeader>
          <div className="space-y-5 pt-6">
            <div className="space-y-1.5"><Label className="text-[11px] font-bold uppercase opacity-40">{t('quickCreate.nodeName')}</Label><Input value={newKPForm.name} onChange={e => setNewKPForm({ ...newKPForm, name: e.target.value })} placeholder={t('quickCreate.nodeNamePlaceholder')} className="bg-unimind-bg-secondary border-none h-11 rounded-xl font-bold px-4 text-sm" /></div>
            <div className="space-y-1.5"><Label className="text-[11px] font-bold uppercase opacity-40">{t('quickCreate.parent')}</Label><Select value={newKPForm.parent} onValueChange={v => setNewKPForm({ ...newKPForm, parent: v })}><SelectTrigger className="h-11 rounded-xl bg-unimind-bg-secondary border-none font-bold text-xs px-4"><SelectValue placeholder={t('quickCreate.topLevel')} /></SelectTrigger><SelectContent>{kpList.map(kp => <SelectItem key={kp.id} value={kp.id.toString()} className="text-xs">{kp.name}</SelectItem>)}</SelectContent></Select></div>
            <textarea value={newKPForm.description} onChange={e => setNewKPForm({ ...newKPForm, description: e.target.value })} className="w-full bg-unimind-bg-secondary border-none rounded-xl p-4 min-h-[100px] font-bold text-xs" placeholder={t('quickCreate.descPlaceholder')} />
            <div className="flex gap-3 pt-2"><Button variant="outline" onClick={() => setShowNewKPDialog(false)} className="flex-1 h-12 rounded-xl font-bold text-xs">{t('quickCreate.cancel')}</Button><Button onClick={handleQuickCreateKP} className="flex-[2] h-12 rounded-xl bg-black text-white font-black shadow text-xs uppercase tracking-widest">{t('quickCreate.confirmSave')}</Button></div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};
