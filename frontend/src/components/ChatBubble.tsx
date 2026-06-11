import React from 'react';
import { Sparkle } from '@phosphor-icons/react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import { cn } from '@/lib/utils';

export interface ChatBubbleMessage {
  role: 'user' | 'assistant';
  content: string;
}

interface ChatBubbleProps {
  msg: ChatBubbleMessage;
  isUser: boolean;
  isThinking?: boolean;
  index: number;
  botGradient?: string;
  botAvatar?: string;
  /** Hide avatar and use tighter spacing */
  compact?: boolean;
}

const ChatBubble: React.FC<ChatBubbleProps> = React.memo(({
  msg,
  isUser,
  isThinking = false,
  index,
  botGradient = 'from-violet-500 to-indigo-500',
  botAvatar,
  compact = false,
}) => (
  <div
    className={cn("flex w-full", compact ? "gap-0" : "gap-2", isUser ? "flex-row-reverse" : "flex-row")}
    style={{ animationDelay: `${Math.min(index * 40, 200)}ms` }}
  >
    {!isUser && !compact && (
      <div className={cn("h-6 w-6 rounded-full overflow-hidden shrink-0 mt-0.5", botAvatar ? "" : `bg-gradient-to-br ${botGradient} flex items-center justify-center`)}>
        {botAvatar ? (
          <img src={botAvatar} alt="" className="w-full h-full object-cover" />
        ) : (
          <Sparkle className="h-3 w-3 text-white" />
        )}
      </div>
    )}
    <div className={cn("flex flex-col max-w-[85%]", isUser ? "items-end" : "items-start")}>
      <div className={cn(
        "w-fit animate-in fade-in slide-in-from-bottom-1 duration-300",
        compact
          ? "px-2.5 py-1 text-[12px] leading-relaxed"
          : "px-3 py-1.5 text-[13px] leading-relaxed",
        isUser
          ? "bg-foreground text-background font-medium rounded-xl rounded-tr-sm"
          : "bg-muted text-foreground rounded-xl rounded-tl-sm"
      )}>
        {isThinking ? (
          <div className="flex items-center gap-1 py-0.5">
            <span className="inline-block w-1 h-1 rounded-full bg-foreground/40 animate-bounce" style={{ animationDelay: '0ms' }} />
            <span className="inline-block w-1 h-1 rounded-full bg-foreground/40 animate-bounce" style={{ animationDelay: '150ms' }} />
            <span className="inline-block w-1 h-1 rounded-full bg-foreground/40 animate-bounce" style={{ animationDelay: '300ms' }} />
          </div>
        ) : (
          <div className={cn(
            "prose prose-sm max-w-full text-left overflow-x-auto",
            "prose-p:my-0.5 prose-p:leading-relaxed",
            isUser ? "prose-p:text-background prose-strong:text-background prose-li:text-background" : "prose-p:text-foreground prose-strong:text-foreground prose-li:text-foreground",
            "prose-headings:font-bold prose-headings:tracking-tight",
            "prose-table:text-xs prose-table:border-collapse prose-table:my-2 prose-table:min-w-[200px]",
            "prose-th:px-2.5 prose-th:py-1.5 prose-th:text-left prose-th:font-bold prose-th:bg-primary/5 prose-th:border prose-th:border-border prose-th:whitespace-nowrap",
            "prose-td:px-2.5 prose-td:py-1.5 prose-td:border prose-td:border-border",
            "prose-thead:border-b-2 prose-thead:border-primary/20",
            "prose-code:text-[11px] prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:rounded",
            "prose-pre:bg-muted prose-pre:border prose-pre:border-border",
            // KaTeX display math spacing
            "prose-[.katex-display]:my-2 prose-[.katex-display]:overflow-x-auto",
          )}>
            <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
              {msg.content}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  </div>
));

export default ChatBubble;
