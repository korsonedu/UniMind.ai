import React, { useState, useRef, useCallback } from 'react';
import { ChatCircle, Plus, Trash, ClockCounterClockwise } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';
import type { ConversationSession } from '@/hooks/useAgentConversation';

export interface SessionSidebarProps {
  sessions: ConversationSession[];
  activeSessionId: number | null;
  onSelect: (session: ConversationSession) => void;
  onDelete?: (session: ConversationSession) => void;
  onNew: () => void;
  botDisplayName: string;
  defaultExpanded?: boolean;
}

const COLLAPSED_W = 48;
const EXPANDED_W = 224;
const SNAP_THRESHOLD = 100; // 低于此宽度自动吸附到收起状态

function formatTime(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  const now = new Date();
  const diffDays = Math.floor((now.getTime() - d.getTime()) / 86400000);
  if (diffDays === 0) return '今天';
  if (diffDays === 1) return '昨天';
  if (diffDays < 7) return `${diffDays} 天前`;
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
}

export default function SessionSidebar({
  sessions,
  activeSessionId,
  onSelect,
  onDelete,
  onNew,
  botDisplayName,
  defaultExpanded = true,
}: SessionSidebarProps) {
  const [width, setWidth] = useState(() => defaultExpanded ? EXPANDED_W : COLLAPSED_W);
  const [dragging, setDragging] = useState(false);
  const dragStartX = useRef(0);
  const dragStartWidth = useRef(0);
  const expanded = width >= SNAP_THRESHOLD;

  const handleDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setDragging(true);
    dragStartX.current = e.clientX;
    dragStartWidth.current = width;

    const onMove = (ev: MouseEvent) => {
      const delta = ev.clientX - dragStartX.current;
      setWidth(Math.max(COLLAPSED_W, Math.min(EXPANDED_W + 80, dragStartWidth.current + delta)));
    };
    const onUp = () => {
      setDragging(false);
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      setWidth(prev => prev < SNAP_THRESHOLD ? COLLAPSED_W : EXPANDED_W);
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }, [width]);

  return (
    <aside
      className={cn(
        'shrink-0 flex flex-col min-h-full bg-card/70 backdrop-blur-2xl',
        dragging && 'select-none overflow-hidden',
      )}
      style={{ width, transition: dragging ? 'none' : 'width 200ms ease' }}
    >
      {/* 可拖动右边缘 — 分隔线 + 热区合一 */}
      <div
        className="absolute right-0 top-0 bottom-0 w-[6px] cursor-col-resize z-10 flex justify-center"
        onMouseDown={handleDragStart}
      >
        <div className="w-px h-full bg-border" />
      </div>

      {/* Header */}
      <div className={cn(
        'shrink-0 flex items-center border-b border-border/30',
        expanded ? 'px-4 py-3 justify-between' : 'px-2 py-3 justify-center',
      )}>
        {expanded && (
          <div className="flex items-center gap-2 min-w-0">
            <div className="h-6 w-6 rounded-lg bg-gradient-to-br from-primary/70 to-primary/40 flex items-center justify-center shrink-0">
              <ClockCounterClockwise className="h-3 w-3 text-primary-foreground" />
            </div>
            <span className="text-[13px] font-bold text-foreground/80 truncate">
              {botDisplayName}
            </span>
          </div>
        )}
        <button
          onClick={onNew}
          className={cn(
            'shrink-0 rounded-lg transition-colors text-muted-foreground/50 hover:text-foreground/70 hover:bg-muted/60',
            expanded ? 'p-1.5' : 'p-1',
          )}
          title="新对话"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Session list */}
      <div className={cn('flex-1 overflow-y-auto min-h-0', dragging && 'overflow-hidden')}>
        {sessions.length === 0 ? (
          expanded && (
            <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
              <ChatCircle className="h-5 w-5 text-muted-foreground/15 mb-2" />
              <p className="text-[11px] text-muted-foreground/35">暂无历史对话</p>
            </div>
          )
        ) : (
          <div className={cn('py-2', expanded && 'px-2')}>
            {[...sessions].reverse().map((session) => {
              const isActive = session.id === activeSessionId;
              return (
                <div
                  key={session.id}
                  className={cn(
                    'flex items-center rounded-lg transition-colors cursor-pointer relative',
                    expanded ? 'px-3 py-2.5 gap-2' : 'justify-center py-2.5',
                    isActive
                      ? 'bg-primary/8 text-foreground'
                      : 'hover:bg-muted/50 text-foreground/60',
                  )}
                  onClick={() => onSelect(session)}
                >
                  {/* Active indicator — left accent line */}
                  {isActive && expanded && (
                    <div className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-full bg-primary/60" />
                  )}

                  {!expanded ? (
                    <div className={cn(
                      'h-2 w-2 rounded-full shrink-0',
                      isActive ? 'bg-primary/60' : 'bg-muted-foreground/20',
                    )} />
                  ) : (
                    <div className="flex-1 min-w-0 overflow-hidden">
                      <p className={cn(
                        'text-[13px] truncate',
                        isActive ? 'font-semibold' : 'font-medium',
                      )}>
                        {session.title || session.label}
                      </p>
                      <p className="text-[10px] text-muted-foreground/45 mt-0.5 whitespace-nowrap">
                        {session.messages.length} 条消息
                        {session.lastTime && (
                          <> · {formatTime(session.lastTime)}</>
                        )}
                      </p>
                    </div>
                  )}

                  {/* Delete button — always visible */}
                  {expanded && onDelete && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onDelete(session);
                      }}
                      className="shrink-0 p-1 rounded text-muted-foreground/25 hover:text-destructive hover:bg-destructive/10 transition-colors"
                      title="删除对话"
                    >
                      <Trash className="h-3 w-3" />
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </aside>
  );
}
