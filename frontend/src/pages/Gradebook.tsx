/**
 * 教师端 — 成绩册。
 * 班级选择 → 学生×作业矩阵表 → 班级统计。
 */
import { useEffect, useState } from 'react';
import { Spinner, Users, ClipboardText, ChartBar, GraduationCap } from '@phosphor-icons/react';
import api from '@/lib/api';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

interface ClassItem {
  id: number;
  name: string;
}

interface AssignmentColumn {
  id: number;
  title: string;
  max_score: number;
}

interface StudentRow {
  student_id: number;
  student_name: string;
  scores: Record<string, number | null>; // assignment_id → score
}

interface GradebookData {
  class_id: number;
  class_name: string;
  assignments: AssignmentColumn[];
  students: StudentRow[];
  stats: {
    class_average: number | null;
    submission_rate: number | null; // 0-100
    total_assignments: number;
    total_students: number;
  };
}

export function Gradebook() {
  const [classes, setClasses] = useState<ClassItem[]>([]);
  const [selectedClassId, setSelectedClassId] = useState<string>('');
  const [classesLoading, setClassesLoading] = useState(true);
  const [data, setData] = useState<GradebookData | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchClasses = async () => {
    setClassesLoading(true);
    try {
      const res = await api.get('/users/institution/me/classes/');
      setClasses(res.data || []);
    } catch {
      toast.error('加载班级列表失败');
    }
    setClassesLoading(false);
  };

  useEffect(() => {
    fetchClasses();
  }, []);

  const fetchGradebook = async (classId: string) => {
    setLoading(true);
    try {
      const res = await api.get('/users/institution/me/gradebook/', {
        params: { class_id: classId },
      });
      setData(res.data);
    } catch {
      toast.error('加载成绩册失败');
      setData(null);
    }
    setLoading(false);
  };

  useEffect(() => {
    if (selectedClassId) {
      fetchGradebook(selectedClassId);
    } else {
      setData(null);
    }
  }, [selectedClassId]);

  if (classesLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto p-4 md:p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">成绩册</h1>
        <Select value={selectedClassId} onValueChange={setSelectedClassId}>
          <SelectTrigger className="w-48">
            <SelectValue placeholder="选择班级" />
          </SelectTrigger>
          <SelectContent>
            {classes.map((c) => (
              <SelectItem key={c.id} value={String(c.id)}>
                {c.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {!selectedClassId && (
        <div className="text-center py-20 space-y-2">
          <GraduationCap className="h-10 w-10 mx-auto text-muted-foreground/40" />
          <p className="text-sm text-muted-foreground">请选择一个班级查看成绩册</p>
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center py-12">
          <Spinner className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {!loading && data && (
        <>
          {/* Stats row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
                  <Users className="h-3.5 w-3.5" />
                  学生数
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold">{data.stats.total_students}</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
                  <ClipboardText className="h-3.5 w-3.5" />
                  作业数
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold">{data.stats.total_assignments}</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
                  <ChartBar className="h-3.5 w-3.5" />
                  班级均分
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold">
                  {data.stats.class_average != null ? data.stats.class_average.toFixed(1) : '—'}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
                  <ChartBar className="h-3.5 w-3.5" />
                  提交率
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold">
                  {data.stats.submission_rate != null ? `${data.stats.submission_rate}%` : '—'}
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Grade matrix */}
          {data.assignments.length === 0 ? (
            <div className="text-center py-12 space-y-2">
              <ClipboardText className="h-10 w-10 mx-auto text-muted-foreground/40" />
              <p className="text-sm text-muted-foreground">该班级暂无作业</p>
            </div>
          ) : data.students.length === 0 ? (
            <div className="text-center py-12 space-y-2">
              <Users className="h-10 w-10 mx-auto text-muted-foreground/40" />
              <p className="text-sm text-muted-foreground">该班级暂无学生</p>
            </div>
          ) : (
            <div className="rounded-xl border border-border overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-muted/50 border-b border-border">
                      <th className="text-left px-4 py-3 font-bold text-muted-foreground sticky left-0 bg-muted/50 z-10">
                        学生
                      </th>
                      {data.assignments.map((a) => (
                        <th
                          key={a.id}
                          className="text-center px-3 py-3 font-bold text-muted-foreground whitespace-nowrap"
                          title={a.title}
                        >
                          <div className="text-xs max-w-[120px] truncate mx-auto">{a.title}</div>
                          <div className="text-[10px] text-muted-foreground/60">{a.max_score}分</div>
                        </th>
                      ))}
                      <th className="text-center px-3 py-3 font-bold text-muted-foreground whitespace-nowrap">
                        均分
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.students.map((student) => {
                      const scores = data.assignments
                        .map((a) => student.scores[String(a.id)])
                        .filter((s): s is number => s != null);
                      const avg =
                        scores.length > 0
                          ? scores.reduce((a, b) => a + b, 0) / scores.length
                          : null;
                      return (
                        <tr
                          key={student.student_id}
                          className="border-b border-border/50 hover:bg-muted/30 transition-colors"
                        >
                          <td className="px-4 py-2.5 font-medium whitespace-nowrap sticky left-0 bg-card">
                            {student.student_name}
                          </td>
                          {data.assignments.map((a) => {
                            const score = student.scores[String(a.id)];
                            return (
                              <td
                                key={a.id}
                                className={cn(
                                  'text-center px-3 py-2.5 tabular-nums',
                                  score == null
                                    ? 'text-muted-foreground/40'
                                    : 'font-medium'
                                )}
                              >
                                {score != null ? score : '—'}
                              </td>
                            );
                          })}
                          <td className="text-center px-3 py-2.5 font-bold tabular-nums">
                            {avg != null ? avg.toFixed(1) : '—'}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
