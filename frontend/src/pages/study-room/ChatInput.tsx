import React from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Popover, PopoverContent, PopoverTrigger,
} from '@/components/ui/popover';
import { cn } from '@/lib/utils';
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
  return (
    <footer className={cn(
      "um-study-input border-t border-border z-20",
      isMobile ? "px-3 pt-2 pb-[calc(0.75rem+env(safe-area-inset-bottom))] shrink-0" : "px-5 py-3"
    )}>
      <div className="max-w-4xl mx-auto">
        <div className="um-study-composer transition-colors border border-border overflow-hidden">
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
            placeholder="发送消息到学习咖啡厅"
            className={cn(
              "um-study-composer-textarea block w-full bg-transparent border-none shadow-none focus:outline-none focus-visible:ring-0 text-sm px-3.5 pt-2.5 pb-1 text-foreground placeholder:text-muted-foreground/55 resize-none leading-5",
              isMobile ? "h-9 min-h-9 max-h-9" : "min-h-9 max-h-24"
            )}
            rows={1}
          />

          <div className="um-study-composer-bar flex items-center justify-between px-1.5 pb-1.5">
            <div className="um-study-input-tools flex items-center gap-0.5">
          {isMobile && (
            <Popover open={showMobileTimerSetup} onOpenChange={setShowMobileTimerSetup}>
              <PopoverTrigger asChild>
                <Button
                  variant="ghost" size="icon"
                  className={cn(
                    "h-8 w-8 rounded-md transition-colors",
                    isActive ? "text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50" : "text-muted-foreground hover:text-foreground hover:bg-muted"
                  )}
                  aria-label="设置专注时钟"
                >
                  <Timer className="h-5 w-5" />
                </Button>
              </PopoverTrigger>
              <PopoverContent side="top" align="start" className="w-[82vw] max-w-72 rounded-2xl p-4 border-none shadow-lg bg-card/95 backdrop-blur-xl z-[var(--z-dropdown)]">
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <p className="text-xs font-semibold text-muted-foreground">番茄钟</p>
                    <span className="font-mono font-black text-lg tabular-nums">{formatTime(timeLeft)}</span>
                  </div>
                  <Input value={taskName} onChange={e => onTaskNameChange(e.target.value)} placeholder="任务名称..." className="h-10 rounded-xl bg-muted border-none text-sm font-bold" />
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-[11px] font-bold text-muted-foreground uppercase">
                      <span>时长</span>
                      <span>{`${duration} 分钟`}</span>
                    </div>
                    <Slider disabled={isActive} value={[duration]} onValueChange={v => onDurationChange(v[0])} max={120} min={1} step={1} />
                  </div>
                  <Button onClick={onEnterMobileFocus} className="w-full h-10 rounded-xl bg-slate-900 text-white font-black">
                    进入全屏专注
                  </Button>
                </div>
              </PopoverContent>
            </Popover>
          )}

          {/* Emoji picker */}
          <Popover>
            <PopoverTrigger asChild>
              <Button variant="ghost" size="icon" className="h-8 w-8 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors" aria-label="选择表情">
                <Smiley className="h-5 w-5"/>
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

          <Button variant="ghost" size="icon" onClick={() => fileInputRef.current?.click()} className="h-8 w-8 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors" aria-label="上传图片">
            <ImageIcon className="h-5 w-5"/>
          </Button>
          {isMobile && (
            <Button variant="ghost" size="icon" onClick={() => cameraInputRef.current?.click()} className="h-8 w-8 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors" aria-label="拍照">
              <Camera className="h-5 w-5" />
            </Button>
          )}
          <input type="file" ref={fileInputRef} onChange={onFileUpload} className="hidden" accept="image/*" />
          <input type="file" ref={cameraInputRef} onChange={onFileUpload} className="hidden" accept="image/*" capture="environment" />
            </div>
          </div>

          <Button
            onClick={onSendMessage}
            size="icon"
            aria-label="发送消息"
            disabled={!chatInput.trim()}
            className="um-study-send absolute right-2 bottom-2 h-8 w-8 bg-primary text-primary-foreground shrink-0 transition-colors"
          >
            <PaperPlaneTilt className="h-[18px] w-[18px]" weight="fill" />
          </Button>
        </div>
      </div>
    </footer>
  );
};
