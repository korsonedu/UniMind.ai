import { useEffect, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { ScrollArea } from '@/components/ui/scroll-area';
import api from '@/lib/api';
import { toast } from 'sonner';
import {
  BrainCircuit, Upload, Download, Plus, Pencil, Trash2, Loader2,
  ChevronRight, ChevronDown, FileText, FileUp, RefreshCw, Check,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface KPNode {
  id: number;
  code: string;
  name: string;
  level: string;
  prefix_category: string;
  description: string;
  parent: number | null;
  children: KPNode[];
  questions_count: number;
}

const LEVEL_LABELS: Record<string, string> = { sub: '学科', ch: '模块', sec: '篇章', kp: '考点' };
const LEVEL_COLORS: Record<string, string> = {
  sub: 'bg-indigo-100 text-indigo-700',
  ch: 'bg-blue-100 text-blue-700',
  sec: 'bg-emerald-100 text-emerald-700',
  kp: 'bg-amber-100 text-amber-700',
};

/* ── Tree Node ── */
function TreeNode({
  node, depth, selectedId, onSelect, onEdit, onDelete, onRefresh,
}: {
  node: KPNode; depth: number; selectedId: number | null;
  onSelect: (id: number) => void; onEdit: (node: KPNode) => void;
  onDelete: (node: KPNode) => void; onRefresh: () => void;
}) {
  const [open, setOpen] = useState(depth < 2);
  const hasChildren = node.children && node.children.length > 0;

  return (
    <div>
      <div
        className={cn(
          'flex items-center gap-1.5 px-2 py-1.5 rounded-lg cursor-pointer transition-colors group text-xs',
          selectedId === node.id ? 'bg-primary/8 text-primary' : 'hover:bg-muted',
        )}
        style={{ paddingLeft: `${depth * 16 + 8}px` }}
        onClick={() => onSelect(node.id)}
      >
        {hasChildren ? (
          <button onClick={(e) => { e.stopPropagation(); setOpen(!open); }} className="shrink-0">
            {open ? <ChevronDown className="h-3 w-3 text-muted-foreground" /> : <ChevronRight className="h-3 w-3 text-muted-foreground" />}
          </button>
        ) : (
          <span className="w-3 shrink-0" />
        )}
        <Badge className={cn('text-[9px] px-1 py-0 leading-snug font-bold shrink-0', LEVEL_COLORS[node.level] || 'bg-muted')}>
          {LEVEL_LABELS[node.level] || node.level}
        </Badge>
        <span className="font-bold text-[11px] truncate flex-1">{node.name}</span>
        {node.code && <span className="text-[9px] text-muted-foreground font-mono shrink-0">{node.code}</span>}
        {node.questions_count > 0 && (
          <span className="text-[9px] text-muted-foreground shrink-0">{node.questions_count}题</span>
        )}
        <div className="hidden group-hover:flex items-center gap-0.5 shrink-0">
          <button onClick={(e) => { e.stopPropagation(); onEdit(node); }} className="p-0.5 hover:bg-muted rounded">
            <Pencil className="h-2.5 w-2.5 text-muted-foreground" />
          </button>
          <button onClick={(e) => { e.stopPropagation(); onDelete(node); }} className="p-0.5 hover:bg-red-50 rounded">
            <Trash2 className="h-2.5 w-2.5 text-red-400" />
          </button>
        </div>
      </div>
      {open && hasChildren && (
        <div>
          {node.children.map((child) => (
            <TreeNode key={child.id} node={child} depth={depth + 1} selectedId={selectedId} onSelect={onSelect} onEdit={onEdit} onDelete={onDelete} onRefresh={onRefresh} />
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Edit Dialog ── */
function KPEditDialog({
  open, node, onClose, onSaved, parentOptions,
}: {
  open: boolean; node: KPNode | null; onClose: () => void; onSaved: () => void;
  parentOptions: KPNode[];
}) {
  const [form, setForm] = useState({ name: '', code: '', level: 'kp', description: '', parent: '0' });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (node) {
      setForm({
        name: node.name || '',
        code: node.code || '',
        level: node.level || 'kp',
        description: node.description || '',
        parent: node.parent ? String(node.parent) : '0',
      });
    } else {
      setForm({ name: '', code: '', level: 'kp', description: '', parent: '0' });
    }
  }, [node, open]);

  const handleSave = async () => {
    if (!form.name.trim()) { toast.error('名称不能为空'); return; }
    setSaving(true);
    try {
      const payload = {
        name: form.name.trim(),
        code: form.code.trim() || null,
        level: form.level,
        description: form.description.trim(),
        parent: form.parent === '0' ? null : parseInt(form.parent),
      };
      if (node) {
        await api.put(`/quizzes/knowledge-points/${node.id}/`, payload);
        toast.success('已更新');
      } else {
        await api.post('/quizzes/knowledge-points/', payload);
        toast.success('已创建');
      }
      onSaved();
      onClose();
    } catch (e: any) { toast.error(e.response?.data?.error || '保存失败'); }
    setSaving(false);
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>{node ? '编辑知识点' : '新建知识点'}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label className="text-[10px] font-bold uppercase text-muted-foreground">名称</Label>
            <Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} className="h-9 rounded-xl bg-muted/50 border-none font-bold text-sm" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <Label className="text-[10px] font-bold uppercase text-muted-foreground">编码</Label>
              <Input value={form.code} onChange={e => setForm({ ...form, code: e.target.value })} placeholder="如 MB-1-1" className="h-9 rounded-xl bg-muted/50 border-none text-xs font-mono" />
            </div>
            <div className="space-y-1">
              <Label className="text-[10px] font-bold uppercase text-muted-foreground">层级</Label>
              <Select value={form.level} onValueChange={v => setForm({ ...form, level: v })}>
                <SelectTrigger className="h-9 rounded-xl bg-muted/50 border-none text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="sub">学科</SelectItem>
                  <SelectItem value="ch">模块</SelectItem>
                  <SelectItem value="sec">篇章</SelectItem>
                  <SelectItem value="kp">考点</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1">
            <Label className="text-[10px] font-bold uppercase text-muted-foreground">父节点</Label>
            <Select value={form.parent} onValueChange={v => setForm({ ...form, parent: v })}>
              <SelectTrigger className="h-9 rounded-xl bg-muted/50 border-none text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="0">无（顶层）</SelectItem>
                {parentOptions.map(p => (
                  <SelectItem key={p.id} value={String(p.id)}>{p.name} {p.code ? `(${p.code})` : ''}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-[10px] font-bold uppercase text-muted-foreground">描述</Label>
            <Input value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} className="h-9 rounded-xl bg-muted/50 border-none text-xs" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" size="sm" onClick={onClose}>取消</Button>
          <Button size="sm" onClick={handleSave} disabled={saving}>{saving ? '保存中...' : '保存'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ── Main Panel ── */
export function KnowledgeSystemPanel() {
  const [tree, setTree] = useState<KPNode[]>([]);
  const [allNodes, setAllNodes] = useState<KPNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [editNode, setEditNode] = useState<KPNode | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [mdText, setMdText] = useState('');
  const [importing, setImporting] = useState(false);

  const fetchTree = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/quizzes/knowledge-points/');
      setTree(data);
      // Flatten tree for parent selector
      const flat: KPNode[] = [];
      const walk = (nodes: KPNode[]) => {
        for (const n of nodes) {
          flat.push(n);
          if (n.children) walk(n.children);
        }
      };
      walk(data);
      setAllNodes(flat);
    } catch { /* */ }
    setLoading(false);
  };

  useEffect(() => { fetchTree(); }, []);

  const handleDelete = async (node: KPNode) => {
    if (!confirm(`删除「${node.name}」？子节点也会一并删除。`)) return;
    try {
      await api.delete(`/quizzes/knowledge-points/${node.id}/`);
      toast.success('已删除');
      fetchTree();
    } catch (e: any) { toast.error('删除失败'); }
  };

  const handleExportMD = async () => {
    try {
      const { data } = await api.get('/quizzes/knowledge-points/export-md/');
      const blob = new Blob([data.content], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = 'knowledge-tree.md'; a.click();
      URL.revokeObjectURL(url);
      toast.success('已导出');
    } catch { toast.error('导出失败'); }
  };

  const handleImportMD = async () => {
    if (!mdText.trim()) { toast.error('请输入 Markdown 内容'); return; }
    setImporting(true);
    try {
      const { data } = await api.post('/quizzes/knowledge-points/import-md/', { content: mdText });
      toast.success(`导入完成：新建 ${data.created} 个，更新 ${data.updated} 个`);
      setMdText('');
      fetchTree();
    } catch (e: any) { toast.error(e.response?.data?.error || '导入失败'); }
    setImporting(false);
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const { data } = await api.post('/quizzes/knowledge-points/import-md/', fd);
      toast.success(`导入完成：新建 ${data.created} 个，更新 ${data.updated} 个`);
      fetchTree();
    } catch (e: any) { toast.error(e.response?.data?.error || '导入失败'); }
    setImporting(false);
  };

  const selectedNode = allNodes.find(n => n.id === selectedId);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 h-[calc(100vh-14rem)]">
      {/* Left: Tree */}
      <Card className="p-4 lg:col-span-2 flex flex-col min-h-0">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-extrabold text-[#1D1D1F] flex items-center gap-2">
            <BrainCircuit className="h-4 w-4 text-indigo-500" /> 知识体系
          </h3>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={fetchTree}>
              <RefreshCw className="h-3 w-3 mr-1" /> 刷新
            </Button>
            <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={handleExportMD}>
              <Download className="h-3 w-3 mr-1" /> 导出 MD
            </Button>
            <Button variant="apple" size="sm" className="h-7 text-xs" onClick={() => setShowCreate(true)}>
              <Plus className="h-3 w-3 mr-1" /> 新建
            </Button>
          </div>
        </div>

        {loading ? (
          <div className="flex-1 flex items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
        ) : tree.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground gap-2">
            <BrainCircuit className="h-10 w-10 opacity-20" />
            <p className="text-sm font-bold">暂无知识体系</p>
            <p className="text-xs">通过 Markdown 导入或手动创建知识点</p>
          </div>
        ) : (
          <ScrollArea className="flex-1 -mx-2">
            <div className="space-y-0.5 pr-2">
              {tree.map(node => (
                <TreeNode key={node.id} node={node} depth={0} selectedId={selectedId} onSelect={setSelectedId} onEdit={setEditNode} onDelete={handleDelete} onRefresh={fetchTree} />
              ))}
            </div>
          </ScrollArea>
        )}
        <p className="text-[10px] text-muted-foreground mt-2 text-right">{allNodes.length} 个知识点</p>
      </Card>

      {/* Right: Detail + Import */}
      <ScrollArea className="min-h-0">
      <div className="space-y-4">
        {/* Detail */}
        {selectedNode ? (
          <Card className="p-4 space-y-2">
            <div className="flex items-center justify-between">
              <Badge className={cn('text-[9px] font-bold', LEVEL_COLORS[selectedNode.level] || 'bg-muted')}>
                {LEVEL_LABELS[selectedNode.level] || selectedNode.level}
              </Badge>
              <div className="flex gap-1">
                <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => setEditNode(selectedNode)}>
                  <Pencil className="h-3 w-3" />
                </Button>
              </div>
            </div>
            <h4 className="text-sm font-extrabold text-[#1D1D1F]">{selectedNode.name}</h4>
            {selectedNode.code && <p className="text-xs font-mono text-muted-foreground">{selectedNode.code}</p>}
            {selectedNode.description && <p className="text-xs text-muted-foreground leading-relaxed">{selectedNode.description}</p>}
            <div className="flex items-center gap-3 text-[10px] text-muted-foreground pt-1">
              <span>题目: {selectedNode.questions_count}</span>
              <span>子节点: {selectedNode.children?.length || 0}</span>
            </div>
          </Card>
        ) : (
          <Card className="p-4 text-center text-xs text-muted-foreground">
            <BrainCircuit className="h-6 w-6 mx-auto mb-1 opacity-30" />
            选择左侧知识点查看详情
          </Card>
        )}

        {/* MD Import */}
        <Card className="p-4 space-y-3">
          <h4 className="text-xs font-extrabold text-[#1D1D1F] flex items-center gap-1.5">
            <FileUp className="h-3.5 w-3.5 text-indigo-500" /> Markdown 导入
          </h4>
          <div className="relative">
            <Button variant="outline" className="w-full h-12 rounded-xl border-dashed border-2 text-xs font-bold" asChild>
              <label>
                <Upload className="h-3.5 w-3.5 mr-1.5 opacity-40" />
                上传 .md 文件
                <input type="file" accept=".md,.txt" onChange={handleFileUpload} className="hidden" />
              </label>
            </Button>
          </div>
          <p className="text-[10px] text-muted-foreground text-center">或直接粘贴内容</p>
          <textarea
            value={mdText}
            onChange={e => setMdText(e.target.value)}
            placeholder={`# MB - 货币银行学\n## MB-1 - 货币的起源\n### MB-1-1 - 商品交换\n#### MB-1-1-1 - 一般等价物`}
            className="w-full h-32 rounded-xl bg-muted/50 border-none p-3 text-xs font-mono resize-none"
          />
          <Button className="w-full h-9 rounded-xl text-xs font-bold" onClick={handleImportMD} disabled={importing}>
            {importing ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : <Check className="h-3.5 w-3.5 mr-1" />}
            导入 Markdown
          </Button>
          <div className="bg-muted/50 rounded-lg p-2 text-[9px] text-muted-foreground leading-relaxed">
            <p className="font-bold mb-1">格式说明：</p>
            <code># 学科名</code> → 学科 &nbsp; <code>## CODE - 模块</code> → 模块<br />
            <code>### CODE - 篇章</code> → 篇章 &nbsp; <code>#### CODE - 考点</code> → 考点
          </div>
        </Card>
      </div>
      </ScrollArea>

      <KPEditDialog
        open={showCreate || !!editNode}
        node={editNode}
        onClose={() => { setShowCreate(false); setEditNode(null); }}
        onSaved={fetchTree}
        parentOptions={allNodes}
      />
    </div>
  );
}
