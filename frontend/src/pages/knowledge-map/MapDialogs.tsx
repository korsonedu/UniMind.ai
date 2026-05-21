import React from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Target, BookOpen, FileText, Video, Maximize2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { processMathContent } from '@/lib/utils';
import { useTranslation } from 'react-i18next';

interface NodeDetailDialogProps {
  node: any;
  details: { courses: any[], articles: any[], questions: any[] };
  onClose: () => void;
  onQuestionClick: (q: any) => void;
}

export const NodeDetailDialog: React.FC<NodeDetailDialogProps> = ({
  node,
  details,
  onClose,
  onQuestionClick
}) => {
  const { t } = useTranslation('knowledgeMap');

  return (
    <Dialog open={!!node} onOpenChange={open => !open && onClose()}>
      <DialogContent className="sm:max-w-[750px] rounded-[3rem] p-10 border-none shadow-2xl text-left overflow-hidden max-h-[85vh] flex flex-col bg-card">
        <DialogHeader>
          <div className="flex items-center gap-3 mb-2"><Badge className="bg-emerald-500 text-white border-none uppercase text-[11px] font-bold">Node Detail</Badge></div>
          <DialogTitle className="text-3xl font-bold tracking-tight text-left">{node?.name}</DialogTitle>
          <div className="text-sm font-medium text-muted-foreground mt-2 leading-relaxed text-left">
            <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
              {processMathContent(node?.description || "")}
            </ReactMarkdown>
          </div>
        </DialogHeader>
        <ScrollArea className="flex-1 mt-8 pr-4">
          <div className="space-y-8 pb-4 text-left">
            <div className="space-y-4 text-left">
              <h5 className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2"><Target className="w-3.5 h-3.5" /> {t('nodeDetailDialog.relatedQuestions')} ({details.questions.length})</h5>
              <div className="grid gap-2">{details.questions.map(q => (
                <button
                  key={q.id}
                  type="button"
                  onClick={() => onQuestionClick(q)}
                  className="w-full text-left p-4 bg-muted/60 rounded-2xl flex items-center gap-3 border border-border cursor-pointer hover:bg-muted transition-colors group"
                >
                  <Badge variant="outline" className="text-[11px] py-0 h-4 uppercase">{q.subjective_type || q.q_type}</Badge>
                  <div className="text-xs font-bold text-foreground truncate flex-1 text-left">
                    <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                      {processMathContent(q.text)}
                    </ReactMarkdown>
                  </div>
                  <Maximize2 className="w-3 h-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-all" />
                </button>))}
              </div>
            </div>
            <div className="space-y-4 text-left">
              <h5 className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2"><BookOpen className="w-3.5 h-3.5" /> {t('nodeDetailDialog.courseResources')} ({details.courses.length})</h5>
              <div className="grid gap-2">{details.courses.map(c => (<div key={c.id} className="p-4 bg-emerald-500/10 rounded-2xl flex items-center gap-3 border border-emerald-400/20"><Video className="w-3.5 h-3.5 text-emerald-500" /><p className="text-xs font-bold text-foreground truncate">{c.title}</p></div>))}</div>
            </div>
            <div className="space-y-4 text-left">
              <h5 className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2"><FileText className="w-3.5 h-3.5" /> {t('nodeDetailDialog.referenceArticles')} ({details.articles.length})</h5>
              <div className="grid gap-2">{details.articles.map(a => (<div key={a.id} className="p-4 bg-orange-500/10 rounded-2xl flex items-center gap-3 border border-orange-400/20"><FileText className="w-3.5 h-3.5 text-orange-500" /><p className="text-xs font-bold text-foreground truncate">{a.title}</p></div>))}</div>
            </div>
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
};

interface QuestionDetailDialogProps {
  question: any;
  onClose: () => void;
}

export const QuestionDetailDialog: React.FC<QuestionDetailDialogProps> = ({
  question,
  onClose
}) => {
  const { t } = useTranslation('knowledgeMap');

  return (
    <Dialog open={!!question} onOpenChange={open => !open && onClose()}>
      <DialogContent className="sm:max-w-[800px] rounded-[3rem] p-12 border-none shadow-2xl text-left overflow-y-auto max-h-[90vh] bg-card">
        <DialogHeader>
          <div className="flex items-center gap-3 mb-4"><Badge className="bg-indigo-600 text-white border-none uppercase text-[11px] font-bold">Question Details</Badge><Badge variant="outline" className="text-[11px] font-bold">ELO {question?.difficulty}</Badge></div>
          <DialogTitle className="text-2xl font-bold leading-relaxed text-foreground text-left">
            <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
              {processMathContent(question?.text || "")}
            </ReactMarkdown>
          </DialogTitle>
        </DialogHeader>
        <div className="mt-10 space-y-8 text-left">
          <div className="space-y-3 text-left">
            <h5 className="text-[11px] font-bold uppercase tracking-widest text-emerald-600">{t('nodeDetailDialog.standardAnswer')}</h5>
            <div className="p-8 bg-emerald-500/10 rounded-[2rem] border border-emerald-400/20 text-sm font-medium leading-relaxed text-left text-foreground">
              <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                {processMathContent(question?.correct_answer || "")}
              </ReactMarkdown>
            </div>
          </div>
          {question?.ai_answer && (
            <div className="space-y-3 text-left">
              <h5 className="text-[11px] font-bold uppercase tracking-widest text-indigo-600">{t('nodeDetailDialog.deepAnalysis')}</h5>
              <div className="p-8 bg-slate-900 text-slate-200 rounded-[2rem] text-sm leading-relaxed shadow-sm text-left">
                <div className="prose prose-invert prose-sm max-w-none prose-p:leading-relaxed">
                  <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
                    {processMathContent(question.ai_answer)}
                  </ReactMarkdown>
                </div>
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
};
