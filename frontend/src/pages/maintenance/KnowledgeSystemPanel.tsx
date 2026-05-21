import { useEffect, useState, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation('maintenance');
  const [open, setOpen] = useState(depth < 2);
  const hasChildren = node.children && node.children.length > 0;

  const levelLabels: Record<string, string> = {
    sub: t('knowledgeSystem.levelSub'),
    ch: t('knowledgeSystem.levelCh'),
    sec: t('knowledgeSystem.levelSec'),
    kp: t('knowledgeSystem.levelKp'),
  };

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
          <button onClick={(e) => { e.stopPropagation(); setOpen(!open); }} className="shrink-0" aria-label={open ? 'Collapse' : 'Expand'}>
            {open ? <ChevronDown className="h-3 w-3 text-muted-foreground" /> : <ChevronRight className="h-3 w-3 text-muted-foreground" />}
          </button>
        ) : (
          <span className="w-3 shrink-0" />
        )}
        <Badge className={cn('text-[9px] px-1 py-0 leading-snug font-bold shrink-0', LEVEL_COLORS[node.level] || 'bg-muted')}>
          {levelLabels[node.level] || node.level}
        </Badge>
        <span className="font-bold text-[11px] truncate flex-1">{node.name}</span>
        {node.code && <span className="text-[9px] text-muted-foreground font-mono shrink-0">{node.code}</span>}
        {node.questions_count > 0 && (
          <span className="text-[9px] text-muted-foreground shrink-0">{t('knowledgeSystem.nodeQuestions', { count: node.questions_count })}</span>
        )}
        <div className="hidden group-hover:flex items-center gap-0.5 shrink-0">
          <button onClick={(e) => { e.stopPropagation(); onEdit(node); }} className="p-0.5 hover:bg-muted rounded" aria-label={`Edit ${node.name}`}>
            <Pencil className="h-2.5 w-2.5 text-muted-foreground" />
          </button>
          <button onClick={(e) => { e.stopPropagation(); onDelete(node); }} className="p-0.5 hover:bg-red-50 rounded" aria-label={`Delete ${node.name}`}>
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
  const { t } = useTranslation('maintenance');
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
    if (!form.name.trim()) { toast.error(t('knowledgeSystem.nameRequired')); return; }
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
        toast.success(t('knowledgeSystem.updated'));
      } else {
        await api.post('/quizzes/knowledge-points/', payload);
        toast.success(t('knowledgeSystem.created'));
      }
      onSaved();
      onClose();
    } catch (e: any) { toast.error(e.response?.data?.error || t('knowledgeSystem.saveFailed')); }
    setSaving(false);
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>{node ? t('knowledgeSystem.editNode') : t('knowledgeSystem.newNode')}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label className="text-[10px] font-bold uppercase text-muted-foreground">{t('knowledgeSystem.name')}</Label>
            <Input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} autoComplete="off" className="h-9 rounded-xl bg-muted/50 border-none font-bold text-sm" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="space-y-1">
              <Label className="text-[10px] font-bold uppercase text-muted-foreground">{t('knowledgeSystem.code')}</Label>
              <Input value={form.code} onChange={e => setForm({ ...form, code: e.target.value })} placeholder={t('knowledgeSystem.codePlaceholder')} autoComplete="off" className="h-9 rounded-xl bg-muted/50 border-none text-xs font-mono" />
            </div>
            <div className="space-y-1">
              <Label className="text-[10px] font-bold uppercase text-muted-foreground">{t('knowledgeSystem.level')}</Label>
              <Select value={form.level} onValueChange={v => setForm({ ...form, level: v })}>
                <SelectTrigger className="h-9 rounded-xl bg-muted/50 border-none text-xs"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="sub">{t('knowledgeSystem.levelSub')}</SelectItem>
                  <SelectItem value="ch">{t('knowledgeSystem.levelCh')}</SelectItem>
                  <SelectItem value="sec">{t('knowledgeSystem.levelSec')}</SelectItem>
                  <SelectItem value="kp">{t('knowledgeSystem.levelKp')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1">
            <Label className="text-[10px] font-bold uppercase text-muted-foreground">{t('knowledgeSystem.parentNode')}</Label>
            <Select value={form.parent} onValueChange={v => setForm({ ...form, parent: v })}>
              <SelectTrigger className="h-9 rounded-xl bg-muted/50 border-none text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="0">{t('knowledgeSystem.noParent')}</SelectItem>
                {parentOptions.map(p => (
                  <SelectItem key={p.id} value={String(p.id)}>{p.name} {p.code ? `(${p.code})` : ''}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label className="text-[10px] font-bold uppercase text-muted-foreground">{t('knowledgeSystem.description')}</Label>
            <Input value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} className="h-9 rounded-xl bg-muted/50 border-none text-xs" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" size="sm" onClick={onClose}>{t('knowledgeSystem.cancel')}</Button>
          <Button size="sm" onClick={handleSave} disabled={saving}>{saving ? t('knowledgeSystem.saving') : t('knowledgeSystem.save')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ── Main Panel ── */
export function KnowledgeSystemPanel() {
  const { t } = useTranslation('maintenance');
  const [tree, setTree] = useState<KPNode[]>([]);
  const [allNodes, setAllNodes] = useState<KPNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [editNode, setEditNode] = useState<KPNode | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [mdText, setMdText] = useState('');
  const [importing, setImporting] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const dragCounter = useRef(0);
  const dropRef = useRef<HTMLDivElement>(null);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation();
    if (e.type === 'dragenter') {
      dragCounter.current += 1;
      if (dragCounter.current === 1) setDragOver(true);
    } else if (e.type === 'dragleave') {
      dragCounter.current -= 1;
      if (dragCounter.current === 0) setDragOver(false);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation();
    dragCounter.current = 0;
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    if (!file.name.endsWith('.md') && !file.name.endsWith('.txt') && !file.name.endsWith('.markdown')) {
      toast.error('仅支持 .md / .txt / .markdown 文件');
      return;
    }
    setImporting(true);
    const fd = new FormData();
    fd.append('file', file);
    api.post('/quizzes/knowledge-points/import-md/', fd)
      .then(({ data }) => {
        toast.success(t('knowledgeSystem.importDone', { created: data.created, updated: data.updated }));
        fetchTree();
      })
      .catch((e: any) => toast.error(e.response?.data?.error || t('knowledgeSystem.importFailed')))
      .finally(() => setImporting(false));
  }, []);

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
    if (!confirm(t('knowledgeSystem.deleteConfirm', { name: node.name }))) return;
    try {
      await api.delete(`/quizzes/knowledge-points/${node.id}/`);
      toast.success(t('knowledgeSystem.deleted'));
      fetchTree();
    } catch (e: any) { toast.error(t('knowledgeSystem.deleteFailed')); }
  };

  const handleExportMD = async () => {
    try {
      const { data } = await api.get('/quizzes/knowledge-points/export-md/');
      const blob = new Blob([data.content], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = 'knowledge-tree.md'; a.click();
      URL.revokeObjectURL(url);
      toast.success(t('knowledgeSystem.exported'));
    } catch { toast.error(t('knowledgeSystem.exportFailed')); }
  };

  const handleImportMD = async () => {
    if (!mdText.trim()) { toast.error(t('knowledgeSystem.mdContentRequired')); return; }
    setImporting(true);
    try {
      const { data } = await api.post('/quizzes/knowledge-points/import-md/', { content: mdText });
      toast.success(t('knowledgeSystem.importDone', { created: data.created, updated: data.updated }));
      setMdText('');
      fetchTree();
    } catch (e: any) { toast.error(e.response?.data?.error || t('knowledgeSystem.importFailed')); }
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
      toast.success(t('knowledgeSystem.importDone', { created: data.created, updated: data.updated }));
      fetchTree();
    } catch (e: any) { toast.error(e.response?.data?.error || t('knowledgeSystem.importFailed')); }
    setImporting(false);
  };

  const selectedNode = allNodes.find(n => n.id === selectedId);

  const levelLabels: Record<string, string> = {
    sub: t('knowledgeSystem.levelSub'),
    ch: t('knowledgeSystem.levelCh'),
    sec: t('knowledgeSystem.levelSec'),
    kp: t('knowledgeSystem.levelKp'),
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 h-[calc(100vh-14rem)]">
      {/* Left: Tree */}
      <Card className="p-4 lg:col-span-2 flex flex-col min-h-0">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-extrabold text-foreground flex items-center gap-2">
            <BrainCircuit className="h-4 w-4 text-indigo-500" /> {t('knowledgeSystem.title')}
          </h3>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={fetchTree}>
              <RefreshCw className="h-3 w-3 mr-1" /> {t('knowledgeSystem.refresh')}
            </Button>
            <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={handleExportMD}>
              <Download className="h-3 w-3 mr-1" /> {t('knowledgeSystem.exportMd')}
            </Button>
            <Button variant="apple" size="sm" className="h-7 text-xs" onClick={() => setShowCreate(true)}>
              <Plus className="h-3 w-3 mr-1" /> {t('knowledgeSystem.create')}
            </Button>
          </div>
        </div>

        {loading ? (
          <div className="flex-1 flex items-center justify-center"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
        ) : tree.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground gap-2">
            <BrainCircuit className="h-10 w-10 opacity-20" />
            <p className="text-sm font-bold">{t('knowledgeSystem.noTree')}</p>
            <p className="text-xs">{t('knowledgeSystem.noTreeHint')}</p>
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
        <p className="text-[10px] text-muted-foreground mt-2 text-right">{t('knowledgeSystem.totalNodes', { count: allNodes.length })}</p>
      </Card>

      {/* Right: Detail + Import */}
      <ScrollArea className="min-h-0">
      <div className="space-y-4">
        {/* Detail */}
        {selectedNode ? (
          <Card className="p-4 space-y-2">
            <div className="flex items-center justify-between">
              <Badge className={cn('text-[9px] font-bold', LEVEL_COLORS[selectedNode.level] || 'bg-muted')}>
                {levelLabels[selectedNode.level] || selectedNode.level}
              </Badge>
              <div className="flex gap-1">
                <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => setEditNode(selectedNode)}>
                  <Pencil className="h-3 w-3" />
                </Button>
              </div>
            </div>
            <h4 className="text-sm font-extrabold text-foreground">{selectedNode.name}</h4>
            {selectedNode.code && <p className="text-xs font-mono text-muted-foreground">{selectedNode.code}</p>}
            {selectedNode.description && <p className="text-xs text-muted-foreground leading-relaxed">{selectedNode.description}</p>}
            <div className="flex items-center gap-3 text-[10px] text-muted-foreground pt-1">
              <span>{t('knowledgeSystem.questions', { count: selectedNode.questions_count })}</span>
              <span>{t('knowledgeSystem.children', { count: selectedNode.children?.length || 0 })}</span>
            </div>
          </Card>
        ) : (
          <Card className="p-4 text-center text-xs text-muted-foreground">
            <BrainCircuit className="h-6 w-6 mx-auto mb-1 opacity-30" />
            {t('knowledgeSystem.selectHint')}
          </Card>
        )}

        {/* MD Import */}
        <Card className="p-4 space-y-3">
          <h4 className="text-xs font-extrabold text-foreground flex items-center gap-1.5">
            <FileUp className="h-3.5 w-3.5 text-indigo-500" /> {t('knowledgeSystem.mdImport')}
          </h4>

          {/* Drag & drop zone */}
          <div
            ref={dropRef}
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            className={cn(
              'relative rounded-xl border-2 border-dashed transition-all duration-200',
              dragOver
                ? 'border-primary bg-primary/5 scale-[1.02] shadow-md'
                : 'border-muted-foreground/25 hover:border-primary/30 hover:bg-accent/30',
            )}
          >
            <div className="flex flex-col items-center justify-center py-5 px-4 pointer-events-none">
              {importing ? (
                <Loader2 className="h-6 w-6 animate-spin text-primary mb-1" />
              ) : dragOver ? (
                <FileUp className="h-6 w-6 text-primary mb-1" strokeWidth={1.5} />
              ) : (
                <Upload className="h-5 w-5 text-muted-foreground/50 mb-1" strokeWidth={1.5} />
              )}
              <p className="text-[11px] font-bold text-center">
                {dragOver ? '松开以导入文件' : t('knowledgeSystem.uploadMd')}
              </p>
              <p className="text-[9px] text-muted-foreground mt-0.5">
                支持 .md / .txt / .markdown
              </p>
            </div>
            <input
              type="file"
              accept=".md,.txt,.markdown"
              onChange={handleFileUpload}
              className="absolute inset-0 opacity-0 cursor-pointer"
            />
          </div>

          <p className="text-[10px] text-muted-foreground text-center">{t('knowledgeSystem.orPasteContent')}</p>
          <textarea
            value={mdText}
            onChange={e => setMdText(e.target.value)}
            placeholder={t('knowledgeSystem.mdPlaceholder')}
            className="w-full h-32 rounded-xl bg-muted/50 border-none p-3 text-xs font-mono resize-none"
          />
          <Button className="w-full h-9 rounded-xl text-xs font-bold" onClick={handleImportMD} disabled={importing}>
            {importing ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : <Check className="h-3.5 w-3.5 mr-1" />}
            {t('knowledgeSystem.importMd')}
          </Button>
          <div className="bg-muted/50 rounded-lg p-2 text-[9px] text-muted-foreground leading-relaxed">
            <p className="font-bold mb-1">{t('knowledgeSystem.formatHelp')}</p>
            <div dangerouslySetInnerHTML={{ __html: t('knowledgeSystem.formatDetail') }} />
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
