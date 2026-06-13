/**
 * 资产管理 — 题目管理 + 图文题 tab 切换。
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { MagnifyingGlass, Plus, MagicWand, PaperPlaneTilt, Image } from '@phosphor-icons/react';
import api from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
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

const TYPE_LABELS: Record<string, string> = {
  objective: '客观题', noun: '名词解释', short: '简答题', essay: '论述题', calculate: '计算题',
};
const DIFFICULTY_LABELS: Record<string, string> = {
  entry: '入门', easy: '简单', normal: '中等', hard: '困难', extreme: '极限',
};

const TABS = [
  { key: 'questions', label: '题目管理' },
  { key: 'image', label: '图文题' },
] as const;

export default function TeacherQuestions() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<string>('questions');
  const [search, setSearch] = useState('');
  const [qType, setQType] = useState('all');
  const [difficulty, setDifficulty] = useState('all');
  const [page, setPage] = useState(1);
  const [data, setData] = useState<{ total: number; results: QuestionItem[] }>({ total: 0, results: [] });
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());

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

  return (
    <div className="flex flex-col h-full p-4 md:p-6 space-y-4 max-w-5xl mx-auto w-full">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-bold">题目管理</h1>
          {/* Tabs */}
          <div className="flex items-center gap-1 bg-muted rounded-lg p-0.5">
            {TABS.map(t => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={cn(
                  'px-3 py-1 text-xs font-bold rounded-md transition-colors',
                  tab === t.key
                    ? 'bg-card text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {selected.size > 0 && (
            <Button size="sm" onClick={() => {
              toast.info(`已选 ${selected.size} 道题。布置作业功能即将上线`);
            }}>
              <PaperPlaneTilt className="h-4 w-4 mr-1" /> 布置作业
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={() => toast.info('手动出题功能即将上线')}>
            <Plus className="h-4 w-4 mr-1" /> 手动出题
          </Button>
          <Button size="sm" onClick={() => navigate('/workbench')}>
            <MagicWand className="h-4 w-4 mr-1" /> AI 出题
          </Button>
        </div>
      </div>

      {/* Tab 内容 */}
      {tab === 'questions' ? (
        <>
          {/* Filters */}
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

          {/* Question list */}
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

          {/* Pagination */}
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
        </>
      ) : (
        /* 图文题 tab */
        <div className="flex-1 flex flex-col items-center justify-center text-center space-y-3">
          <Image className="h-12 w-12 text-muted-foreground/50" />
          <div>
            <p className="text-sm font-bold text-muted-foreground">图文题功能开发中</p>
            <p className="text-xs text-muted-foreground mt-1">支持题目中包含图片、图表等富媒体内容</p>
          </div>
        </div>
      )}
    </div>
  );
}
