import React, { useReducer, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import api from '@/lib/api';

interface SubmissionEntry {
  submission_id: number;
  student_name: string;
  question_preview: string;
  ai_score: number;
  ai_feedback: string;
  q_type: string;
}

interface EditsState {
  [submission_id: number]: { score: number; feedback: string };
}

type EditAction =
  | { type: 'set_score'; submission_id: number; score: number }
  | { type: 'set_feedback'; submission_id: number; feedback: string }
  | { type: 'reset' };

function editsReducer(state: EditsState, action: EditAction): EditsState {
  switch (action.type) {
    case 'set_score': {
      const entry = state[action.submission_id] || { score: 0, feedback: '' };
      return { ...state, [action.submission_id]: { ...entry, score: action.score } };
    }
    case 'set_feedback': {
      const entry = state[action.submission_id] || { score: 0, feedback: '' };
      return { ...state, [action.submission_id]: { ...entry, feedback: action.feedback } };
    }
    case 'reset':
      return {};
    default:
      return state;
  }
}

export function GradingPreviewCard({ payload }: { payload: Record<string, unknown> }) {
  const assignmentId = payload.assignment_id as number;
  const title = (payload.title as string) || `练习 #${assignmentId}`;
  const submissions = (payload.submissions || []) as SubmissionEntry[];

  const [edits, dispatch] = useReducer(editsReducer, {});
  const [confirming, setConfirming] = useState(false);

  if (!submissions.length) {
    return <p className="text-muted-foreground text-sm">暂无待评分提交</p>;
  }

  const handleConfirm = async () => {
    setConfirming(true);
    const editList = Object.entries(edits).map(([sid, e]) => ({
      submission_id: parseInt(sid),
      score: e.score,
      feedback: e.feedback,
    }));
    // Fill in unmodified entries with AI scores
    for (const sub of submissions) {
      if (!edits[sub.submission_id]) {
        editList.push({
          submission_id: sub.submission_id,
          score: sub.ai_score,
          feedback: sub.ai_feedback,
        });
      }
    }
    try {
      await api.post('/api/ai/chat/', {
        message: `confirm_grades ${JSON.stringify({ assignment_id: assignmentId, edits: editList })}`,
        bot_id: 0,
      });
      toast.success('成绩已确认');
    } catch {
      toast.error('确认失败');
    } finally {
      setConfirming(false);
    }
  };

  const handleReject = async () => {
    try {
      await api.post('/api/ai/chat/', {
        message: `bulk_grade_submissions ${JSON.stringify({ assignment_id: assignmentId, action: 'reject' })}`,
        bot_id: 0,
      });
      toast.success('已驳回 AI 评分');
    } catch {
      toast.error('驳回失败');
    }
  };

  return (
    <div className="space-y-4 rounded-2xl border border-border bg-card p-5">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold">{title}</h3>
        <span className="text-xs text-muted-foreground">{submissions.length} 份提交</span>
      </div>

      <div className="space-y-3 max-h-96 overflow-y-auto">
        {submissions.map((sub) => {
          const edit = edits[sub.submission_id];
          return (
            <div key={sub.submission_id} className="border border-border/50 rounded-xl p-3 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold">{sub.student_name}</span>
                <span className="text-[10px] text-muted-foreground">{sub.q_type}</span>
              </div>
              <p className="text-xs text-muted-foreground line-clamp-2">{sub.question_preview}</p>
              <div className="flex items-center gap-2">
                <label className="text-[10px] text-muted-foreground w-8">分数</label>
                <Input
                  type="number"
                  min={0}
                  className="h-7 w-20 text-xs rounded-lg"
                  defaultValue={edit?.score ?? sub.ai_score}
                  onChange={(e) => {
                    const v = Math.max(0, parseFloat(e.target.value) || 0);
                    dispatch({ type: 'set_score', submission_id: sub.submission_id, score: v });
                  }}
                />
                <Textarea
                  className="h-7 text-xs rounded-lg flex-1 resize-none"
                  placeholder={sub.ai_feedback || '评语'}
                  defaultValue={edit?.feedback ?? ''}
                  onChange={(e) =>
                    dispatch({ type: 'set_feedback', submission_id: sub.submission_id, feedback: e.target.value })
                  }
                  rows={1}
                />
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex items-center gap-2 pt-2">
        <Button size="sm" className="rounded-xl" onClick={handleConfirm} disabled={confirming}>
          全部确认
        </Button>
        <Button size="sm" variant="outline" className="rounded-xl" onClick={handleReject}>
          全部驳回
        </Button>
      </div>
    </div>
  );
}
