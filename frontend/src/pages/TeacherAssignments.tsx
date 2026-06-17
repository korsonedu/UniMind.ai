/**
 * 教师端 — 作业管理。
 * 查看所有已发布的作业，查看提交状态。
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Spinner, ClipboardText, Check, Clock, Users, CaretDown, CaretUp } from '@phosphor-icons/react';
import api from '@/lib/api';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';

interface TeacherAssignment {
  id: number;
  title: string;
  status: 'published' | 'draft' | 'closed';
  due_date: string | null;
  question_count: number;
  submitted_count: number;
  graded_count: number;
  total_students: number;
  created_at: string;
}

const STATUS_COLORS: Record<string, string> = {
  published: 'bg-blue-50 text-blue-600 border-blue-200',
  draft: 'bg-gray-50 text-gray-500 border-gray-200',
  closed: 'bg-red-50 text-red-500 border-red-200',
};

const STATUS_LABELS: Record<string, string> = {
  published: '已发布',
  draft: '草稿',
  closed: '已关闭',
};

export function TeacherAssignments() {
  const [assignments, setAssignments] = useState<TeacherAssignment[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const fetchList = async () => {
    setLoading(true);
    try {
      const res = await api.get('/quizzes/teacher-assignments/');
      setAssignments(res.data || []);
    } catch {
      toast.error('加载作业列表失败');
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchList();
  }, []);

  const toggleExpand = (id: number) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto p-4 md:p-6 space-y-4">
      <h1 className="text-lg font-bold">作业管理</h1>

      {assignments.length === 0 ? (
        <div className="text-center py-20 space-y-2">
          <ClipboardText className="h-10 w-10 mx-auto text-muted-foreground/40" />
          <p className="text-sm text-muted-foreground">暂无作业</p>
          <p className="text-xs text-muted-foreground/60">通过工作台 AI 助手布置作业后会显示在这里</p>
        </div>
      ) : (
        <div className="space-y-2">
          {assignments.map((a) => {
            const isExpanded = expandedId === a.id;
            const isOverdue = a.due_date && new Date(a.due_date) < new Date();
            return (
              <div
                key={a.id}
                className="rounded-xl border border-border bg-card overflow-hidden transition-colors"
              >
                {/* Header row */}
                <button
                  onClick={() => toggleExpand(a.id)}
                  className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-muted/30 transition-colors"
                >
                  <div
                    className={cn(
                      'h-8 w-8 rounded-lg flex items-center justify-center shrink-0',
                      a.status === 'published' && !isOverdue
                        ? 'bg-blue-50 text-blue-500'
                        : a.status === 'closed' || isOverdue
                        ? 'bg-red-50 text-red-500'
                        : 'bg-gray-100 text-gray-400'
                    )}
                  >
                    {a.status === 'published' && !isOverdue ? (
                      <Clock className="h-4 w-4" />
                    ) : (
                      <Check className="h-4 w-4" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-bold truncate">{a.title}</div>
                    <div className="text-xs text-muted-foreground mt-0.5 flex items-center gap-2">
                      <span>{a.question_count} 题</span>
                      <span>·</span>
                      <span className="flex items-center gap-1">
                        <Users className="h-3 w-3" />
                        {a.submitted_count}/{a.total_students} 已提交
                      </span>
                      {a.due_date && (
                        <>
                          <span>·</span>
                          <span>
                            截止 {new Date(a.due_date).toLocaleDateString('zh-CN')}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                  <Badge
                    variant="outline"
                    className={cn('text-[10px] font-bold shrink-0', STATUS_COLORS[a.status])}
                  >
                    {STATUS_LABELS[a.status]}
                  </Badge>
                  {isExpanded ? (
                    <CaretUp className="h-4 w-4 text-muted-foreground shrink-0" />
                  ) : (
                    <CaretDown className="h-4 w-4 text-muted-foreground shrink-0" />
                  )}
                </button>

                {/* Expanded detail */}
                {isExpanded && (
                  <div className="border-t border-border px-4 py-3 space-y-2 bg-muted/20">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      <div>
                        <p className="text-[10px] text-muted-foreground font-bold uppercase">题目数</p>
                        <p className="text-sm font-bold">{a.question_count}</p>
                      </div>
                      <div>
                        <p className="text-[10px] text-muted-foreground font-bold uppercase">已提交</p>
                        <p className="text-sm font-bold">
                          {a.submitted_count}
                          <span className="text-xs text-muted-foreground font-normal">
                            /{a.total_students}
                          </span>
                        </p>
                      </div>
                      <div>
                        <p className="text-[10px] text-muted-foreground font-bold uppercase">已批改</p>
                        <p className="text-sm font-bold">
                          {a.graded_count}
                          <span className="text-xs text-muted-foreground font-normal">
                            /{a.submitted_count}
                          </span>
                        </p>
                      </div>
                      <div>
                        <p className="text-[10px] text-muted-foreground font-bold uppercase">创建时间</p>
                        <p className="text-sm font-bold">
                          {new Date(a.created_at).toLocaleDateString('zh-CN')}
                        </p>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
