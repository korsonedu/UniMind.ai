import React from 'react';
import { User, Robot as BotIcon, Spinner } from '@phosphor-icons/react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { cn } from '@/lib/utils';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface ChatMessageProps {
  msg: Message;
  isUser: boolean;
  avatar: string | null;
  botName: string;
  userName: string;
  isThinking?: boolean;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({ 
  msg, 
  isUser, 
  avatar, 
  botName, 
  userName,
  isThinking = false
}) => {
  return (
    <div className={cn(
      "flex gap-4 group w-full", 
      isUser ? "flex-row-reverse text-right" : "flex-row text-left animate-in fade-in slide-in-from-bottom-2"
    )}>
      <div className={cn(
        "h-10 w-10 rounded-full flex items-center justify-center shrink-0 shadow-sm border border-border",
        isUser ? "bg-card" : "bg-primary"
      )}>
        {isUser ? (
          <User className="w-5 h-5 text-foreground" />
        ) : (
          avatar ? <img src={avatar} alt="" className="w-full h-full rounded-full object-cover" /> : <BotIcon className="w-5 h-5 text-primary-foreground" />
        )}
      </div>
      <div className={cn("flex flex-col gap-1.5 max-w-[75%]", isUser ? "items-end" : "items-start")}>
        <span className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground px-1">
          {isUser ? userName : botName}
        </span>
        <div className={cn(
          "p-3 px-4 rounded-2xl text-[13px] shadow-sm transition-all border border-border w-fit text-left",
          isUser 
            ? "bg-primary text-primary-foreground rounded-tr-none font-medium" 
            : "bg-muted text-foreground rounded-tl-none font-medium"
        )}>
          {isThinking ? (
            <div className="flex items-center justify-center py-1">
              <Spinner className="h-4 w-4 animate-spin opacity-40" />
            </div>
          ) : (
            <div className={cn("prose prose-sm max-w-none text-left prose-headings:font-black prose-headings:tracking-tight prose-p:leading-relaxed", isUser ? "prose-p:text-primary-foreground prose-strong:text-primary-foreground prose-li:text-primary-foreground" : "prose-p:text-foreground prose-strong:text-foreground prose-li:text-foreground")}>
              <ReactMarkdown 
                remarkPlugins={[remarkMath]} 
                rehypePlugins={[rehypeKatex]}
              >
                {msg.content}
              </ReactMarkdown>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
