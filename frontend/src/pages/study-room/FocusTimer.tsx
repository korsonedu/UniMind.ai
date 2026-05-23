import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Slider } from '@/components/ui/slider';
import {
  Popover, PopoverContent, PopoverTrigger,
} from '@/components/ui/popover';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel,
  AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Play, Pause, Timer, XCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';

interface FocusTimerProps {
  isActive: boolean;
  duration: number;
  timeLeft: number;
  taskName: string;
  onDurationChange: (val: number) => void;
  onTaskNameChange: (val: string) => void;
  onStart: () => void;
  onPause: () => void;
  onAbort: () => void;
}

const formatTime = (s: number) => {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`;
};

export const FocusTimer: React.FC<FocusTimerProps> = ({
  isActive, duration, timeLeft, taskName,
  onDurationChange, onTaskNameChange, onStart, onPause, onAbort,
}) => {
  const { t } = useTranslation('studyRoom');
  const [isOpen, setIsOpen] = useState(false);
  const [showStopAlert, setShowStopAlert] = useState(false);

  return (
    <>
      <Popover open={isOpen} onOpenChange={setIsOpen}>
        <PopoverTrigger asChild>
          <Button
            className={cn(
              "rounded-2xl h-10 px-5 gap-3 transition-all duration-500 shadow border border-black/5",
              isActive ? "bg-emerald-500 text-white" : "bg-primary text-primary-foreground hover:opacity-90",
            )}
          >
            <Timer className="h-4 w-4" />
            <span className="font-mono font-bold text-sm tracking-tight tabular-nums">{formatTime(timeLeft)}</span>
          </Button>
        </PopoverTrigger>
        <PopoverContent
          className="w-80 rounded-[2.5rem] p-8 border-none shadow-lg bg-card/95 backdrop-blur-xl z-[100]"
          side="bottom" align="end"
        >
          <div className="space-y-5 text-center">
            <div className="text-5xl font-mono font-bold tracking-tighter text-foreground tabular-nums">
              {formatTime(timeLeft)}
            </div>
            <div className="space-y-4 text-left">
              <div className="space-y-2">
                <div className="flex justify-between items-center mb-1">
                  <label className="text-[11px] font-bold uppercase tracking-widest opacity-30 text-foreground">
                    {t('timer.duration')}
                  </label>
                  <div className="flex items-center gap-1">
                    <Input
                      type="number" disabled={isActive}
                      value={duration}
                      onChange={e => onDurationChange(parseInt(e.target.value) || 0)}
                      className="w-12 h-6 p-0 text-center border-none bg-muted rounded-md text-[11px] font-bold text-foreground"
                    />
                    <span className="text-[11px] font-bold opacity-30 uppercase text-foreground">{t('timer.min')}</span>
                  </div>
                </div>
                <Slider disabled={isActive} value={[duration]} onValueChange={v => onDurationChange(v[0])} max={120} min={1} step={1} />
              </div>
              <div className="space-y-2">
                <label className="text-[11px] font-bold uppercase tracking-widest opacity-30 ml-1 text-foreground">
                  {t('timer.taskGoal')}
                </label>
                <Input
                  value={taskName} onChange={e => onTaskNameChange(e.target.value)}
                  placeholder={t('timer.taskPlaceholder')}
                  className="bg-muted border-none h-11 rounded-xl text-center font-bold text-sm text-foreground"
                />
              </div>
            </div>
            <div className="flex justify-center gap-2.5 pt-1">
              <Button
                size="lg"
                onClick={isActive ? () => { onPause(); } : () => { onStart(); setIsOpen(false); }}
                className={cn(
                  "rounded-2xl flex-1 font-bold h-12 shadow-lg",
                  isActive ? "bg-muted text-foreground" : "bg-primary text-primary-foreground shadow-primary/10",
                )}
              >
                {isActive ? <Pause className="mr-2 h-4 w-4" /> : <Play className="mr-2 h-4 w-4" />}
                {isActive ? t('timer.pause') : t('timer.startStudy')}
              </Button>
              {isActive && (
                <Button
                  variant="destructive"
                  onClick={() => setShowStopAlert(true)}
                  className="rounded-2xl h-12 w-12 shadow"
                >
                  <XCircle className="h-5 w-5" />
                </Button>
              )}
            </div>
          </div>
        </PopoverContent>
      </Popover>

      <AlertDialog open={showStopAlert} onOpenChange={setShowStopAlert}>
        <AlertDialogContent className="rounded-[2.5rem] border-none shadow-2xl bg-card">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-foreground">{t('focusMode.confirmTitle')}</AlertDialogTitle>
            <AlertDialogDescription className="text-muted-foreground">{t('focusMode.confirmDesc')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setShowStopAlert(false)} className="rounded-xl border-border text-foreground hover:bg-muted">
              {t('focusMode.keepFocusing')}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={() => { onAbort(); setShowStopAlert(false); }}
              className="rounded-xl bg-red-500 hover:bg-red-600 text-white font-bold"
            >
              {t('focusMode.abortAndLeave')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
};

export const MobileFocusTimer: React.FC<{
  isActive: boolean; duration: number; timeLeft: number; taskName: string;
  onDurationChange: (v: number) => void; onTaskNameChange: (v: string) => void;
  onStart: () => void; onPause: () => void; onAbort: () => void;
}> = ({ isActive, duration, timeLeft, taskName, onDurationChange, onTaskNameChange, onStart, onPause, onAbort }) => {
  const { t } = useTranslation('studyRoom');
  const [showSetup, setShowSetup] = useState(false);
  const [showFullscreen, setShowFullscreen] = useState(false);
  const [showStopAlert, setShowStopAlert] = useState(false);

  return (
    <>
      <Popover open={showSetup} onOpenChange={setShowSetup}>
        <PopoverTrigger asChild>
          <Button
            variant="ghost" size="icon"
            className={cn(
              "h-8 w-8 rounded-lg transition-colors",
              isActive ? "text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50" : "text-muted-foreground hover:text-foreground hover:bg-muted",
            )}
          >
            <Timer className="h-4 w-4" />
          </Button>
        </PopoverTrigger>
        <PopoverContent side="top" align="start" className="w-[82vw] max-w-72 rounded-2xl p-4 border-none shadow-lg bg-card/95 backdrop-blur-xl z-[100]">
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold text-muted-foreground">{t('mobile.pomodoro')}</p>
              <span className="font-mono font-black text-lg tabular-nums">{formatTime(timeLeft)}</span>
            </div>
            <Input value={taskName} onChange={e => onTaskNameChange(e.target.value)} placeholder={t('mobile.taskPlaceholder')} className="h-10 rounded-xl bg-muted border-none text-sm font-bold" />
            <div className="space-y-2">
              <div className="flex items-center justify-between text-[11px] font-bold text-muted-foreground uppercase">
                <span>{t('mobile.duration')}</span>
                <span>{t('mobile.durationFormat', { duration })}</span>
              </div>
              <Slider disabled={isActive} value={[duration]} onValueChange={v => onDurationChange(v[0])} max={120} min={1} step={1} />
            </div>
            <Button
              onClick={() => { onStart(); setShowSetup(false); setShowFullscreen(true); }}
              className="w-full h-10 rounded-xl bg-slate-900 text-white font-black"
            >
              {t('mobile.enterFullscreen')}
            </Button>
          </div>
        </PopoverContent>
      </Popover>

      {/* Fullscreen focus modal */}
      <div className={cn(
        "fixed inset-0 z-[120] md:hidden bg-black/95 text-white flex flex-col items-center justify-center gap-6 transition-all duration-300",
        showFullscreen ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none",
      )}>
        <button onClick={() => setShowFullscreen(false)} className="absolute top-6 right-6 h-10 w-10 rounded-full bg-white/10 flex items-center justify-center">
          <XCircle className="h-5 w-5" />
        </button>
        <p className="text-xs font-semibold text-white/40">{t('focusMode.title')}</p>
        <p className="font-mono font-black text-[72px] leading-none tabular-nums">{formatTime(timeLeft)}</p>
        <p className="text-base font-bold text-white/80 px-8 text-center">{taskName || t('deepFocus')}</p>
        <div className="flex items-center gap-3">
          <Button
            size="lg"
            onClick={isActive ? onPause : onStart}
            className={cn(
              "rounded-2xl px-6 h-12 font-black",
              isActive ? "bg-white/20 text-white hover:bg-white/30" : "bg-emerald-500 text-white hover:bg-emerald-600",
            )}
          >
            {isActive ? <Pause className="mr-2 h-4 w-4" /> : <Play className="mr-2 h-4 w-4" />}
            {isActive ? t('focusMode.pause') : t('focusMode.start')}
          </Button>
          <Button
            size="lg" variant="ghost"
            onClick={() => setShowStopAlert(true)}
            className="rounded-2xl px-6 h-12 font-black text-white border border-white/20 hover:bg-white/10"
          >
            {t('focusMode.end')}
          </Button>
        </div>
      </div>

      <AlertDialog open={showStopAlert} onOpenChange={setShowStopAlert}>
        <AlertDialogContent className="rounded-[2.5rem] border-none shadow-2xl bg-card">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-foreground">{t('focusMode.confirmTitle')}</AlertDialogTitle>
            <AlertDialogDescription className="text-muted-foreground">{t('focusMode.confirmDesc')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setShowStopAlert(false)} className="rounded-xl border-border text-foreground hover:bg-muted">
              {t('focusMode.keepFocusing')}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={() => { onAbort(); setShowStopAlert(false); setShowFullscreen(false); }}
              className="rounded-xl bg-red-500 hover:bg-red-600 text-white font-bold"
            >
              {t('focusMode.abortAndLeave')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
};
