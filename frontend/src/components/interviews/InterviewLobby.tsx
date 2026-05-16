import React, { useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { FileText, Globe, GraduationCap, Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import { formatApiErrorToast } from '@/lib/apiError';
import api from '@/lib/api';

interface Props {
  style: 'friendly' | 'pressure';
  onStyleChange: (s: 'friendly' | 'pressure') => void;
  onSessionCreated: (sessionId: number) => void;
}

const INTERVIEW_TYPES = [
  { id: 'resume', icon: FileText, title: '简历深挖', desc: '结合你的经历生成针对性追问。' },
  { id: 'english', icon: Globe, title: '英语口语', desc: '模拟英文问答并给出流畅度反馈。' },
  { id: 'professional', icon: GraduationCap, title: '专业课', desc: '围绕专业核心考点进行深度追问。' },
];

export const InterviewLobby: React.FC<Props> = ({ style, onStyleChange, onSessionCreated }) => {
  const [startingType, setStartingType] = useState<string | null>(null);
  const [resumeText, setResumeText] = useState('');
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [resumeSaving, setResumeSaving] = useState(false);

  const startInterview = async (type: string) => {
    setStartingType(type);
    try {
      const res = await api.post('/interviews/sessions/', { session_type: type, interviewer_style: style });
      const sessionId = Number(res.data?.id || 0);
      if (!sessionId) throw new Error('missing_session_id');
      toast.success(`面试会话 #${sessionId} 已创建`);
      onSessionCreated(sessionId);
    } catch (e) {
      toast.error(formatApiErrorToast(e, '创建面试会话失败'));
    } finally {
      setStartingType(null);
    }
  };

  const submitResume = async () => {
    if (!resumeText.trim() && !resumeFile) { toast.error('请填写简历文本或上传文件'); return; }
    setResumeSaving(true);
    try {
      const fd = new FormData();
      if (resumeText.trim()) fd.append('resume_text', resumeText.trim());
      if (resumeFile) fd.append('file', resumeFile);
      const res = await api.post('/interviews/resume/tune/', fd);
      toast.success(`简历调优已完成（记录 #${res.data?.record_id || '--'}）`);
    } catch (e) {
      toast.error(formatApiErrorToast(e, '简历调优失败'));
    } finally {
      setResumeSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card className="p-6 rounded-3xl bg-gradient-to-r from-indigo-500/10 to-emerald-500/10 border-indigo-200/60">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/15 text-indigo-700 text-xs font-bold">
          <Sparkles className="w-4 h-4" /> 多阶段复试训练
        </div>
        <h2 className="text-2xl font-black mt-3">从简历到专业面试的一体化闭环</h2>
        <p className="text-sm text-muted-foreground mt-2">支持风格选择、实时追问和结束后雷达报告。</p>
      </Card>

      <Card className="p-5 rounded-2xl border border-border/60 space-y-3">
        <p className="text-xs font-black uppercase tracking-widest text-muted-foreground">导师风格</p>
        <div className="flex gap-2">
          <Button size="sm" variant={style === 'friendly' ? 'default' : 'outline'} className="h-8 text-xs" onClick={() => onStyleChange('friendly')}>和蔼引导</Button>
          <Button size="sm" variant={style === 'pressure' ? 'default' : 'outline'} className="h-8 text-xs" onClick={() => onStyleChange('pressure')}>高压追问</Button>
        </div>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {INTERVIEW_TYPES.map((type) => (
          <Card key={type.id} className="p-5 rounded-2xl border border-border/60">
            <type.icon className="w-7 h-7 text-indigo-600" />
            <h4 className="text-lg font-bold mt-3">{type.title}</h4>
            <p className="text-sm text-muted-foreground mt-2 min-h-10">{type.desc}</p>
            <Button className="w-full mt-4 rounded-xl bg-slate-900 text-white text-xs font-bold" onClick={() => startInterview(type.id)} disabled={startingType === type.id}>
              {startingType === type.id ? '创建中...' : '进入会话'}
            </Button>
          </Card>
        ))}
      </div>

      <Card className="p-5 rounded-2xl border border-border/60 space-y-3">
        <p className="text-xs font-black uppercase tracking-widest text-muted-foreground">简历调优</p>
        <textarea
          value={resumeText}
          onChange={(e) => setResumeText(e.target.value)}
          className="w-full min-h-[120px] rounded-xl border border-border/60 p-3 text-sm"
          placeholder="粘贴简历文本，或上传 PDF/DOCX/TXT..."
        />
        <Input type="file" accept=".pdf,.doc,.docx,.txt" onChange={(e) => setResumeFile(e.target.files?.[0] || null)} />
        <Button className="rounded-xl text-xs font-bold bg-black text-white" onClick={submitResume} disabled={resumeSaving}>
          {resumeSaving ? '分析中...' : '提交简历调优'}
        </Button>
      </Card>
    </div>
  );
};
