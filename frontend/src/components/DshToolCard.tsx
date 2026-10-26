import { Link } from 'react-router-dom';
import { InlineVisualCard } from '@/components/InlineVisualCard';
import type { VisualData } from '@/pages/xiaoyu/visuals';
import { PracticeQuizCard, type PracticePayload } from '@/pages/xiaoyu/visuals/PracticeQuizCard';
import { PracticeResultCard, type PracticeResultPayload } from '@/pages/xiaoyu/visuals/PracticeResultCard';

export type DshCard = VisualData & { tool: string };
type Question = { id?: number; text: string; kp_name?: string; options?: string[] | Record<string, string>; answer?: string };

export function DshToolCard({ card }: { card: DshCard }) {
  if (card.type === 'question_preview') {
    const questions = card.payload.questions as Question[];
    return <div className="space-y-4 rounded-xl border border-black/10 p-4">
      <h3 className="text-sm font-semibold">{String(card.payload.title)}</h3>
      {questions.map((question, index) => <div key={question.id ?? index} className="space-y-2 border-t border-black/5 pt-3 text-sm leading-6">
        <p className="text-xs text-black/45">{question.kp_name} {question.id ? `· #${question.id}` : ''}</p>
        <p className="whitespace-pre-wrap">{question.text}</p>
        {question.options && Object.entries(question.options).map(([key, value]) => <p key={key} className="text-black/60">{Array.isArray(question.options) ? String.fromCharCode(65 + Number(key)) : key}．{String(value)}</p>)}
        {question.answer && <details><summary className="cursor-pointer text-xs text-black/50">参考答案</summary><p className="whitespace-pre-wrap pt-2">{question.answer}</p></details>}
      </div>)}
      {!questions.length && <p className="text-sm text-black/50">暂无匹配题目。</p>}
      <p className="text-xs text-black/40">只读题目预览；作答与批改请进入习题训练。</p>
      <Link to="/tests" className="inline-block text-xs underline underline-offset-4">进入习题训练 →</Link>
    </div>;
  }
  if (card.type === 'practice_quiz') return <PracticeQuizCard payload={card.payload as unknown as PracticePayload} />;
  if (card.type === 'practice_result') return <PracticeResultCard payload={card.payload as unknown as PracticeResultPayload} snapshot />;
  if (!['data_card', 'knowledge_map'].includes(card.type)) return null;
  return <InlineVisualCard visual={card} />;
}
