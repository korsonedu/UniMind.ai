import { DshActionCard, type ActionPayload } from './DshActionCard';
import { Link } from 'react-router-dom';
import { InlineVisualCard } from '@/components/InlineVisualCard';
import type { VisualData } from '@/pages/xiaoyu/visuals';
import { PracticeResultCard, type PracticeResultPayload } from '@/pages/xiaoyu/visuals/PracticeResultCard';

export type DshCard = VisualData & { tool: string };
type Question = { id?: number; text: string; kp_name?: string; options?: string[] | Record<string, string>; answer?: string };

export function DshToolCard({ card }: { card: DshCard }) {
  if (card.type === 'diagnostic_quiz' || card.type === 'faq_draft') return <DshActionCard payload={card.payload as unknown as ActionPayload} />;
  if (card.type === 'question_preview') {
    const questions = card.payload.questions as Question[];
    return <div className="um-visual-card"><div className="um-visual-body"><div className="um-visual-question-preview space-y-4">
      <h3 className="text-sm font-semibold">{String(card.payload.title)}</h3>
      {questions.map((question, index) => <div key={question.id ?? index} className="space-y-2 border-t border-border/60 pt-3 text-sm leading-6">
        <p className="text-xs text-muted-foreground">{question.kp_name} {question.id ? `· #${question.id}` : ''}</p>
        <p className="whitespace-pre-wrap">{question.text}</p>
        {question.options && Object.entries(question.options).map(([key, value]) => <p key={key} className="text-foreground/60">{Array.isArray(question.options) ? String.fromCharCode(65 + Number(key)) : key}．{String(value)}</p>)}
        {question.answer && <details><summary className="cursor-pointer text-xs text-muted-foreground">参考答案</summary><p className="whitespace-pre-wrap pt-2">{question.answer}</p></details>}
      </div>)}
      {!questions.length && <p className="text-sm text-muted-foreground">暂无匹配题目。</p>}
      <p className="text-xs text-muted-foreground/80">只读题目预览；作答与批改请进入习题训练。</p>
      <Link to="/tests" className="inline-block text-xs underline underline-offset-4">进入习题训练 →</Link>
    </div></div></div>;
  }
  if (card.type === 'practice_quiz') return <InlineVisualCard visual={card} />;
  if (card.type === 'practice_result') return <section className="um-visual-card"><div className="um-visual-body"><PracticeResultCard payload={card.payload as unknown as PracticeResultPayload} snapshot /></div></section>;
  if (!['data_card', 'knowledge_map', 'latex_derivation', 'step_solution', 'function_graph', 'action_cards'].includes(card.type)) return null;
  return <InlineVisualCard visual={card} />;
}
