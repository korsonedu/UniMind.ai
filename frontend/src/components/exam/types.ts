export type SubmissionStatus = 'not_submitted' | 'submitted' | 'graded';

export type MockExamItem = {
  id: number;
  status: 'processing' | 'ready' | 'failed';
  question_count: number;
  weak_coverage: number;
  error_message: string;
  created_at: string;
  exam_pdf_url: string;
  answer_pdf_url: string;
};

export type TeacherExamItem = {
  id: number;
  title: string;
  description: string;
  exam_pdf_url: string;
  created_at: string;
  submission: {
    id: number;
    answer_pdf_url: string;
    graded_pdf_url: string;
    score: number | null;
    feedback: string;
  } | null;
};

export type SubmissionItem = {
  id: number;
  student_name: string;
  student_email: string;
  answer_pdf_url: string;
  graded_pdf_url: string;
  score: number | null;
  feedback: string;
  created_at: string;
};
