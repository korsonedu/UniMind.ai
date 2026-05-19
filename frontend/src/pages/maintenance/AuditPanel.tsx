import React from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { BookOpen, FileText, BrainCircuit, Rocket, X, Search, RefreshCcw, Edit3, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';

export const AuditPanel = ({ 
  auditMode, 
  setAuditMode, 
  qSearch, 
  setQSearch, 
  fetchLists, 
  courseList, 
  articleList, 
  kpList, 
  smList, 
  onEdit, 
  onDelete 
}: { 
  auditMode: string, 
  setAuditMode: (m: any) => void, 
  qSearch: string, 
  setQSearch: (s: string) => void, 
  fetchLists: () => void, 
  courseList: any[], 
  articleList: any[], 
  kpList: any[], 
  smList: any[], 
  onEdit: (type: string, data: any) => void, 
  onDelete: (type: string, id: number) => void
}) => {
  const { t } = useTranslation('maintenance');
  if (auditMode === 'hub') {
    return (
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 text-left">
        {[
          { id: 'courses', label: t('audit.hubCourses'), icon: BookOpen, color: 'text-emerald-600', bg: 'bg-emerald-50' },
          { id: 'articles', label: t('audit.hubArticles'), icon: FileText, color: 'text-orange-600', bg: 'bg-orange-50' },
          { id: 'kp', label: t('audit.hubKnowledge'), icon: BrainCircuit, color: 'text-purple-600', bg: 'bg-purple-50' },
          { id: 'sm', label: t('audit.hubStartupMaterials'), icon: Rocket, color: 'text-red-600', bg: 'bg-red-50' },
        ].map(item => (
          <Card key={item.id} onClick={() => setAuditMode(item.id)} className="p-8 rounded-[2rem] bg-white border border-black/5 flex flex-col items-center gap-4 cursor-pointer hover:shadow-xl hover:-translate-y-1 transition-all group text-left">
            <div className={cn("h-16 w-16 rounded-2xl flex items-center justify-center group-hover:scale-110 transition-transform", item.bg, item.color)}><item.icon className="w-8 h-8" /></div>
            <div className="text-center"><h4 className="text-sm font-bold tracking-tight">{item.label}</h4></div>
          </Card>
        ))}
      </div>
    );
  }

  return (
    <Card className="border-none shadow-sm rounded-[2.5rem] bg-white border border-black/[0.03] overflow-hidden text-left">
      <div className="p-6 border-b border-black/[0.03] flex justify-between items-center bg-slate-50/50">
        <Button variant="ghost" onClick={() => setAuditMode('hub')} className="rounded-xl gap-2 font-bold text-xs"><X className="w-4 h-4" /> {t('audit.exitList')}</Button>
        <div className="flex gap-4 items-center">
          <div className="relative"><Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 opacity-30" /><Input value={qSearch} onChange={e => setQSearch(e.target.value)} placeholder={t('audit.searchPlaceholder')} className="pl-12 bg-white border-none h-10 rounded-xl font-bold w-64 shadow-sm text-xs" /></div>
          <Button variant="ghost" size="icon" onClick={fetchLists} className="rounded-full"><RefreshCcw className="w-4 h-4 opacity-40" /></Button>
        </div>
      </div>
      <ScrollArea className="h-[600px] p-6">
        <div className="grid gap-2">
          {auditMode === 'courses' && courseList.map(c => (
            <div key={c.id} className="p-4 bg-[#F5F5F7]/50 rounded-2xl flex items-center justify-between group border border-transparent hover:border-black/5 transition-all">
              <p className="text-sm font-bold text-[#1D1D1F]">{c.title}</p>
              <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <Button onClick={() => onEdit('courses', c)} variant="ghost" size="icon" className="rounded-xl h-8 w-8 hover:bg-white text-blue-600 shadow-sm"><Edit3 className="w-4 h-4" /></Button>
                <Button onClick={() => onDelete('courses', c.id)} variant="ghost" size="icon" className="rounded-xl h-8 w-8 hover:bg-white text-red-500 shadow-sm"><Trash2 className="w-4 h-4" /></Button>
              </div>
            </div>
          ))}
          {auditMode === 'articles' && articleList.map(a => (
            <div key={a.id} className="p-4 bg-[#F5F5F7]/50 rounded-2xl flex items-center justify-between group border border-transparent hover:border-black/5 transition-all">
              <p className="text-sm font-bold text-[#1D1D1F]">{a.title}</p>
              <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <Button onClick={() => onEdit('articles', a)} variant="ghost" size="icon" className="rounded-xl h-8 w-8 hover:bg-white text-blue-600 shadow-sm"><Edit3 className="w-4 h-4" /></Button>
                <Button onClick={() => onDelete('articles', a.id)} variant="ghost" size="icon" className="rounded-xl h-8 w-8 hover:bg-white text-red-500 shadow-sm"><Trash2 className="w-4 h-4" /></Button>
              </div>
            </div>
          ))}
          {auditMode === 'kp' && kpList.map(kp => (
            <div key={kp.id} className="p-4 bg-[#F5F5F7]/50 rounded-2xl flex items-center justify-between group border border-transparent hover:border-black/5 transition-all">
              <p className="text-sm font-bold text-[#1D1D1F]">{kp.name}</p>
              <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                <Button onClick={() => onEdit('kp', kp)} variant="ghost" size="icon" className="rounded-xl h-8 w-8 hover:bg-white text-blue-600 shadow-sm"><Edit3 className="w-4 h-4" /></Button>
                <Button onClick={() => onDelete('kp', kp.id)} variant="ghost" size="icon" className="rounded-xl h-8 w-8 hover:bg-white text-red-500 shadow-sm"><Trash2 className="w-4 h-4" /></Button>
              </div>
            </div>
          ))}
          {auditMode === 'sm' && smList.map(sm => (
            <div key={sm.id} className="p-4 bg-[#F5F5F7]/50 rounded-2xl flex items-center justify-between group border border-transparent hover:border-black/5 transition-all">
              <p className="text-sm font-bold text-[#1D1D1F]">{sm.name}</p>
              <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                <Button onClick={() => onEdit('sm', sm)} variant="ghost" size="icon" className="rounded-xl h-8 w-8 hover:bg-white text-blue-600 shadow-sm"><Edit3 className="w-4 h-4" /></Button>
                <Button onClick={() => onDelete('sm', sm.id)} variant="ghost" size="icon" className="rounded-xl h-8 w-8 hover:bg-white text-red-500 shadow-sm"><Trash2 className="w-4 h-4" /></Button>
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>
    </Card>
  );
};
