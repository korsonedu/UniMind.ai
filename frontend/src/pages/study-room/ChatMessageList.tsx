import React from 'react';
import { Button } from '@/components/ui/button';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';
import { ArrowDown, Lightning, CheckCircle, XCircle, Calendar } from '@phosphor-icons/react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { processMathContent } from '@/lib/utils';

interface Message {
  id: number;
  user_detail: { username: string; nickname: string; avatar_url: string; role: string; };
  content: string;
  timestamp: string;
  related_plan?: number;
}

const remarkSoftBreaks = () => {
  const skipTypes = new Set(['code', 'inlineCode', 'math', 'inlineMath', 'html']);
  const walk = (node: any) => {
    if (!node || skipTypes.has(node.type) || !Array.isArray(node.children)) return;
    const nextChildren: any[] = [];
    node.children.forEach((child: any) => {
      if (child?.type === 'text' && typeof child.value === 'string' && child.value.includes('\n')) {
        const normalizedValue = child.value.replace(/\r\n?/g, '\n');
        const lines = normalizedValue.split('\n');
        lines.forEach((line: string, index: number) => {
          if (line) nextChildren.push({ ...child, value: line });
          if (index < lines.length - 1) nextChildren.push({ type: 'break' });
        });
        return;
      }
      walk(child);
      nextChildren.push(child);
    });
    node.children = nextChildren;
  };
  return (tree: any) => { walk(tree); };
};

const isTaskStateMessage = (content: string) =>
  content.includes('💪') || content.includes('✅') || content.includes('❌') || content.includes('📅');

interface ChatMessageListProps {
  messages: Message[];
  currentUsername: string;
  showOthersBroadcast: boolean;
  lastMyMessageId: number | null;
  lastMyTaskMessageId: number | null;
  isAtBottom: boolean;
  isMobile: boolean;
  scrollContainerRef: React.RefObject<HTMLDivElement | null>;
  onScroll: () => void;
  onScrollToBottom: (force?: boolean) => void;
  onUndoMessage: (messageId: number) => void;
}

export const ChatMessageList: React.FC<ChatMessageListProps> = ({
  messages, currentUsername, showOthersBroadcast,
  lastMyMessageId, lastMyTaskMessageId, isAtBottom, isMobile,
  scrollContainerRef, onScroll, onScrollToBottom, onUndoMessage,
}) => {
  const { t } = useTranslation('studyRoom');

  return (
    <>
      <div
        ref={scrollContainerRef}
        onScroll={onScroll}
        className={cn(
          "flex-1 overflow-y-auto space-y-4 scrollbar-thin scrollbar-thumb-primary/10 relative",
          isMobile ? "min-h-0 p-3" : "p-8"
        )}
      >
        <div className="max-w-4xl mx-auto space-y-4 pb-4">
          {messages.map((msg) => {
            const isMe = msg.user_detail.username === currentUsername;
            const isTask = isTaskStateMessage(msg.content);
            if (isTask && !showOthersBroadcast && !isMe) return null;
            if (isTask) return (
              <div key={msg.id} className="flex flex-col items-center py-0.5 animate-in fade-in zoom-in-95 duration-300">
                <div className={cn("px-6 py-1.5 rounded-2xl border flex items-center gap-3 shadow-sm relative group/task",
                  msg.content.includes('💪') ? "bg-emerald-500/10 text-emerald-600 border-emerald-500/20" :
                  msg.content.includes('✅') ? "bg-blue-500/10 text-blue-600 border-blue-500/20" :
                  msg.content.includes('📅') ? "bg-orange-500/10 text-orange-600 border-orange-500/20" :
                  "bg-red-500/10 text-red-600 border-red-500/20"
                )}>
                   {msg.content.includes('💪') ? <Lightning className="h-3 w-3 fill-emerald-500 text-emerald-500" /> :
                    msg.content.includes('✅') ? <CheckCircle className="h-3 w-3 text-blue-500" /> :
                    msg.content.includes('📅') ? <Calendar className="h-3 w-3 text-orange-500" /> :
                    <XCircle className="h-3 w-3 text-red-500" />
                   }
                   <span className="text-[11px] font-bold tracking-tight text-foreground">
                     <span className="opacity-70">{msg.user_detail.nickname || msg.user_detail.username}</span>
                     {' '}{msg.content}
                   </span>
                   {isMe && msg.id === lastMyTaskMessageId && (
                      <button
                        onClick={() => onUndoMessage(msg.id)}
                        className="ml-3 text-[11px] font-bold text-muted-foreground/50 hover:text-red-500 underline decoration-dotted underline-offset-2 transition-colors cursor-pointer"
                      >
                        {t('undo')}
                      </button>
                   )}
                </div>
              </div>
            );
            const isMediaOnly = msg.content.trim().startsWith('![') && msg.content.trim().endsWith(')');
            return (
              <div key={msg.id} className={cn("flex gap-4 group animate-in fade-in slide-in-from-bottom-2 duration-300", isMe ? "flex-row-reverse text-right" : "flex-row text-left")}>
                <Avatar className="h-9 w-9 border border-border shadow-sm shrink-0 group-hover:scale-105 transition-transform">
                  <AvatarImage src={msg.user_detail.avatar_url} />
                  <AvatarFallback className="text-[11px] font-bold bg-muted">{(msg.user_detail.nickname || msg.user_detail.username)[0]}</AvatarFallback>
                </Avatar>
                <div className={cn("flex flex-col gap-1 max-w-[70%] w-fit", isMe ? "items-end" : "items-start")}>
                  <div className="flex items-center gap-2 px-1 text-muted-foreground">
                    <span className="text-[11px] font-bold uppercase tracking-widest">{msg.user_detail.nickname || msg.user_detail.username}</span>
                  </div>
                  <div
                    className={cn(
                      "text-[13px] leading-relaxed break-words overflow-hidden text-left w-fit h-fit",
                      !isMediaOnly && (isMe ? "p-2 px-3 bg-slate-900 text-white rounded-2xl rounded-tr-none shadow-sm font-medium" : "p-2 px-3 rounded-2xl rounded-tl-none shadow-sm font-medium")
                    )}
                    style={!isMediaOnly && !isMe ? { backgroundColor: '#ffb0b3', color: '#0f172a' } : {}}
                  >
                    <ReactMarkdown
                      remarkPlugins={[remarkMath, remarkSoftBreaks]}
                      rehypePlugins={[rehypeKatex]}
                      components={{
                        img: ({node, ...props}) => <img {...props} alt={props.alt || 'image'} className="max-w-[130px] md:max-w-[200px] rounded-lg my-0.5 cursor-zoom-in hover:opacity-90 transition-opacity" onClick={() => window.open(props.src || '', '_blank', 'noopener,noreferrer')}/>,
                        p: ({node, ...props}) => <p {...props} className="m-0 leading-normal w-fit" />,
                        div: ({node, ...props}) => <div {...props} className="w-fit" />,
                        br: () => <br />
                      }}
                    >
                      {processMathContent(msg.content)}
                    </ReactMarkdown>
                  </div>
                  <div className="mt-0.3 flex items-center gap-2 px-1">
                    <span className="text-[11px] text-muted-foreground/40 font-medium">
                      {new Date(msg.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                    </span>
                    {isMe && msg.id === lastMyMessageId && (
                      <button
                        onClick={() => onUndoMessage(msg.id)}
                        className="text-[11px] font-bold text-muted-foreground/50 hover:text-red-500 underline decoration-dotted underline-offset-2 transition-colors cursor-pointer"
                      >
                        {t('undo')}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {!isAtBottom && (
        <Button onClick={() => onScrollToBottom(true)} size="icon" className="absolute bottom-24 right-8 rounded-full h-10 w-10 shadow-lg bg-primary text-primary-foreground z-50 hover:scale-110 transition-transform opacity-80 hover:opacity-100 border border-white/10">
          <ArrowDown className="h-5 w-5"/>
        </Button>
      )}
    </>
  );
};
