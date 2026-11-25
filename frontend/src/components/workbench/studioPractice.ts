import type { StudioQuizAnswer, StudioQuizQuestion } from '@/types/workbench';

export function flashcardStep(index: number, key: string, count: number) {
  if (key === 'ArrowLeft') return Math.max(0, index - 1);
  if (key === 'ArrowRight') return Math.min(count - 1, index + 1);
  return index;
}

export type StudioQuizDrafts = Record<string, StudioQuizAnswer['answer']>;

export function studioQuizAnswers(questions: StudioQuizQuestion[], drafts: StudioQuizDrafts): StudioQuizAnswer[] {
  return questions.flatMap(question => {
    const value = drafts[question.id];
    const answer = typeof value === 'string' ? value.trim() : value;
    return answer === undefined || answer === '' ? [] : [{ question_id: question.id, answer }];
  });
}
