import { useEffect, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import api from '@/lib/api';
import { Loader2, Copy, Plus, Ticket } from 'lucide-react';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

interface InviteCode {
  id: number;
  code: string;
  code_type: 'trial' | 'formal';
  plan: string;
  plan_label: string;
  duration_days: number;
  max_uses: number;
  used_count: number;
  is_active: boolean;
  is_exhausted: boolean;
  note: string;
  created_at: string;
  created_by: string;
}

const PLAN_COLORS: Record<string, string> = {
  free: 'bg-unimind-text-quaternary',
  starter: 'bg-primary',
  growth: 'bg-unimind-green',
  enterprise: 'bg-amber-500',
};

const TYPE_COLORS: Record<string, string> = {
  trial: 'bg-blue-500',
  formal: 'bg-emerald-600',
};

const DEFAULT_DURATION_DAYS = 30;

function formatDuration(days: number) {
  return days === 0 ? '永久' : `${days}天`;
}

export default function InviteCodeAdmin() {
  const [codes, setCodes] = useState<InviteCode[]>([]);
  const [loading, setLoading] = useState(true);
  const [codeType, setCodeType] = useState<'trial' | 'formal'>('trial');
  const [plan, setPlan] = useState('growth');
  const [count, setCount] = useState(1);
  const [maxUses, setMaxUses] = useState(1);
  const [durationDays, setDurationDays] = useState(DEFAULT_DURATION_DAYS);
  const [note, setNote] = useState('');
  const [generating, setGenerating] = useState(false);
  const [generated, setGenerated] = useState<string[]>([]);

  const isTrial = codeType === 'trial';

  const fetchCodes = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/users/admin/plan-invite-codes/');
      setCodes(data);
    } catch { toast.error('加载邀请码失败'); }
    setLoading(false);
  };

  useEffect(() => { fetchCodes(); }, []);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const { data } = await api.post('/users/admin/plan-invite-codes/generate/', {
        code_type: codeType,
        plan: isTrial ? 'growth' : plan,
        count,
        max_uses: maxUses,
        duration_days: isTrial ? 7 : durationDays,
        note,
      });
      setGenerated(data.codes.map((c: any) => c.code));
      fetchCodes();
      toast.success(`已生成 ${data.generated} 条${isTrial ? '试用' : '正式'}邀请码`);
    } catch { toast.error('生成邀请码失败，请重试'); }
    setGenerating(false);
  };

  const handleDeactivate = async (id: number) => {
    await api.post(`/users/admin/plan-invite-codes/${id}/deactivate/`);
    fetchCodes();
  };

  const copyCode = (code: string) => {
    navigator.clipboard.writeText(code);
    toast.success('已复制');
  };

  const activeCount = codes.filter(c => c.is_active && !c.is_exhausted).length;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold text-foreground tracking-tight">邀请码管理</h1>
        <p className="text-sm text-unimind-text-tertiary mt-1">{activeCount} 条可用</p>
      </div>

      {/* Generator */}
      <Card variant="apple" className="p-5">
        <h3 className="text-sm font-extrabold text-foreground mb-4 flex items-center gap-2">
          <Plus className="h-4 w-4" /> 生成邀请码
        </h3>
        <div className="flex items-end gap-2.5 flex-wrap">
          <div className="space-y-1">
            <p className="text-[10px] font-bold text-unimind-text-quaternary uppercase">类型</p>
            <select value={codeType} onChange={e => setCodeType(e.target.value as 'trial' | 'formal')}
              className="h-10 rounded-xl border border-border bg-background px-3 text-sm font-bold">
              <option value="trial">试用码</option>
              <option value="formal">正式码</option>
            </select>
          </div>
          <div className="space-y-1">
            <p className="text-[10px] font-bold text-unimind-text-quaternary uppercase">方案</p>
            <select value={isTrial ? 'growth' : plan} onChange={e => setPlan(e.target.value)}
              disabled={isTrial}
              className={cn("h-10 rounded-xl border border-border bg-background px-3 text-sm font-bold", isTrial && "opacity-50 cursor-not-allowed")}>
              <option value="free">Free 免费</option>
              <option value="starter">Starter 入门</option>
              <option value="growth">Growth 成长</option>
              <option value="enterprise">Enterprise 企业</option>
            </select>
          </div>
          <div className="space-y-1">
            <p className="text-[10px] font-bold text-unimind-text-quaternary uppercase">有效期(天)</p>
            <Input type="number" min={0} max={3650} value={isTrial ? 7 : durationDays}
              onChange={e => setDurationDays(parseInt(e.target.value, 10) || 0)}
              disabled={isTrial}
              className={cn("h-10 w-22 rounded-xl text-sm", isTrial && "opacity-50 cursor-not-allowed")} />
          </div>
          <div className="space-y-1">
            <p className="text-[10px] font-bold text-unimind-text-quaternary uppercase">数量</p>
            <Input type="number" min={1} max={100} value={count}
              onChange={e => setCount(parseInt(e.target.value, 10) || 1)}
              className="h-10 w-20 rounded-xl text-sm" />
          </div>
          <div className="space-y-1">
            <p className="text-[10px] font-bold text-unimind-text-quaternary uppercase">可用次数</p>
            <Input type="number" min={1} max={1000} value={maxUses}
              onChange={e => setMaxUses(parseInt(e.target.value) || 1)}
              className="h-10 w-20 rounded-xl text-sm" />
          </div>
          <div className="space-y-1 flex-1 min-w-[120px]">
            <p className="text-[10px] font-bold text-unimind-text-quaternary uppercase">备注</p>
            <Input placeholder="" value={note}
              onChange={e => setNote(e.target.value)}
              className="h-10 rounded-xl text-sm" />
          </div>
          <Button variant="apple" onClick={handleGenerate} disabled={generating} className="h-10">
            {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : '生成'}
          </Button>
        </div>
        {isTrial && (
          <p className="text-[11px] text-muted-foreground mt-2">试用码固定为 Growth 方案 7 天，无法修改。</p>
        )}

        {generated.length > 0 && (
          <div className="mt-4 bg-unimind-green/6 border border-unimind-green/20 rounded-xl p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-extrabold text-unimind-green">新生成 {generated.length} 条</span>
              <Button variant="ghost" size="sm" className="h-6 text-[10px]"
                onClick={() => { navigator.clipboard.writeText(generated.join('\n')); toast.success('已复制全部'); }}>
                一键复制
              </Button>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {generated.map(c => (
                <code key={c} className="font-mono text-xs font-bold bg-white px-2.5 py-1 rounded-lg border cursor-pointer hover:bg-unimind-bg-secondary"
                  onClick={() => copyCode(c)}>{c}</code>
              ))}
            </div>
          </div>
        )}
      </Card>

      {/* Code list */}
      <Card variant="apple" className="p-5">
        <h3 className="text-sm font-extrabold text-foreground mb-4 flex items-center gap-2">
          <Ticket className="h-4 w-4" /> 全部邀请码
        </h3>
        {loading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : codes.length === 0 ? (
          <p className="text-xs text-unimind-text-quaternary text-center py-8">暂无邀请码，先生成几条</p>
        ) : (
          <div className="space-y-1.5">
            {codes.map(c => (
              <div key={c.id} className="flex items-center justify-between py-2.5 px-3 rounded-xl hover:bg-unimind-bg-secondary text-sm">
                <div className="flex items-center gap-3 min-w-0">
                  <code className="font-mono font-extrabold text-foreground cursor-pointer select-all">{c.code}</code>
                  <Badge className={cn('text-[10px] font-bold text-white shrink-0', TYPE_COLORS[c.code_type] || 'bg-gray-400')}>
                    {c.code_type === 'trial' ? '试用' : '正式'}
                  </Badge>
                  <Badge className={cn('text-[10px] font-bold text-white shrink-0', PLAN_COLORS[c.plan] || 'bg-unimind-text-quaternary')}>
                    {c.plan_label}
                  </Badge>
                  <span className="text-[10px] font-bold text-unimind-text-quaternary">
                    {formatDuration(c.duration_days)}
                  </span>
                  <span className={cn('text-xs font-bold', c.is_exhausted ? 'text-red-400' : 'text-unimind-text-quaternary')}>
                    {c.used_count}/{c.max_uses}
                  </span>
                  {c.note && <span className="text-xs text-unimind-text-quaternary truncate hidden sm:inline">{c.note}</span>}
                  <span className="text-[10px] text-unimind-text-quaternary hidden sm:inline">{c.created_at?.slice(0, 10)}</span>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => copyCode(c.code)}>
                    <Copy className="h-3.5 w-3.5 text-unimind-text-quaternary" />
                  </Button>
                  {(!c.is_active || c.is_exhausted) ? (
                    <span className="text-[10px] text-unimind-text-quaternary font-bold">
                      {!c.is_active ? '已停用' : '已用完'}
                    </span>
                  ) : (
                    <Button variant="ghost" size="sm" className="h-7 text-[11px] text-red-400"
                      onClick={() => handleDeactivate(c.id)}>停用</Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
