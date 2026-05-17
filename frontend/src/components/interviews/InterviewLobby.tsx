import React, { useEffect, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { FileText, Globe, GraduationCap, Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import { formatApiErrorToast } from '@/lib/apiError';
import { ResumeTuner } from './ResumeTuner';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import api from '@/lib/api';

interface Props {
  style: 'friendly' | 'pressure';
  onStyleChange: (s: 'friendly' | 'pressure') => void;
  onSessionCreated: (sessionId: number) => void;
}

const INTERVIEW_TYPES = [
  { id: 'resume', icon: FileText, title: '简历深挖', desc: '结合你的经历生成针对性追问。' },
  { id: 'english', icon: Globe, title: '英语口语', desc: '模拟英文问答并给出流畅度反馈。由 GLM 语音模型驱动。' },
  { id: 'professional', icon: GraduationCap, title: '专业课', desc: '围绕专业核心考点进行深度追问。' },
];

export const InterviewLobby: React.FC<Props> = ({ style, onStyleChange, onSessionCreated }) => {
  const [startingType, setStartingType] = useState<string | null>(null);
  const [hasResume, setHasResume] = useState<boolean | null>(null);
  const [hasKnowledgeTree, setHasKnowledgeTree] = useState<boolean | null>(null);
  const [checking, setChecking] = useState(true);
  const institution = useInstitutionStore((s) => s.institution);

  // 检查是否有简历记录 + 机构知识树
  useEffect(() => {
    const check = async () => {
      setChecking(true);
      // 简历检查
      try {
        const res = await api.get('/interviews/resume/tune/');
        setHasResume((res.data?.results || []).length > 0);
      } catch {
        setHasResume(false);
      }
      // 知识树检查：API 按用户机构自动隔离，无需传参
      if (institution) {
        try {
          const kpRes = await api.get('/quizzes/knowledge-points/');
          // 无分页时返回数组，有分页时返回 {results: [...]}
          const results = Array.isArray(kpRes.data) ? kpRes.data : (kpRes.data?.results || []);
          setHasKnowledgeTree(results.length > 0);
        } catch {
          setHasKnowledgeTree(false);
        }
      } else {
        setHasKnowledgeTree(false);
      }
      setChecking(false);
    };
    check();
  }, [institution]);

  const startInterview = async (type: string) => {
    // 前端前置校验（加载中也不允许操作，防止竞态绕过）
    if (type === 'resume' && hasResume !== true) {
      toast.error('请先在下方「简历调优」中上传并分析简历');
      return;
    }
    if (type === 'professional' && hasKnowledgeTree !== true) {
      toast.error('当前机构尚未设置知识结构，请联系机构管理员');
      return;
    }

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

  const getCardState = (typeId: string) => {
    // 加载中：所有卡片禁用
    if (checking) {
      return { disabled: true, hint: '检查中...' };
    }
    if (typeId === 'resume' && !hasResume) {
      return { disabled: true, hint: '请先上传简历' };
    }
    if (typeId === 'english') {
      return { disabled: true, hint: '语音面试即将上线' };
    }
    if (typeId === 'professional' && !hasKnowledgeTree) {
      return { disabled: true, hint: '机构未设置知识结构' };
    }
    return { disabled: false, hint: null };
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
        {INTERVIEW_TYPES.map((type) => {
          const state = getCardState(type.id);
          return (
            <Card key={type.id} className={`p-5 rounded-2xl border border-border/60 ${state.disabled ? 'opacity-60' : ''}`}>
              <type.icon className="w-7 h-7 text-indigo-600" />
              <h4 className="text-lg font-bold mt-3">{type.title}</h4>
              <p className="text-sm text-muted-foreground mt-2 min-h-10">{type.desc}</p>
              <Button
                className="w-full mt-4 rounded-xl bg-slate-900 text-white text-xs font-bold"
                onClick={() => startInterview(type.id)}
                disabled={startingType === type.id || state.disabled}
              >
                {startingType === type.id ? '创建中...' : state.hint || '进入会话'}
              </Button>
            </Card>
          );
        })}
      </div>

      <ResumeTuner />
    </div>
  );
};
