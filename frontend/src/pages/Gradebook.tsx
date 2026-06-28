/**
 * 教师端 — 成绩册。
 * 班级选择 → 学生×作业矩阵表 → 班级统计。
 */
import { useEffect, useState } from 'react';
import { Spinner, Users, ClipboardText, ChartBar, GraduationCap, MagnifyingGlass, FileCsv, SortAscending, SortDescending } from '@phosphor-icons/react';
import api from '@/lib/api';
import { cn } from '@/lib/utils';
import { PageWrapper } from '@/components/PageWrapper';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
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
  max_score: number | null;
}

interface ScoreItem {
  assignment_id: number;
  assignment_title: string;
  score: number | null;
  submitted: boolean;
  max_score: number | null;
}

interface StudentRow {
  id: number;
  name: string;
  scores: ScoreItem[];
  average: number | null;
}

interface GradebookData {
  class_id: number;
  class_name: string;
  assignments: AssignmentColumn[];
  students: StudentRow[];
  stats: {
    class_average: number | null;
    submission_rate: number | null;
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

  // Sort & search
  const [sortBy, setSortBy] = useState<string>('name');
  const [sortDir, setSortDir] = useState<string>('asc');
  const [search, setSearch] = useState('');

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

  const fetchGradebook = async (classId: string, sort_by?: string, sort_dir?: string, search_query?: string) => {
    setLoading(true);
    try {
      const params: Record<string, string> = { class_id: classId };
      if (sort_by) params.sort_by = sort_by;
      if (sort_dir) params.sort_dir = sort_dir;
      if (search_query) params.search = search_query;
      const res = await api.get('/users/institution/me/gradebook/', { params });
      setData(res.data);
    } catch {
      toast.error('加载成绩册失败');
      setData(null);
    }
    setLoading(false);
  };

  useEffect(() => {
    if (selectedClassId) {
      fetchGradebook(selectedClassId, sortBy, sortDir, search);
    } else {
      setData(null);
    }
  }, [selectedClassId]);

  const handleSort = (column: string) => {
    const newDir = sortBy === column && sortDir === 'asc' ? 'desc' : 'asc';
    setSortBy(column);
    setSortDir(newDir);
    if (selectedClassId) fetchGradebook(selectedClassId, column, newDir, search);
  };

  const handleSearch = (q: string) => {
    setSearch(q);
    if (selectedClassId) fetchGradebook(selectedClassId, sortBy, sortDir, q);
  };

  const handleExport = () => {
    if (!selectedClassId) return;
    window.open(`/api/users/institution/me/gradebook/?class_id=${selectedClassId}&format=csv`, '_blank');
  };

  const SortIcon = sortDir === 'asc' ? SortAscending : SortDescending;

  if (classesLoading) {
    return (
      <PageWrapper title="成绩册" subtitle="">
        <div className="max-w-6xl mx-auto flex items-center justify-center py-20">
          <Spinner className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      </PageWrapper>
    );
  }

  return (
    <PageWrapper title="成绩册" subtitle="">
      <div className="max-w-6xl mx-auto space-y-4 md:space-y-6">
        {/* Controls row */}
        <div className="flex items-center gap-3 flex-wrap">
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
          {selectedClassId && (
            <>
              <div className="relative flex-1 max-w-xs">
                <MagnifyingGlass className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="搜索学生..."
                  value={search}
                  onChange={e => handleSearch(e.target.value)}
                  className="pl-8 h-9 text-sm"
                />
              </div>
              <div className="flex-1" />
              <Button size="sm" variant="outline" onClick={handleExport}>
                <FileCsv className="h-4 w-4 mr-1" />导出 CSV
              </Button>
            </>
          )}
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
                      <th className="text-left px-4 py-3 sticky left-0 bg-muted/50 z-10">
                        <button
                          onClick={() => handleSort('name')}
                          className="flex items-center gap-1 font-bold text-muted-foreground hover:text-foreground transition-colors"
                        >
                          学生
                          {sortBy === 'name' && <SortIcon className="h-3 w-3" />}
                        </button>
                      </th>
                      {data.assignments.map((a) => (
                        <th
                          key={a.id}
                          className="text-center px-3 py-3 font-bold text-muted-foreground whitespace-nowrap"
                          title={a.title}
                        >
                          <div className="text-xs max-w-[120px] truncate mx-auto">{a.title}</div>
                          <div className="text-[10px] text-muted-foreground/60">{a.max_score != null ? `${a.max_score}分` : ''}</div>
                        </th>
                      ))}
                      <th className="text-center px-3 py-3 whitespace-nowrap">
                        <button
                          onClick={() => handleSort('average')}
                          className="flex items-center gap-1 font-bold text-muted-foreground hover:text-foreground transition-colors mx-auto"
                        >
                          均分
                          {sortBy === 'average' && <SortIcon className="h-3 w-3" />}
                        </button>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.students.map((student) => (
                      <tr
                        key={student.id}
                        className="border-b border-border/50 hover:bg-muted/30 transition-colors"
                      >
                        <td className="px-4 py-2.5 font-medium whitespace-nowrap sticky left-0 bg-card">
                          {student.name}
                        </td>
                        {student.scores.map((s) => (
                          <td
                            key={s.assignment_id}
                            className={cn(
                              'text-center px-3 py-2.5 tabular-nums',
                              s.score == null
                                ? 'text-muted-foreground/40'
                                : 'font-medium'
                            )}
                          >
                            {s.score != null ? s.score : '—'}
                          </td>
                        ))}
                        <td className="text-center px-3 py-2.5 font-bold tabular-nums">
                          {student.average != null ? student.average.toFixed(1) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
      </div>
    </PageWrapper>
  );
}
