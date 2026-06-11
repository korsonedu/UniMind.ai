import React from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Popover, PopoverContent, PopoverTrigger,
} from '@/components/ui/popover';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';
import { PaperPlaneTilt, Smiley, Image as ImageIcon, Camera, Timer } from '@phosphor-icons/react';
import { Slider } from '@/components/ui/slider';
import { GiphyPicker } from './GiphyPicker';

interface ChatInputProps {
  chatInput: string;
  isMobile: boolean;
  isComposing: boolean;
  isActive: boolean;
  chatTextareaRef: React.RefObject<HTMLTextAreaElement | null>;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  cameraInputRef: React.RefObject<HTMLInputElement | null>;
  onChatInputChange: (value: string) => void;
  onCompositionStart: () => void;
  onCompositionEnd: () => void;
  onSendMessage: () => void;
  onFileUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onSendGif: (url: string) => void;
  // Mobile timer setup
  showMobileTimerSetup: boolean;
  setShowMobileTimerSetup: (v: boolean) => void;
  timeLeft: number;
  taskName: string;
  duration: number;
  onTaskNameChange: (v: string) => void;
  onDurationChange: (v: number) => void;
  onEnterMobileFocus: () => void;
  formatTime: (s: number) => string;
}

const EMOJIS = ['😊','😂','🤣','😍','😒','🤔','😭','👍','🙌','🔥','✨','💯','📚','🎓','💪','🎯','❤️','✔️','❌','⚠️','🚀','💡','🌟','🎉'];

export const ChatInput: React.FC<ChatInputProps> = ({
  chatInput, isMobile, isComposing, isActive,
  chatTextareaRef, fileInputRef, cameraInputRef,
  onChatInputChange, onCompositionStart, onCompositionEnd,
  onSendMessage, onFileUpload, onSendGif,
  showMobileTimerSetup, setShowMobileTimerSetup,
  timeLeft, taskName, duration,
  onTaskNameChange, onDurationChange, onEnterMobileFocus,
  formatTime,
}) => {
  const { t } = useTranslation('studyRoom');

  return (
    <footer className={cn(
      "bg-card/80 backdrop-blur-md border-t border-border z-20",
      isMobile ? "p-2 pb-[calc(4.9rem+env(safe-area-inset-bottom))] shrink-0" : "p-4"
    )}>
      <div className="max-w-4xl mx-auto space-y-3">
        <div className="flex gap-2 px-1">
          {isMobile && (
            <Popover open={showMobileTimerSetup} onOpenChange={setShowMobileTimerSetup}>
              <PopoverTrigger asChild>
                <Button
                  variant="ghost" size="icon"
                  className={cn(
                    "h-8 w-8 rounded-lg transition-colors",
                    isActive ? "text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50" : "text-muted-foreground hover:text-foreground hover:bg-muted"
                  )}
                >
                  <Timer className="h-4 w-4" />
                </Button>
              </PopoverTrigger>
              <PopoverContent side="top" align="start" className="w-[82vw] max-w-72 rounded-2xl p-4 border-none shadow-lg bg-card/95 backdrop-blur-xl z-[var(--z-dropdown)]">
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
                  <Button onClick={onEnterMobileFocus} className="w-full h-10 rounded-xl bg-slate-900 text-white font-black">
                    {t('mobile.enterFullscreen')}
                  </Button>
                </div>
              </PopoverContent>
            </Popover>
          )}

          {/* Emoji picker */}
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="ghost" size="icon" className="h-8 w-8 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors" aria-label="Emoji">
                <Smiley className="h-4 w-4"/>
              </Button>
            </PopoverTrigger>
            <PopoverContent side="top" className="w-64 p-2 rounded-2xl border-border shadow-lg bg-card">
              <div className="grid grid-cols-8 gap-1">
                {EMOJIS.map(e => (
                  <button key={e} onClick={() => onChatInputChange(chatInput + e)} className="h-8 w-8 flex items-center justify-center hover:bg-muted rounded-lg text-lg transition-colors">{e}</button>
                ))}
              </div>
            </PopoverContent>
          </Popover>

          <GiphyPicker onGifSent={onSendGif} />

          <Button variant="ghost" size="icon" onClick={() => fileInputRef.current?.click()} className="h-8 w-8 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors" aria-label="Upload image">
            <ImageIcon className="h-4 w-4"/>
          </Button>
          {isMobile && (
            <Button variant="ghost" size="icon" onClick={() => cameraInputRef.current?.click()} className="h-8 w-8 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors" aria-label="Take photo">
              <Camera className="h-4 w-4" />
            </Button>
          )}
          <input type="file" ref={fileInputRef} onChange={onFileUpload} className="hidden" accept="image/*" />
          <input type="file" ref={cameraInputRef} onChange={onFileUpload} className="hidden" accept="image/*" capture="environment" />
        </div>

        {/* Text input area */}
        <div className="flex gap-3 bg-muted rounded-2xl p-1.5 focus-within:bg-card focus-within:ring-2 focus-within:ring-primary/5 transition-all shadow-inner border border-border">
          <textarea
            ref={chatTextareaRef}
            value={chatInput}
            onChange={e => onChatInputChange(e.target.value)}
            onCompositionStart={onCompositionStart}
            onCompositionEnd={onCompositionEnd}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey && !isComposing) {
                e.preventDefault();
                onSendMessage();
              }
            }}
            placeholder=""
            className={cn(
              "flex-1 bg-transparent border-none shadow-none focus:outline-none focus-visible:ring-0 text-[13px] px-4 py-2.5 text-foreground placeholder:text-muted-foreground/50 resize-none leading-5",
              isMobile ? "h-10 min-h-10 max-h-10" : "min-h-10 max-h-32"
            )}
            rows={1}
          />
          <Button onClick={onSendMessage} size="icon" className="rounded-xl h-10 w-10 bg-primary text-primary-foreground shadow shrink-0 hover:opacity-90 active:scale-95 transition-transform">
            <PaperPlaneTilt className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </footer>
  );
};
