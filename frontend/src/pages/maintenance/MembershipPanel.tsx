import React from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';
import { ShieldCheck, Loader2, Sparkles, RefreshCcw } from 'lucide-react';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';

export const MembershipPanel = ({ 
  codes, 
  newCodeCount, 
  setNewCodeCount, 
  isGeneratingCodes, 
  handleGenerateCodes, 
  handleDeleteCode, 
  fetchCodes 
}: { 
  codes: any[], 
  newCodeCount: number, 
  setNewCodeCount: (n: number) => void, 
  isGeneratingCodes: boolean, 
  handleGenerateCodes: () => void, 
  handleDeleteCode: (id: number) => void,
  fetchCodes: () => void
}) => {
  const { t } = useTranslation('maintenance');
  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start text-left">
      <Card className="lg:col-span-4 border-none shadow-sm rounded-3xl p-10 bg-white border border-black/[0.03] space-y-8">
        <div className="flex items-center gap-3">
          <ShieldCheck className="h-6 w-6 text-amber-600" />
          <h3 className="text-xl font-bold tracking-tight text-foreground">{t('membership.batchGenerateCodes')}</h3>
        </div>
        <div className="space-y-6">
          <div className="space-y-2.5">
            <Label className="text-[11px] font-bold uppercase tracking-widest opacity-40 ml-1">{t('membership.generateCount')}</Label>
            <Input 
              type="number" 
              min="1" 
              max="50" 
              value={newCodeCount} 
              onChange={e => setNewCodeCount(parseInt(e.target.value) || 1)} 
              className="bg-unimind-bg-secondary border-none h-12 rounded-xl font-bold px-5" 
            />
          </div>
          <Button 
            onClick={handleGenerateCodes} 
            disabled={isGeneratingCodes}
            className="w-full bg-black text-white h-14 rounded-2xl font-bold shadow uppercase text-xs tracking-widest gap-2"
          >
            {isGeneratingCodes ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
            Generate Codes
          </Button>
          <p className="text-[11px] font-medium text-muted-foreground leading-relaxed px-2">
            {t('membership.hint')}
          </p>
        </div>
      </Card>

      <Card className="lg:col-span-8 border-none shadow-sm rounded-3xl p-10 bg-unimind-bg-secondary/50 border border-black/[0.03] space-y-6">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold uppercase tracking-widest text-black/40">{t('membership.codeInventory')}</h3>
          <Button variant="ghost" size="icon" onClick={fetchCodes} className="rounded-full h-10 w-10">
            <RefreshCcw className="w-4 h-4 opacity-40" />
          </Button>
        </div>
        <ScrollArea className="h-[520px]">
          <div className="grid gap-3 pr-4">
            {codes.length === 0 ? (
              <div className="py-20 text-center opacity-20 font-bold uppercase text-[11px] tracking-widest">{t('membership.noData')}</div>
            ) : (
              codes.map(c => (
                <div key={c.id} className="p-4 bg-white rounded-2xl border border-black/[0.02] shadow-sm flex items-center justify-between group">
                  <div className="flex items-center gap-4">
                    <div className={cn(
                      "h-10 px-4 rounded-xl flex items-center justify-center font-mono font-bold text-sm tracking-widest",
                      c.is_used ? "bg-muted text-muted-foreground line-through" : "bg-amber-50 text-amber-700 border border-amber-100"
                    )}>
                      {c.code}
                    </div>
                    <div className="flex flex-col">
                      <span className={cn("text-[11px] font-bold uppercase", c.is_used ? "text-red-500" : "text-emerald-500")}>
                        {c.is_used ? t('membership.expired') : t('membership.pending')}
                      </span>
                      {c.is_used && (
                        <span className="text-[11px] font-medium text-muted-foreground italic">
                          {t('membership.activatedBy', { user: c.used_by_username || '?', date: new Date(c.used_at).toLocaleDateString() })}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex gap-1 opacity-100 transition-opacity text-left">
                    {!c.is_used && (
                      <Button 
                        variant="ghost" 
                        size="sm" 
                        onClick={() => {
                          navigator.clipboard.writeText(c.code);
                          toast.success(t('membership.copiedToClipboard'));
                        }}
                        className="h-8 rounded-lg font-bold text-[11px] uppercase text-indigo-600 hover:bg-indigo-50"
                      >
                        Copy
                      </Button>
                    )}
                    <Button 
                      variant="ghost" 
                      size="sm" 
                      onClick={() => handleDeleteCode(c.id)}
                      className="h-8 rounded-lg font-bold text-[11px] uppercase text-red-600 hover:bg-red-50"
                    >
                      {c.is_used ? 'Revoke' : 'Delete'}
                    </Button>
                  </div>
                </div>
              ))
            )}
          </div>
        </ScrollArea>
      </Card>
    </div>
  );
};
