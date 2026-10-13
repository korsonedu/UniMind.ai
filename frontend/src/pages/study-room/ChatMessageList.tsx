import React from 'react';
import { Button } from '@/components/ui/button';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { cn } from '@/lib/utils';
import { ArrowDown, Lightning, CheckCircle, XCircle, Calendar } from '@phosphor-icons/react';
import { MarkdownContent } from '@/components/MarkdownContent';
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
  lastMyTaskMessageId, isAtBottom, isMobile,
  scrollContainerRef, onScroll, onScrollToBottom, onUndoMessage,
}) => {
  return (
    <>
      <div
        ref={scrollContainerRef}
        onScroll={onScroll}
        className={cn(
          "um-study-messages flex-1 overflow-y-auto scrollbar-thin scrollbar-thumb-primary/10 relative",
          isMobile ? "min-h-0 p-3" : "p-5"
        )}
      >
        <div className="max-w-4xl mx-auto space-y-4 pb-4">
          {messages.map((msg) => {
            const isMe = msg.user_detail.username === currentUsername;
            const isTask = isTaskStateMessage(msg.content);
            if (isTask && !showOthersBroadcast && !isMe) return null;
            if (isTask) return (
              <div key={msg.id} className="flex flex-col items-center py-0.5 animate-in fade-in zoom-in-95 duration-300">
                <div className={cn("um-study-event px-3 py-1.5 flex items-center gap-2 relative group/task",
                  msg.content.includes('❌') && "is-danger"
                )}>
                   {msg.content.includes('💪') ? <Lightning className="h-3 w-3 fill-emerald-500 text-emerald-500" /> :
                    msg.content.includes('✅') ? <CheckCircle className="h-3 w-3 text-blue-500" /> :
                    msg.content.includes('📅') ? <Calendar className="h-3 w-3 text-orange-500" /> :
                    <XCircle className="h-3 w-3 text-red-500" />
                   }
                   <span className="text-xs text-foreground">
                     <span className="opacity-70">{msg.user_detail.nickname || msg.user_detail.username}</span>
                     {' '}{msg.content}
                   </span>
                   {isMe && msg.id === lastMyTaskMessageId && (
                      <button
                        onClick={() => onUndoMessage(msg.id)}
                        className="ml-3 text-[11px] font-bold text-muted-foreground/50 hover:text-red-500 underline decoration-dotted underline-offset-2 transition-colors cursor-pointer"
                      >
                        撤销
                      </button>
                   )}
                </div>
              </div>
            );
            const isMediaOnly = msg.content.trim().startsWith('![') && msg.content.trim().endsWith(')');
            return (
              <div key={msg.id} className={cn("um-study-message flex gap-3 group animate-in fade-in slide-in-from-bottom-2 duration-300", isMe ? "flex-row-reverse text-right" : "flex-row text-left")}>
                <Avatar className="h-8 w-8 border border-border shrink-0">
                  <AvatarImage src={msg.user_detail.avatar_url} />
                  <AvatarFallback className="text-[11px] font-bold bg-muted">{(msg.user_detail.nickname || msg.user_detail.username)[0]}</AvatarFallback>
                </Avatar>
                <div className={cn("flex flex-col gap-1 max-w-[70%] w-fit", isMe ? "items-end" : "items-start")}>
                  <div className="flex items-center gap-2 px-1 text-muted-foreground">
                    <span className="text-xs font-medium">{msg.user_detail.nickname || msg.user_detail.username}</span>
                  </div>
                  <div
                    className={cn(
                      "um-study-message-bubble text-sm leading-relaxed break-words overflow-hidden text-left w-fit h-fit",
                      !isMediaOnly && (isMe ? "is-own p-2.5 px-3.5" : "is-other p-2.5 px-3.5")
                    )}
                  >
                    <MarkdownContent
                      content={processMathContent(msg.content)}
                      extraRemarkPlugins={[remarkSoftBreaks]}
                      components={{
                        img: ({node, ...props}: any) => <img {...props} loading="lazy" alt={props.alt || 'image'} className="max-w-[130px] md:max-w-[200px] rounded-lg my-0.5 cursor-zoom-in hover:opacity-90 transition-opacity" onClick={() => window.open(props.src || '', '_blank', 'noopener,noreferrer')}/>,
                        p: ({node, ...props}: any) => <p {...props} className="m-0 leading-normal w-fit" />,
                        div: ({node, ...props}: any) => <div {...props} className="w-fit" />,
                        br: () => <br />
                      }}
                    />
                  </div>
                  <div className="mt-0.3 flex items-center gap-2 px-1">
                    <span className="text-[11px] text-muted-foreground/40 font-medium">
                      {new Date(msg.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {!isAtBottom && (
        <Button onClick={() => onScrollToBottom(true)} size="icon" className="um-study-scroll-bottom absolute bottom-24 right-8 h-10 w-10 bg-primary text-primary-foreground z-50">
          <ArrowDown className="h-5 w-5"/>
        </Button>
      )}
    </>
  );
};
