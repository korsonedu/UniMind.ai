import React from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { PageWrapper } from '@/components/PageWrapper';
import { useSystemStore } from '@/store/useSystemStore';
import { useAuthStore } from '@/store/useAuthStore';
import { Sun, Moon, Palette, Check, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';

const PRESET_COLORS = [
  { hex: '#000000' },
  { hex: '#1d4ed8' },
  { hex: '#059669' },
  { hex: '#991b1b' },
  { hex: '#d97706' },
];

export const SystemSettings: React.FC = () => {
  const { t } = useTranslation('settings');
  const { theme, setTheme, primaryColor, setPrimaryColor } = useSystemStore();
  const { user } = useAuthStore();
  const canUseDarkMode = user?.role === 'admin';

  const colorName = (hex: string) => {
    const map: Record<string, string> = {
      '#000000': t('visual.colors.minimalBlack'),
      '#1d4ed8': t('visual.colors.academicBlue'),
      '#059669': t('visual.colors.ivyGreen'),
      '#991b1b': t('visual.colors.oxfordRed'),
      '#d97706': t('visual.colors.amberOrange'),
    };
    return map[hex] || hex;
  };

  return (
    <PageWrapper title={t('pages:systemSettings.title')} subtitle={t('pages:systemSettings.subtitle')}>
      <div className="max-w-4xl mx-auto space-y-8 text-left animate-in fade-in duration-700">

        {/* Visual Styling Card */}
        <Card className="border shadow-sm rounded-3xl bg-card border-border overflow-hidden">
          <CardHeader className="p-10 pb-6 border-b border-border">
            <div className="flex items-center gap-4">
               <div className="h-12 w-12 rounded-2xl bg-muted flex items-center justify-center">
                 <Palette className="h-6 w-6 text-muted-foreground" />
               </div>
               <div className="text-left">
                  <CardTitle className="text-xl font-bold tracking-tight">{t('visual.title')}</CardTitle>
                  <CardDescription className="text-sm font-medium text-muted-foreground">{t('visual.description')}</CardDescription>
               </div>
            </div>
          </CardHeader>
          <CardContent className="p-10 space-y-12">
            <div className="flex items-center justify-between p-6 rounded-[2rem] bg-muted/60 border border-border">
              <div className="flex items-center gap-5">
                <div className="h-12 w-12 rounded-2xl bg-card flex items-center justify-center shadow-sm border border-border">
                  {theme === 'light' ? <Sun className="h-6 w-6 text-amber-500" /> : <Moon className="h-6 w-6 text-blue-500" />}
                </div>
                <div className="space-y-0.5 text-left">
                  <p className="text-base font-bold text-foreground">{t('visual.darkMode')}</p>
                  <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">
                    {t('visual.darkModeAdminOnly')}
                  </p>
                </div>
              </div>
              <Switch
                checked={canUseDarkMode && theme === 'dark'}
                disabled={!canUseDarkMode}
                onCheckedChange={(checked) => {
                  if (!canUseDarkMode) {
                    setTheme('light');
                    return;
                  }
                  setTheme(checked ? 'dark' : 'light');
                }}
              />
            </div>
            <div className="space-y-6 text-left">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-muted-foreground/60" />
                <Label className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">{t('visual.brandAccent')}</Label>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                {PRESET_COLORS.map((color) => (
                  <button
                    key={color.hex}
                    onClick={() => setPrimaryColor(color.hex)}
                    className={cn(
                      "group relative h-24 rounded-[1.5rem] border-2 transition-all flex flex-col items-center justify-center gap-3 overflow-hidden",
                      primaryColor === color.hex
                        ? "border-primary shadow scale-105 bg-card"
                        : "border-transparent bg-muted/60 hover:border-border"
                    )}
                  >
                    <div className="h-8 w-8 rounded-full shadow-inner ring-4 ring-card" style={{ backgroundColor: color.hex }} />
                    <span className="text-[10px] font-bold uppercase tracking-widest text-foreground">{colorName(color.hex)}</span>
                    {primaryColor === color.hex && (
                      <div className="absolute top-2 right-2 h-5 w-5 bg-primary rounded-full flex items-center justify-center animate-in zoom-in">
                        <Check className="h-3 w-3 text-primary-foreground" />
                      </div>
                    )}
                  </button>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </PageWrapper>
  );
};
