import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Spinner, ArrowsClockwise, ArrowCounterClockwise, FloppyDisk } from '@phosphor-icons/react';
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
  { value: 'quizzes' },
  { value: 'ai_assistant' },
  { value: 'pipeline' },
];

const formatTime = (value?: string | number) => {
  if (!value) return '--';
  try {
    const d = typeof value === 'number' ? new Date(value * 1000) : new Date(value);
    return d.toLocaleString();
  } catch {
    return String(value);
  }
};

export const PromptTemplatesPanel: React.FC = () => {
  const { t } = useTranslation('maintenance');
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

  const namespaceLabel = (ns: string) => {
    const map: Record<string, string> = {
      quizzes: t('promptTemplates.namespaceQuizzes'),
      ai_assistant: t('promptTemplates.namespaceAssistant'),
      pipeline: t('promptTemplates.namespacePipeline'),
    };
    return map[ns] || ns;
  };

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
      toast.error(formatApiErrorToast(e, t('promptTemplates.listLoadFailed')));
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
      toast.error(formatApiErrorToast(e, t('promptTemplates.detailLoadFailed')));
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
      toast.success(t('promptTemplates.saved'));
      await fetchTemplateDetail(selectedTemplateName);
      await fetchTemplates();
    } catch (e) {
      toast.error(formatApiErrorToast(e, t('promptTemplates.saveFailed')));
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
      toast.success(t('promptTemplates.rolledBack'));
      await fetchTemplateDetail(selectedTemplateName);
      await fetchTemplates();
    } catch (e) {
      toast.error(formatApiErrorToast(e, t('promptTemplates.rollbackFailed')));
    } finally {
      setRolling(false);
    }
  };

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start text-left">
      <Card className="xl:col-span-3 p-5 rounded-3xl border border-black/[0.04] shadow-sm bg-white space-y-4">
        <div>
          <p className="text-[11px] font-bold text-black/40 uppercase tracking-widest">{t('promptTemplates.namespaceLabel')}</p>
          <div className="mt-2 flex gap-2">
            {NAMESPACE_OPTIONS.map((item) => (
              <Button
                key={item.value}
                variant={namespace === item.value ? 'default' : 'outline'}
                onClick={() => setNamespace(item.value)}
                className="h-8 rounded-xl text-[11px] font-bold px-3"
              >
                {namespaceLabel(item.value)}
              </Button>
            ))}
          </div>
        </div>
        <div className="flex items-center justify-between">
          <p className="text-[11px] font-bold text-black/40 uppercase tracking-widest">{t('promptTemplates.templateList')}</p>
          <Button variant="ghost" size="icon" className="h-7 w-7 rounded-lg" onClick={fetchTemplates}>
            {loadingList ? <Spinner className="w-3.5 h-3.5 animate-spin" /> : <ArrowsClockwise className="w-3.5 h-3.5 opacity-50" />}
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
              <p className="text-[11px] font-bold text-black/25 py-8 text-center">{t('promptTemplates.noTemplates')}</p>
            ) : null}
          </div>
        </ScrollArea>
      </Card>

      <Card className="xl:col-span-6 p-6 rounded-3xl border border-black/[0.04] shadow-sm bg-white space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-[11px] font-bold text-black/40 uppercase tracking-widest">{t('promptTemplates.templateEditor')}</p>
            <p className="text-sm font-bold text-slate-800 mt-1">{selectedTemplateName || t('promptTemplates.selectTemplate')}</p>
          </div>
          <div className="flex items-center gap-2">
            <Badge className="bg-slate-100 text-slate-600 border-none text-[10px] font-black rounded-lg h-6 px-3">
              {t('promptTemplates.currentVersion', { version: latestVersion })}
            </Badge>
            <Badge className={`border-none text-[10px] font-black rounded-lg h-6 px-3 ${dirty ? 'bg-amber-100 text-amber-700' : 'bg-emerald-100 text-emerald-700'}`}>
              {dirty ? t('promptTemplates.unsaved') : t('promptTemplates.synced')}
            </Badge>
          </div>
        </div>
        <Input
          value={changeNote}
          onChange={(e) => setChangeNote(e.target.value)}
          className="bg-slate-50 border-none h-10 rounded-xl font-bold text-xs"
          placeholder={t('promptTemplates.changeNotePlaceholder')}
        />
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          className="w-full rounded-2xl bg-slate-50 border border-black/[0.04] p-4 font-mono text-xs min-h-[520px]"
          placeholder={t('promptTemplates.contentPlaceholder')}
        />
        <div className="flex justify-end gap-2">
          <Button variant="outline" className="rounded-xl text-xs font-bold" onClick={() => setContent(originalContent)} disabled={!dirty}>
            {t('promptTemplates.revertChanges')}
          </Button>
          <Button className="rounded-xl text-xs font-bold bg-black text-white" onClick={handleSave} disabled={!selectedTemplateName || saving || loadingDetail}>
            {saving ? <Spinner className="w-4 h-4 animate-spin mr-2" /> : <FloppyDisk className="w-4 h-4 mr-2" />}
            {t('promptTemplates.saveNewVersion')}
          </Button>
        </div>
      </Card>

      <Card className="xl:col-span-3 p-5 rounded-3xl border border-black/[0.04] shadow-sm bg-white space-y-4">
        <div className="flex items-center justify-between">
          <p className="text-[11px] font-bold text-black/40 uppercase tracking-widest">{t('promptTemplates.versionHistory')}</p>
          <Button variant="ghost" size="icon" className="h-7 w-7 rounded-lg" onClick={() => selectedTemplateName && fetchTemplateDetail(selectedTemplateName)}>
            {loadingDetail ? <Spinner className="w-3.5 h-3.5 animate-spin" /> : <ArrowsClockwise className="w-3.5 h-3.5 opacity-50" />}
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
                <p className="text-[10px] font-bold text-slate-500 mt-1 truncate">{item.change_note || t('promptTemplates.noChangeNote')}</p>
                <p className="text-[10px] font-bold text-slate-400 mt-1">{item.created_by_username || 'system'} · {formatTime(item.created_at)}</p>
              </button>
            ))}
            {history.length === 0 ? <p className="text-[11px] font-bold text-black/25 py-8 text-center">{t('promptTemplates.noHistory')}</p> : null}
          </div>
        </ScrollArea>
        <Button
          onClick={handleRollback}
          disabled={!selectedTemplateName || !selectedHistoryId || rolling}
          className="w-full rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-700 text-white"
        >
          {rolling ? <Spinner className="w-4 h-4 animate-spin mr-2" /> : <ArrowCounterClockwise className="w-4 h-4 mr-2" />}
          {t('promptTemplates.rollbackToSelected')}
        </Button>
      </Card>
    </div>
  );
};
