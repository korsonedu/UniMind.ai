import type { Course, LearningDay } from './types';
import { LearningHeatmap } from './LearningHeatmap';

export function LearningCalendar({ today, days, courses }: { today: string; days: LearningDay[]; courses: Course[] }) {
  return <LearningHeatmap today={today} days={days} courses={courses} />;
}
