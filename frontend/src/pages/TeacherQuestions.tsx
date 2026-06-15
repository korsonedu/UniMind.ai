/**
 * 题库管理 — 题目列表 + 布置作业 dialog。
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { MagnifyingGlass, MagicWand, PaperPlaneTilt } from '@phosphor-icons/react';
import api from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

interface QuestionItem {
  id: number;
  text: string;
  q_type: string;
  difficulty_level: string;
  knowledge_point_name?: string;
  subject?: string;
}

interface ClassItem {
  id: number;
  name: string;
}

const TYPE_LABELS: Record<string, string> = {
  objective: '客观题', noun: '名词解释', short: '简答题', essay: '论述题', calculate: '计算题',
};
const DIFFICULTY_LABELS: Record<string, string> = {
  entry: '入门', easy: '简单', normal: '中等', hard: '困难', extreme: '极限',
};

export default function TeacherQuestions() {
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [qType, setQType] = useState('all');
  const [difficulty, setDifficulty] = useState('all');
  const [page, setPage] = useState(1);
  const [data, setData] = useState<{ total: number; results: QuestionItem[] }>({ total: 0, results: [] });
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());

  // ── Assignment dialog state ──
  const [assignOpen, setAssignOpen] = useState(false);
  const [assignTitle, setAssignTitle] = useState('');
  const [assignDueDate, setAssignDueDate] = useState('');
  const [assignPoints, setAssignPoints] = useState(1);
  const [assignClassIds, setAssignClassIds] = useState<number[]>([]);
  const [assignSubmitting, setAssignSubmitting] = useState(false);
  const [classes, setClasses] = useState<ClassItem[]>([]);

  const fetchQuestions = async (p = page) => {
    setLoading(true);
    try {
      const res = await api.get('/quizzes/admin/questions/', {
        params: {
          search: search || undefined,
          q_type: qType !== 'all' ? qType : undefined,
          difficulty: difficulty !== 'all' ? difficulty : undefined,
          page: p,
          page_size: 50,
        },
      });
      setData(res.data);
      setPage(p);
    } catch { toast.error('加载题库失败'); }
    setLoading(false);
  };

  useEffect(() => { fetchQuestions(1); }, [search, qType, difficulty]);

  const toggleSelect = (id: number) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const openAssignDialog = async () => {
    // 拉取班级列表
    try {
      const res = await api.get('/quizzes/classes/');
      setClasses(res.data || []);
    } catch { setClasses([]); }
    setAssignTitle('');
    setAssignDueDate('');
    setAssignPoints(1);
    setAssignClassIds([]);
    setAssignOpen(true);
  };

  const handleAssign = async () => {
    if (!assignTitle.trim()) { toast.error('请输入作业标题'); return; }
    setAssignSubmitting(true);
    try {
      await api.post('/quizzes/assignments/create/', {
        title: assignTitle.trim(),
        question_ids: Array.from(selected),
        class_ids: assignClassIds,
        due_date: assignDueDate || null,
        points_per_question: assignPoints,
      });
      toast.success(`已发布「${assignTitle.trim()}」共 ${selected.size} 题`);
      setAssignOpen(false);
      setSelected(new Set());
    } catch (e: any) {
      toast.error(e?.response?.data?.error || '发布失败');
    }
    setAssignSubmitting(false);
  };

  return (
    <div className="flex flex-col h-full p-4 md:p-6 space-y-4 max-w-5xl mx-auto w-full">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">题目管理</h1>
        <div className="flex items-center gap-2">
          {selected.size > 0 && (
            <Button size="sm" onClick={openAssignDialog}>
              <PaperPlaneTilt className="h-4 w-4 mr-1" /> 布置作业 ({selected.size})
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={() => navigate('/workbench')}>
            <MagicWand className="h-4 w-4 mr-1" /> AI 出题
          </Button>
        </div>
      </div>

      {/* Tab 内容 */}
      <div className="flex items-center gap-2">
            <div className="relative flex-1 max-w-sm">
              <MagnifyingGlass className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="搜索题目..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="pl-9 h-9"
              />
            </div>
            <Select value={qType} onValueChange={setQType}>
              <SelectTrigger className="w-28 h-9"><SelectValue placeholder="题型" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部题型</SelectItem>
                {Object.entries(TYPE_LABELS).map(([k, v]) => (
                  <SelectItem key={k} value={k}>{v}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={difficulty} onValueChange={setDifficulty}>
              <SelectTrigger className="w-28 h-9"><SelectValue placeholder="难度" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部难度</SelectItem>
                {Object.entries(DIFFICULTY_LABELS).map(([k, v]) => (
                  <SelectItem key={k} value={k}>{v}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex-1 overflow-y-auto space-y-1">
            {loading && <p className="text-sm text-muted-foreground text-center py-8">加载中...</p>}
            {!loading && data.results.length === 0 && (
              <p className="text-sm text-muted-foreground text-center py-8">暂无题目</p>
            )}
            {data.results.map(q => (
              <div
                key={q.id}
                className="flex items-start gap-3 p-3 rounded-lg border border-border hover:bg-muted/50 cursor-pointer transition-colors"
                onClick={() => toggleSelect(q.id)}
              >
                <input
                  type="checkbox"
                  checked={selected.has(q.id)}
                  onChange={() => toggleSelect(q.id)}
                  className="mt-1 shrink-0"
                />
                <div className="flex-1 min-w-0">
                  <p className="text-sm leading-relaxed line-clamp-2">{q.text}</p>
                  <div className="flex items-center gap-1.5 mt-1.5">
                    <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                      {TYPE_LABELS[q.q_type] || q.q_type}
                    </Badge>
                    <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                      {DIFFICULTY_LABELS[q.difficulty_level] || q.difficulty_level || '中等'}
                    </Badge>
                    {q.knowledge_point_name && (
                      <span className="text-[11px] text-muted-foreground">{q.knowledge_point_name}</span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {data.total > 50 && (
            <div className="flex items-center justify-center gap-2 pt-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => fetchQuestions(page - 1)}>
                上一页
              </Button>
              <span className="text-sm text-muted-foreground">{page}/{Math.ceil(data.total / 50)}</span>
              <Button variant="outline" size="sm" disabled={page >= Math.ceil(data.total / 50)} onClick={() => fetchQuestions(page + 1)}>
                下一页
              </Button>
            </div>
          )}

      {/* ── 布置作业 Dialog ── */}
      <Dialog open={assignOpen} onOpenChange={setAssignOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>布置作业 · 已选 {selected.size} 题</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <div className="space-y-1.5">
              <label className="text-xs font-bold text-foreground/80">作业标题</label>
              <Input
                placeholder="如：第三章课后练习"
                value={assignTitle}
                onChange={e => setAssignTitle(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-bold text-foreground/80">目标班级</label>
              {classes.length === 0 ? (
                <p className="text-xs text-muted-foreground">暂无班级，请在维护中心创建</p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {classes.map(c => (
                    <button
                      key={c.id}
                      onClick={() => setAssignClassIds(prev =>
                        prev.includes(c.id) ? prev.filter(id => id !== c.id) : [...prev, c.id]
                      )}
                      className={cn(
                        'px-2.5 py-1 rounded-md text-xs font-bold transition-colors border',
                        assignClassIds.includes(c.id)
                          ? 'bg-primary text-primary-foreground border-primary'
                          : 'bg-card text-foreground/70 border-border hover:border-primary/30'
                      )}
                    >
                      {c.name}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <label className="text-xs font-bold text-foreground/80">截止日期</label>
                <Input
                  type="date"
                  value={assignDueDate}
                  onChange={e => setAssignDueDate(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-bold text-foreground/80">每题分值</label>
                <Input
                  type="number"
                  min={1}
                  max={100}
                  value={assignPoints}
                  onChange={e => setAssignPoints(Math.max(1, parseInt(e.target.value) || 1))}
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAssignOpen(false)} disabled={assignSubmitting}>
              取消
            </Button>
            <Button onClick={handleAssign} disabled={assignSubmitting || !assignTitle.trim()}>
              {assignSubmitting ? '发布中...' : '发布作业'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
