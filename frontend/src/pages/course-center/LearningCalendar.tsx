import type { LearningDay } from './types';
import { LearningHeatmap } from './LearningHeatmap';

export function LearningCalendar({ today, days }: { today: string; days: LearningDay[] }) {
  return <LearningHeatmap today={today} days={days} />;
}
