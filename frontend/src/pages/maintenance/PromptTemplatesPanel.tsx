import React, { useEffect, useMemo, useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Loader2, RefreshCw, RotateCcw, Save } from 'lucide-react';
import api from '@/lib/api';
import { formatApiErrorToast } from '@/lib/apiError';
import { toast } from 'sonner';

type TemplateListItem = {
  namespace: string;
  template_name: string;
  latest_version: number;
  updated_at?: string | number;
};

type TemplateHistoryItem = {
  id: number;
  version: number;
  change_note: string;
  created_by_username: string;
  created_at: string;
};

const NAMESPACE_OPTIONS = [
  { value: 'quizzes', label: '题库模板' },
  { value: 'ai_assistant', label: '助手模板' },
  { value: 'pipeline', label: '出题管线' },
];

const formatTime = (value?: string | number) => {
  if (!value) return '--';
  try {
    const d = typeof value === 'number' ? new Date(value * 1000) : new Date(value);
    return d.toLocaleString('zh-CN');
  } catch {
    return String(value);
  }
};

export const PromptTemplatesPanel: React.FC = () => {
  const [namespace, setNamespace] = useState('quizzes');
  const [templates, setTemplates] = useState<TemplateListItem[]>([]);
  const [selectedTemplateName, setSelectedTemplateName] = useState('');
  const [loadingList, setLoadingList] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [saving, setSaving] = useState(false);
  const [rolling, setRolling] = useState(false);
  const [content, setContent] = useState('');
  const [originalContent, setOriginalContent] = useState('');
  const [changeNote, setChangeNote] = useState('');
  const [latestVersion, setLatestVersion] = useState(0);
  const [history, setHistory] = useState<TemplateHistoryItem[]>([]);
  const [selectedHistoryId, setSelectedHistoryId] = useState<number | null>(null);

  const dirty = useMemo(() => content !== originalContent, [content, originalContent]);

  const fetchTemplates = async () => {
    setLoadingList(true);
    try {
      const res = await api.get('/quizzes/admin/prompt-templates/', { params: { namespace } });
      const list = (res.data?.results || []) as TemplateListItem[];
      setTemplates(list);
      if (list.length === 0) {
        setSelectedTemplateName('');
        setContent('');
        setOriginalContent('');
        setHistory([]);
        setLatestVersion(0);
        return;
      }
      if (!list.find((x) => x.template_name === selectedTemplateName)) {
        setSelectedTemplateName(list[0].template_name);
      }
    } catch (e) {
      toast.error(formatApiErrorToast(e, '模板列表加载失败'));
    } finally {
      setLoadingList(false);
    }
  };

  const fetchTemplateDetail = async (templateName: string) => {
    if (!templateName) return;
    setLoadingDetail(true);
    try {
      const res = await api.get('/quizzes/admin/prompt-templates/detail/', {
        params: { namespace, template_name: templateName },
      });
      const detail = res.data || {};
      setContent(String(detail.content || ''));
      setOriginalContent(String(detail.content || ''));
      setLatestVersion(Number(detail.latest_version || 0));
      const rows = (detail.history || []) as TemplateHistoryItem[];
      setHistory(rows);
      setSelectedHistoryId(rows[0]?.id ?? null);
      setChangeNote('');
    } catch (e) {
      toast.error(formatApiErrorToast(e, '模板详情加载失败'));
    } finally {
      setLoadingDetail(false);
    }
  };

  useEffect(() => {
    fetchTemplates();
  }, [namespace]);

  useEffect(() => {
    if (selectedTemplateName) {
      fetchTemplateDetail(selectedTemplateName);
    }
  }, [selectedTemplateName]);

  const handleSave = async () => {
    if (!selectedTemplateName) return;
    setSaving(true);
    try {
      await api.put('/quizzes/admin/prompt-templates/detail/', {
        namespace,
        template_name: selectedTemplateName,
        content,
        change_note: changeNote,
      });
      toast.success('模板已保存并生成新版本');
      await fetchTemplateDetail(selectedTemplateName);
      await fetchTemplates();
    } catch (e) {
      toast.error(formatApiErrorToast(e, '模板保存失败'));
    } finally {
      setSaving(false);
    }
  };

  const handleRollback = async () => {
    if (!selectedTemplateName || !selectedHistoryId) return;
    setRolling(true);
    try {
      await api.post('/quizzes/admin/prompt-templates/rollback/', {
        namespace,
        template_name: selectedTemplateName,
        version_id: selectedHistoryId,
      });
      toast.success('已回滚到指定版本并生成新版本记录');
      await fetchTemplateDetail(selectedTemplateName);
      await fetchTemplates();
    } catch (e) {
      toast.error(formatApiErrorToast(e, '回滚失败'));
    } finally {
      setRolling(false);
    }
  };

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start text-left">
      <Card className="xl:col-span-3 p-5 rounded-3xl border border-black/[0.04] shadow-sm bg-white space-y-4">
        <div>
          <p className="text-[11px] font-bold text-black/40 uppercase tracking-widest">模板命名空间</p>
          <div className="mt-2 flex gap-2">
            {NAMESPACE_OPTIONS.map((item) => (
              <Button
                key={item.value}
                variant={namespace === item.value ? 'default' : 'outline'}
                onClick={() => setNamespace(item.value)}
                className="h-8 rounded-xl text-[11px] font-bold px-3"
              >
                {item.label}
              </Button>
            ))}
          </div>
        </div>
        <div className="flex items-center justify-between">
          <p className="text-[11px] font-bold text-black/40 uppercase tracking-widest">模板列表</p>
          <Button variant="ghost" size="icon" className="h-7 w-7 rounded-lg" onClick={fetchTemplates}>
            {loadingList ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5 opacity-50" />}
          </Button>
        </div>
        <ScrollArea className="h-[520px] pr-2">
          <div className="space-y-1.5">
            {templates.map((item) => (
              <button
                key={`${item.namespace}:${item.template_name}`}
                onClick={() => setSelectedTemplateName(item.template_name)}
                className={`w-full text-left rounded-xl px-3 py-2 border transition ${
                  selectedTemplateName === item.template_name
                    ? 'bg-indigo-50 border-indigo-200'
                    : 'bg-slate-50 border-transparent hover:border-black/10'
                }`}
              >
                <p className="text-[11px] font-bold text-slate-800 truncate">{item.template_name}</p>
                <p className="text-[10px] font-bold text-slate-400 mt-1">v{item.latest_version}</p>
              </button>
            ))}
            {!loadingList && templates.length === 0 ? (
              <p className="text-[11px] font-bold text-black/25 py-8 text-center">暂无模板</p>
            ) : null}
          </div>
        </ScrollArea>
      </Card>

      <Card className="xl:col-span-6 p-6 rounded-3xl border border-black/[0.04] shadow-sm bg-white space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-[11px] font-bold text-black/40 uppercase tracking-widest">模板编辑</p>
            <p className="text-sm font-bold text-slate-800 mt-1">{selectedTemplateName || '请选择模板'}</p>
          </div>
          <div className="flex items-center gap-2">
            <Badge className="bg-slate-100 text-slate-600 border-none text-[10px] font-black rounded-lg h-6 px-3">
              当前版本 v{latestVersion}
            </Badge>
            <Badge className={`border-none text-[10px] font-black rounded-lg h-6 px-3 ${dirty ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'}`}>
              {dirty ? '未保存' : '已同步'}
            </Badge>
          </div>
        </div>
        <Input
          value={changeNote}
          onChange={(e) => setChangeNote(e.target.value)}
          className="bg-slate-50 border-none h-10 rounded-xl font-bold text-xs"
          placeholder="变更说明（可选）"
        />
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          className="w-full rounded-2xl bg-slate-50 border border-black/[0.04] p-4 font-mono text-xs min-h-[520px]"
          placeholder="模板内容..."
        />
        <div className="flex justify-end gap-2">
          <Button variant="outline" className="rounded-xl text-xs font-bold" onClick={() => setContent(originalContent)} disabled={!dirty}>
            还原修改
          </Button>
          <Button className="rounded-xl text-xs font-bold bg-black text-white" onClick={handleSave} disabled={!selectedTemplateName || saving || loadingDetail}>
            {saving ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Save className="w-4 h-4 mr-2" />}
            保存新版本
          </Button>
        </div>
      </Card>

      <Card className="xl:col-span-3 p-5 rounded-3xl border border-black/[0.04] shadow-sm bg-white space-y-4">
        <div className="flex items-center justify-between">
          <p className="text-[11px] font-bold text-black/40 uppercase tracking-widest">版本历史</p>
          <Button variant="ghost" size="icon" className="h-7 w-7 rounded-lg" onClick={() => selectedTemplateName && fetchTemplateDetail(selectedTemplateName)}>
            {loadingDetail ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5 opacity-50" />}
          </Button>
        </div>
        <ScrollArea className="h-[500px] pr-2">
          <div className="space-y-1.5">
            {history.map((item) => (
              <button
                key={item.id}
                onClick={() => setSelectedHistoryId(item.id)}
                className={`w-full text-left rounded-xl border px-3 py-2 transition ${
                  selectedHistoryId === item.id ? 'bg-indigo-50 border-indigo-200' : 'bg-slate-50 border-transparent hover:border-black/10'
                }`}
              >
                <p className="text-[11px] font-bold text-slate-800">v{item.version}</p>
                <p className="text-[10px] font-bold text-slate-500 mt-1 truncate">{item.change_note || '无说明'}</p>
                <p className="text-[10px] font-bold text-slate-400 mt-1">{item.created_by_username || 'system'} · {formatTime(item.created_at)}</p>
              </button>
            ))}
            {history.length === 0 ? <p className="text-[11px] font-bold text-black/25 py-8 text-center">暂无版本历史</p> : null}
          </div>
        </ScrollArea>
        <Button
          onClick={handleRollback}
          disabled={!selectedTemplateName || !selectedHistoryId || rolling}
          className="w-full rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-700 text-white"
        >
          {rolling ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <RotateCcw className="w-4 h-4 mr-2" />}
          回滚到所选版本
        </Button>
      </Card>
    </div>
  );
};
