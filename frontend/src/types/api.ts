export interface UserSummary {
  id: number;
  username: string;
  nickname: string;
  avatar_url: string;
  role: 'student' | 'admin';
  institution_role?: 'owner' | 'teacher' | 'student';
}

export interface KnowledgePoint {
  id: number;
  code: string;
  name: string;
  level: string;
  description: string;
  parent: number | null;
  children: KnowledgePoint[];
  order: number;
  questions_count: number;
  prefix_category?: string;
}

export interface QuizQuestion {
  id: number;
  text: string;
  q_type: 'objective' | 'subjective';
  subjective_type: string | null;
  difficulty: number;
  difficulty_level: string;
  difficulty_level_display: string;
  options: string[];
  knowledge_point: number | null;
  knowledge_point_detail: KnowledgePoint | null;
  is_favorite: boolean;
  is_mastered: boolean;
  correct_answer?: string;
  ai_answer?: string;
  grading_points?: string;
}

export interface QAAnswer {
  id: number;
  question: number;
  user: number;
  user_detail: UserSummary;
  content: string;
  is_teacher: boolean;
  likes_count: number;
  is_liked: boolean;
  created_at: string;
  updated_at: string;
}

export interface QAQuestion {
  id: number;
  user: number;
  user_detail: UserSummary;
  content: string;
  attachment: string | null;
  is_solved: boolean;
  is_starred: boolean;
  is_liked: boolean;
  is_followed: boolean;
  likes_count: number;
  reply_count: number;
  first_answer: QAAnswer | null;
  answers: QAAnswer[];
  created_at: string;
  updated_at: string;
}

export interface Article {
  author_display_name: string;
  views: number;
  excerpt?: string;
  view_count?: number;
  knowledge_point_name?: string;
  id: number;
  title: string;
  content: string;
  cover_image: string | null;
  description?: string;
  knowledge_point: number | null;
  tags: string[];
  author: number;
  author_detail?: UserSummary;
  created_at: string;
  updated_at: string;
}

export interface Album {
  id: number;
  name: string;
  description: string;
  cover_image: string | null;
  course_count: number;
  courses: { id: number; title: string; cover_image: string | null }[];
  created_at: string;
}

export interface CourseModule {
  id: number;
  name: string;
  is_public: boolean;
  description: string;
  sort_order: number;
  course_count: number;
}

export interface Course {
  id: number;
  title: string;
  description: string;
  album: Album | null;
  module: number | null;
  module_name: string;
  subject_name?: string;
  module_sort_order: number;
  album_obj?: number;
  knowledge_point: number | null;
  cover_image: string | null;
  video_file: string | null;
  courseware: string | null;
  reference_materials: string | null;
  elo_reward: number;
  ai_outline_enabled: boolean;
  sort_order: number;
  tags: { id: number; name: string; slug: string }[];
  progress: { last_position: number; is_finished: boolean } | null;
  created_at: string;
  updated_at: string;
}

export interface StartupMaterial {
  file_name?: string;
  file_size?: number;
  id: number;
  name: string;
  description: string;
  file: string;
  created_at: string;
}

export interface Bot {
  institution_name?: string;
  prompt_template_name?: string;
  prompt_file_exists?: boolean;
  id: number;
  name: string;
  avatar: string | null;
  bot_type: 'planner' | 'exam_generator';
  system_prompt: string;
  is_active: boolean;
  institution: number | null;
  institution_personality: Record<string, unknown>;
}

export interface GeneratedQuestion {
  question: string;
  q_type: string;
  subjective_type?: string | null;
  options?: string[] | Record<string, string> | null;
  answer?: string;
  answer_preview?: string;
  grading_points?: string[] | null;
  difficulty_level: string;
  kp_name: string;
  kp_code?: string;
  kp_id?: number;
}
