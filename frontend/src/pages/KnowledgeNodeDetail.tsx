import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Loader2, Maximize2, Target } from 'lucide-react';
import { PageWrapper } from '@/components/PageWrapper';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import api from '@/lib/api';
import { processMathContent } from '@/lib/utils';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { KnowledgeTrainingDialog } from './knowledge-map/TrainingDialog';

interface KnowledgePointDetail {
  id: number;
  name: string;
  description: string;
  level: string;
}

export const KnowledgeNodeDetail: React.FC = () => {
  const navigate = useNavigate();
  const { id } = useParams();
  const [loading, setLoading] = useState(true);
  const [node, setNode] = useState<KnowledgePointDetail | null>(null);
  const [questions, setQuestions] = useState<any[]>([]);
  const [selectedQuestion, setSelectedQuestion] = useState<any>(null);

  useEffect(() => {
    const fetchData = async () => {
      if (!id) return;
      setLoading(true);
      try {
        const [nodeRes, questionRes] = await Promise.all([
          api.get(`/quizzes/knowledge-points/${id}/`),
          api.get('/quizzes/questions/', { params: { kp: id } }),
        ]);
        setNode(nodeRes.data);
        setQuestions(questionRes.data || []);
      } catch (e) { console.error('fetchKnowledgeNode failed', e); }
      finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [id]);

  return (
    <PageWrapper title="知识点详情" subtitle="知识点与关联题目">
      <div className="max-w-3xl mx-auto space-y-4 animate-in fade-in duration-300 text-left">
        <Button
          variant="ghost"
          onClick={() => navigate('/knowledge-map')}
          className="h-9 rounded-xl px-3 text-xs font-bold text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4 mr-1.5" />
          返回知识卡片
        </Button>

        {loading ? (
          <Card className="rounded-2xl border border-border/60 bg-card p-8 flex items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground/50" />
          </Card>
        ) : (
          <>
            <Card className="rounded-2xl border border-border/60 bg-card p-5 space-y-3">
              <div className="flex items-center gap-2">
                <Badge className="bg-emerald-500 text-white border-none uppercase text-[9px] font-bold">Knowledge Point</Badge>
              </div>
              <h1 className="text-lg font-black tracking-tight text-foreground">{node?.name || '知识点'}</h1>
              <div className="text-sm leading-relaxed text-muted-foreground">
                <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                  {processMathContent(node?.description || '暂无描述')}
                </ReactMarkdown>
              </div>
            </Card>

            <Card className="rounded-2xl border border-border/60 bg-card p-5 space-y-3">
              <h2 className="text-[11px] font-black uppercase tracking-widest text-muted-foreground flex items-center gap-2">
                <Target className="h-3.5 w-3.5" />
                关联题目 ({questions.length})
              </h2>
              <div className="space-y-2">
                {questions.map((q) => (
                  <button
                    key={q.id}
                    onClick={() => setSelectedQuestion(q)}
                    className="w-full p-3 bg-muted/30 rounded-xl flex items-center gap-2 border border-border/40 text-left"
                  >
                    <Badge variant="outline" className="text-[9px] py-0 h-4 uppercase shrink-0">
                      {q.subjective_type || q.q_type}
                    </Badge>
                    <div className="text-xs font-bold text-foreground truncate flex-1">
                      <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                        {processMathContent(q.text)}
                      </ReactMarkdown>
                    </div>
                    <Maximize2 className="h-3.5 w-3.5 text-muted-foreground/50 shrink-0" />
                  </button>
                ))}
                {questions.length === 0 && (
                  <div className="text-xs font-bold text-muted-foreground py-6 text-center">暂无关联题目</div>
                )}
              </div>
            </Card>
          </>
        )}

        <KnowledgeTrainingDialog question={selectedQuestion} onClose={() => setSelectedQuestion(null)} />
      </div>
    </PageWrapper>
  );
};

