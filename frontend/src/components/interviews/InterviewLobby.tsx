import React, { useEffect, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { FileText, Globe, GraduationCap, Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import { formatApiErrorToast } from '@/lib/apiError';
import { useTranslation } from 'react-i18next';
import { ResumeTuner } from './ResumeTuner';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import api from '@/lib/api';

interface Props {
  style: 'friendly' | 'pressure';
  onStyleChange: (s: 'friendly' | 'pressure') => void;
  onSessionCreated: (sessionId: number) => void;
}

const INTERVIEW_TYPES = [
  { id: 'resume', icon: FileText },
  { id: 'english', icon: Globe },
  { id: 'professional', icon: GraduationCap },
];

export const InterviewLobby: React.FC<Props> = ({ style, onStyleChange, onSessionCreated }) => {
  const { t } = useTranslation('interviews');
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
      toast.error(t('lobby.resumeRequiredToast'));
      return;
    }
    if (type === 'professional' && hasKnowledgeTree !== true) {
      toast.error(t('lobby.knowledgeTreeRequiredToast'));
      return;
    }

    setStartingType(type);
    try {
      const res = await api.post('/interviews/sessions/', { session_type: type, interviewer_style: style });
      const sessionId = Number(res.data?.id || 0);
      if (!sessionId) throw new Error('missing_session_id');
      toast.success(t('lobby.sessionCreated', { id: sessionId }));
      onSessionCreated(sessionId);
    } catch (e) {
      toast.error(formatApiErrorToast(e, t('lobby.createSessionFailed')));
    } finally {
      setStartingType(null);
    }
  };

  const getCardState = (typeId: string) => {
    // 加载中：所有卡片禁用
    if (checking) {
      return { disabled: true, hint: t('lobby.checking') };
    }
    if (typeId === 'resume' && !hasResume) {
      return { disabled: true, hint: t('lobby.uploadResumeFirst') };
    }
    if (typeId === 'english') {
      return { disabled: true, hint: t('lobby.voiceComingSoon') };
    }
    if (typeId === 'professional' && !hasKnowledgeTree) {
      return { disabled: true, hint: t('lobby.noKnowledgeTree') };
    }
    return { disabled: false, hint: null };
  };

  return (
    <div className="space-y-4">
      <Card className="p-6 rounded-3xl bg-gradient-to-r from-indigo-500/10 to-emerald-500/10 border-indigo-200/60">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-500/15 text-indigo-700 text-xs font-bold">
          <Sparkles className="w-4 h-4" /> {t('lobby.badge')}
        </div>
        <h2 className="text-2xl font-black mt-3">{t('lobby.heading')}</h2>
        <p className="text-sm text-muted-foreground mt-2">{t('lobby.subtitle')}</p>
      </Card>

      <Card className="p-5 rounded-2xl border border-border/60 space-y-3">
        <p className="text-xs font-black uppercase tracking-widest text-muted-foreground">{t('lobby.styleLabel')}</p>
        <div className="flex gap-2">
          <Button size="sm" variant={style === 'friendly' ? 'default' : 'outline'} className="h-8 text-xs" onClick={() => onStyleChange('friendly')}>{t('lobby.styleFriendly')}</Button>
          <Button size="sm" variant={style === 'pressure' ? 'default' : 'outline'} className="h-8 text-xs" onClick={() => onStyleChange('pressure')}>{t('lobby.stylePressure')}</Button>
        </div>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {INTERVIEW_TYPES.map((type) => {
          const state = getCardState(type.id);
          return (
            <Card key={type.id} className={`p-5 rounded-2xl border border-border/60 ${state.disabled ? 'opacity-60' : ''}`}>
              <type.icon className="w-7 h-7 text-indigo-600" />
              <h4 className="text-lg font-bold mt-3">{t(`lobby.type${type.id.charAt(0).toUpperCase() + type.id.slice(1)}`)}</h4>
              <p className="text-sm text-muted-foreground mt-2 min-h-10">{t(`lobby.type${type.id.charAt(0).toUpperCase() + type.id.slice(1)}Desc`)}</p>
              <Button
                className="w-full mt-4 rounded-xl bg-slate-900 text-white text-xs font-bold"
                onClick={() => startInterview(type.id)}
                disabled={startingType === type.id || state.disabled}
              >
                {startingType === type.id ? t('lobby.creating') : state.hint || t('lobby.enterSession')}
              </Button>
            </Card>
          );
        })}
      </div>

      <ResumeTuner />
    </div>
  );
};
