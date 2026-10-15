export interface Course {
  id: number;
  title: string;
  module?: number | null;
  module_name?: string;
  module_sort_order?: number;
  description: string;
  video_file: string | null;
  courseware: string | null;
  reference_materials: string | null;
  elo_reward: number;
  created_at: string;
  subject?: string;
  subject_name?: string;
  album_name?: string;
  tags?: string[];
}

export interface CourseProgress {
  course: number;
  last_position: number;
  duration: number;
  is_finished: boolean;
  updated_at: string | null;
}

export interface LearningDay {
  date: string;
  course: number;
  watched_seconds: number;
  completions: number;
  elo_earned: number;
}

export interface LearningActivity {
  today: string;
  tracking_started_at: string | null;
  days: LearningDay[];
  totals: Omit<LearningDay, 'date'>[];
}

export interface WatchLater { course: number; created_at: string; }

export const LEARNING_TIME_ZONE = 'Asia/Shanghai';

export function learningDate(date = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: LEARNING_TIME_ZONE, year: 'numeric', month: '2-digit', day: '2-digit' }).format(date);
}

export type CourseGrouping = 'module' | 'subject' | 'tag' | 'album';

export function courseGroups(course: Course, grouping: CourseGrouping): string[] {
  if (grouping === 'module') return [String(course.module ?? 'unassigned'), JSON.stringify([course.subject_name || course.subject || '待归类学科', course.module ?? null])];
  if (grouping === 'tag') return course.tags?.length ? course.tags : ['未标记'];
  if (grouping === 'album') return [course.album_name || '未分专辑', JSON.stringify([course.module ?? null, course.album_name || ''])];
  return [course.subject_name || course.subject || '待归类学科'];
}

export function matchesSearch(course: Course, query: string): boolean {
  return [course.title, course.description, course.module_name, course.subject_name, course.subject, course.album_name, ...(course.tags || [])].join(' ').toLocaleLowerCase().includes(query.trim().toLocaleLowerCase());
}

export function playbackTime(seconds: number): string {
  const value = Math.max(0, Math.floor(seconds));
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, '0')}`;
}
