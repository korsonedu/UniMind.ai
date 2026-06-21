import React, { useState, useEffect, useRef } from 'react';
import { useIsMobile } from '@/lib/useIsMobile';
import { useTranslation } from 'react-i18next';
import { ChatCircleText, MagnifyingGlass, Paperclip, PaperPlaneTilt, DotsThree, Star, Trash, CheckCircle, Circle, CaretUp, ArrowBendDownRight, Spinner, ChatCircle, X, PencilSimple, ThumbsUp, Eye } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator
} from "@/components/ui/dropdown-menu";
import { PageWrapper } from '@/components/PageWrapper';
import { useAuthStore } from '@/store/useAuthStore';
import api from '@/lib/api';
import { toast } from 'sonner';
import { useConfirm } from '@/components/useConfirm';
import { cn, processMathContent } from '@/lib/utils';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

// --- Sub-Components ---

const AnswerItem = ({ answer, isFirst, onReplyClick, onRefresh }: { answer: any, isFirst: boolean, onReplyClick: () => void, onRefresh: () => void }) => {
  const { user } = useAuthStore();
  const { t } = useTranslation('qaSystem');
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(answer.content);
  const [isSubmitting, setIsSubmitting] = useState(false);
  
  // Like State
  const [likesCount, setLikesCount] = useState(answer.likes_count || 0);
  const [isLiked, setIsLiked] = useState(answer.is_liked || false);
  const { confirm, Dialog } = useConfirm();

  useEffect(() => {
    if (!isEditing) setEditContent(answer.content);
  }, [answer.content, isEditing]);

  const handleEdit = async () => {
    if (!editContent.trim()) return;
    setIsSubmitting(true);
    try {
      await api.patch(`/qa/answers/${answer.id}/`, { content: editContent });
      toast.success(t('replyUpdated'));
      setIsEditing(false);
      onRefresh();
    } catch (e) { toast.error(t('updateFailed')); }
    finally { setIsSubmitting(false); }
  };

  const handleDelete = async () => {
    if (!(await confirm(t('deleteConfirm')))) return;
    try {
      await api.delete(`/qa/answers/${answer.id}/`);
      toast.success(t('replyDeleted'));
      onRefresh();
    } catch (e) { toast.error(t('deleteFailed')); }
  };

  const handleLike = async (e: React.MouseEvent) => {
      e.stopPropagation();
      try {
          const res = await api.patch(`/qa/answers/${answer.id}/action/`, { toggle_like: true });
          setIsLiked(res.data.is_liked);
          setLikesCount(res.data.likes_count);
      } catch(e) { toast.error(t('operationFailed')); }
  };

  return (
    <div className={cn("flex gap-3 text-left group/answer relative", isFirst ? "mb-2" : "mt-3 ml-2 md:ml-4")}>
      <Avatar className={cn("border border-border shadow-sm", isFirst ? "h-8 w-8" : "h-7 w-7")}>
        <AvatarImage src={answer.user_detail.avatar_url} />
        <AvatarFallback className={cn("font-bold", answer.is_teacher ? "bg-indigo-100 text-indigo-700" : "bg-muted")}>
          {answer.user_detail.username[0]}
        </AvatarFallback>
      </Avatar>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <span className={cn("text-[11px] font-bold", answer.is_teacher ? "text-indigo-600" : "text-foreground")}>
              {answer.user_detail.nickname || answer.user_detail.username}
            </span>
            {answer.is_teacher && <Badge variant="secondary" className="h-4 px-1 text-[11px] bg-indigo-50 text-indigo-600 border-indigo-100">TEACHER</Badge>}
            <span className="text-[11px] text-muted-foreground tabular-nums">
              {new Date(answer.created_at).toLocaleString(navigator.language || 'zh-CN', {month: '2-digit', day: '2-digit', hour: '2-digit', minute:'2-digit'})}
            </span>
          </div>

          {/* Action Menu (Only visible on hover for owner/admin) */}
          {(user?.username === answer.user_detail.username || user?.role === 'admin') && !isEditing && (
            <DropdownMenu modal={false}>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="h-5 w-5 opacity-100 transition-opacity">
                  <DotsThree className="h-3 w-3 text-muted-foreground" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => setIsEditing(true)} className="gap-2 text-xs">
                  <PencilSimple className="h-3 w-3" /> {t('edit')}
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handleDelete} className="gap-2 text-xs text-red-600 focus:text-red-700 focus:bg-red-50">
                  <Trash className="h-3 w-3" /> {t('delete')}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>

        {isEditing ? (
          <div className="space-y-2 animate-in fade-in zoom-in-95 duration-200">
            <textarea
              value={editContent}
              onChange={e => setEditContent(e.target.value)}
              className="w-full text-xs p-3 rounded-xl border border-input bg-muted/30 focus:bg-card min-h-[80px] transition-colors resize-none"
            />
            <div className="flex justify-end gap-2">
              <Button size="sm" variant="ghost" onClick={() => setIsEditing(false)} className="h-7 text-xs rounded-lg hover:bg-muted">{t('cancel')}</Button>
              <Button size="sm" onClick={handleEdit} disabled={isSubmitting} className="h-7 text-xs bg-primary text-primary-foreground rounded-lg hover:opacity-90">{t('save')}</Button>
            </div>
          </div>
        ) : (
          <div>
            <div 
                onClick={onReplyClick}
                className={cn(
                "text-xs leading-relaxed break-words whitespace-pre-wrap rounded-2xl px-4 py-2.5 relative cursor-pointer hover:ring-2 hover:ring-indigo-100 transition-all", 
                isFirst ? "bg-indigo-500/10 text-indigo-700 dark:text-indigo-200 font-medium border border-indigo-200/50 dark:border-indigo-300/20" : "bg-muted/30 text-foreground"
                )}
            >
                <ReactMarkdown 
                remarkPlugins={[remarkMath]} 
                rehypePlugins={[rehypeKatex]}
                >
                {processMathContent(answer.content)}
                </ReactMarkdown>
                
                {answer.is_teacher && (
                <button
                    onClick={(e) => { e.stopPropagation(); onReplyClick(); }}
                    className="absolute -bottom-2 -right-2 h-6 w-6 rounded-full bg-card shadow-sm border border-border flex items-center justify-center text-muted-foreground hover:text-indigo-600 hover:border-indigo-200 transition-all cursor-pointer z-10"
                    aria-label={t('replyToTeacher')}
                    title={t('replyToTeacher')}
                >
                    <ChatCircle className="h-3 w-3" />
                </button>
                )}
            </div>
            {/* Like Button */}
            <div className="flex items-center gap-2 mt-1 ml-1">
                <button onClick={handleLike} className={cn("flex items-center gap-1.5 text-[11px] font-bold transition-all px-2 py-0.5 rounded-full hover:bg-muted/50", isLiked ? "text-pink-500" : "text-muted-foreground/40 hover:text-pink-500/70")}>
                    <ThumbsUp className={cn("h-3 w-3", isLiked && "fill-current")} />
                    {likesCount > 0 && <span>{likesCount}</span>}
                </button>
            </div>
          </div>
        )}
      </div>
      {Dialog}
    </div>
  );
};

const ThreadCard = ({ question, onRefresh, isAdmin }: { question: any, onRefresh: () => void, isAdmin: boolean }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [replyContent, setReplyContent] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showInput, setShowInput] = useState(false);
  const { user } = useAuthStore();
  const { t } = useTranslation('qaSystem');
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const { confirm, Dialog } = useConfirm();

  // Editing state
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(question.content);

  // Like State
  const [likesCount, setLikesCount] = useState(question.likes_count || 0);
  const [isLiked, setIsLiked] = useState(question.is_liked || false);
  // Follow State
  const [isFollowed, setIsFollowed] = useState(question.is_followed || false);

  useEffect(() => {
    if (!isEditing) setEditContent(question.content);
  }, [question.content, isEditing]);

  const firstAnswer = question.first_answer;
  const otherAnswers = question.answers.slice(1);
  const hasOthers = otherAnswers.length > 0;

  // Auto-detect image attachment
  const isImageAttachment = question.attachment?.match(/\.(jpeg|jpg|gif|png|webp)$/i);

  const handleFollow = async () => {
    try {
        const { data } = await api.patch(`/qa/questions/${question.id}/action/`, { toggle_follow: true });
        setIsFollowed(data.is_followed);
        toast.success(data.is_followed ? t('followed') : t('unfollowed'));
    } catch(e) { toast.error(t('operationFailed')); }
  };

  const handleLike = async (e: React.MouseEvent) => {
      e.stopPropagation();
      try {
          const res = await api.patch(`/qa/questions/${question.id}/action/`, { toggle_like: true });
          setIsLiked(res.data.is_liked);
          setLikesCount(res.data.likes_count);
      } catch(e) { toast.error(t('operationFailed')); }
  };

  const handleUpdate = async () => {
     if (!editContent.trim()) return;
     try {
        await api.patch(`/qa/questions/${question.id}/`, { content: editContent });
        toast.success(t('updated'));
        setIsEditing(false);
        onRefresh();
     } catch(e) { toast.error(t('updateFailed')); }
  };

  const handleAction = async (action: string) => {
    try {
      if (action === 'delete') {
        if (!(await confirm(t('deleteQuestionConfirm')))) return;
        await api.delete(`/qa/questions/${question.id}/`);
        toast.success(t('questionDeleted'));
      } else {
        await api.patch(`/qa/questions/${question.id}/action/`, { [action]: true });
        toast.success(t('statusUpdated'));
      }
      onRefresh();
    } catch (e) { toast.error(t('operationFailed')); }
  };

  const handleReply = async () => {
    if (!replyContent.trim()) return;
    setIsSubmitting(true);
    try {
      await api.post('/qa/answers/', { question: question.id, content: replyContent });
      setReplyContent('');
      onRefresh();
      setIsExpanded(true); 
      setShowInput(false); // Close input after sending
      toast.success(t('replySubmitted'));
    } catch (e: any) { 
      toast.error(e.response?.data?.error || t('replyFailed')); 
    } finally {
      setIsSubmitting(false);
    }
  };

  const triggerReply = () => {
    setShowInput(true);
    setIsExpanded(true); 
    setTimeout(() => inputRef.current?.focus(), 100);
  };

  return (
    <Card className="border-none shadow-sm bg-card rounded-2xl md:rounded-3xl p-4 md:p-6 transition-all hover:shadow-md border border-border/40 group">
      {/* Header */}
      <div className="flex justify-between items-start mb-4">
        <div className="flex items-center gap-3">
          <Avatar className="h-10 w-10 border border-border shadow-sm">
            <AvatarImage src={question.user_detail.avatar_url} />
            <AvatarFallback>{question.user_detail.username[0]}</AvatarFallback>
          </Avatar>
          <div>
            <h4 className="text-sm font-bold text-foreground flex items-center gap-2">
              {question.user_detail.nickname || question.user_detail.username}
              {question.is_starred && <Star className="h-3 w-3 text-orange-500 fill-orange-500" />}
              {question.is_solved ? (
                <Badge variant="outline" className="text-[11px] h-4 px-1.5 bg-emerald-50 dark:bg-emerald-950/30 text-emerald-600 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800/40">{t('resolved')}</Badge>
              ) : (
                <Badge variant="outline" className="text-[11px] h-4 px-1.5 bg-muted text-muted-foreground border-border">{t('pending')}</Badge>
              )}
            </h4>
            <p className="text-[11px] text-muted-foreground font-bold uppercase tracking-widest mt-0.5 tabular-nums">
              {new Date(question.created_at).toLocaleString('zh-CN', {month: '2-digit', day: '2-digit', hour: '2-digit', minute:'2-digit'})}
            </p>
          </div>
        </div>
        
        {!isEditing && (
          <DropdownMenu modal={false}>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-8 w-8 rounded-full text-muted-foreground/50 hover:text-foreground">
                <DotsThree className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="rounded-xl">
              <DropdownMenuItem onClick={handleFollow} className="gap-2 text-xs font-bold">
                 <Eye className="h-3.5 w-3.5" /> {isFollowed ? t('unfollowQuestion') : t('followQuestion')}
              </DropdownMenuItem>
              
              {(isAdmin || user?.username === question.user_detail.username) && <DropdownMenuSeparator />}

              {isAdmin && (
                <>
                  <DropdownMenuItem onClick={() => handleAction('toggle_star')} className="gap-2 text-xs font-bold">
                    <Star className="h-3.5 w-3.5" /> {question.is_starred ? t('unstarQuestion') : t('starQuestion')}
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleAction('toggle_solved')} className="gap-2 text-xs font-bold">
                    {question.is_solved ? <Circle className="h-3.5 w-3.5"/> : <CheckCircle className="h-3.5 w-3.5"/>} 
                    {question.is_solved ? t('markUnsolved') : t('markSolved')}
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                </>
              )}
              {(isAdmin || user?.username === question.user_detail.username) && (
                <>
                  <DropdownMenuItem onClick={() => setIsEditing(true)} className="gap-2 text-xs font-bold">
                    <PencilSimple className="h-3.5 w-3.5" /> {t('editContent')}
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleAction('delete')} className="gap-2 text-xs font-bold text-red-600 focus:text-red-700 focus:bg-red-50">
                    <Trash className="h-3.5 w-3.5" /> {t('deleteQuestion')}
                  </DropdownMenuItem>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>

      {/* Question Content */}
      <div className="pl-0 md:pl-13 mb-5 md:mb-6">
        {isEditing ? (
             <div className="space-y-2 animate-in fade-in zoom-in-95 duration-200">
             <textarea
               value={editContent}
               onChange={e => setEditContent(e.target.value)}
               className="w-full text-sm p-4 rounded-xl border border-input bg-muted/30 focus:bg-card min-h-[120px] transition-colors resize-none leading-relaxed"
             />
             <div className="flex justify-end gap-2">
               <Button size="sm" variant="ghost" onClick={() => setIsEditing(false)} className="rounded-lg">{t('cancel')}</Button>
               <Button size="sm" onClick={handleUpdate} className="bg-primary text-primary-foreground rounded-lg hover:opacity-90">{t('save')}</Button>
             </div>
           </div>
        ) : (
          <div 
            onClick={triggerReply}
            className="text-sm font-medium text-foreground leading-relaxed whitespace-pre-wrap cursor-pointer hover:bg-muted/20 rounded-xl transition-colors -m-2 p-2"
          >
            <ReactMarkdown 
              remarkPlugins={[remarkMath]} 
              rehypePlugins={[rehypeKatex]}
            >
              {processMathContent(question.content)}
            </ReactMarkdown>
          </div>
        )}
        
        {/* Attachment Display */}
        {question.attachment && (
          <div className="mt-3">
            {isImageAttachment ? (
              <div className="rounded-xl overflow-hidden border border-border/50 max-w-[200px] md:max-w-sm group/img relative">
                <img src={question.attachment} alt="attachment" className="w-full h-auto max-h-[140px] md:max-h-[300px] object-cover" loading="lazy" />
                <a href={question.attachment} target="_blank" rel="noreferrer" className="absolute top-2 right-2 p-1.5 bg-black/50 text-white rounded-lg opacity-0 group-hover/img:opacity-100 transition-opacity">
                  <Paperclip className="h-3.5 w-3.5" />
                </a>
              </div>
            ) : (
              <a href={question.attachment} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl bg-muted/50 border border-border/50 text-xs font-bold text-primary hover:bg-muted transition-colors">
                <Paperclip className="h-3.5 w-3.5" /> {t('downloadAttachments')}
              </a>
            )}
          </div>
        )}

        {/* Like Button */}
        {!isEditing && (
            <div className="flex items-center gap-2 mt-4">
                <button onClick={handleLike} className={cn("flex items-center gap-1.5 text-[11px] font-bold transition-all px-2 py-0.5 rounded-full hover:bg-muted/50 border border-transparent hover:border-border/50", isLiked ? "text-pink-500 bg-pink-50 hover:bg-pink-100 border-pink-100" : "text-muted-foreground hover:text-pink-500/70")}>
                    <ThumbsUp className={cn("h-3 w-3", isLiked && "fill-current")} />
                    {likesCount > 0 && <span>{likesCount}</span>}
                </button>
            </div>
        )}
        
        {/* Admin Reply Trigger Button */}
        {isAdmin && !firstAnswer && !showInput && !isEditing && (
          <Button onClick={() => setShowInput(true)} size="sm" className="mt-4 rounded-xl bg-indigo-50 text-indigo-600 hover:bg-indigo-100 font-bold text-xs h-8">
            <ChatCircle className="w-3.5 h-3.5 mr-2" />
            {t('answerStudent')}
          </Button>
        )}
      </div>

      {/* First Answer (Teacher) */}
      {firstAnswer && (
        <div className="pl-2 md:pl-4 border-l-2 border-indigo-100 ml-1 md:ml-4 mb-2">
          <div className="relative">
            <AnswerItem answer={firstAnswer} isFirst={true} onReplyClick={triggerReply} onRefresh={onRefresh} />
          </div>
        </div>
      )}

      {/* Replies & Expansion */}
      {hasOthers && (
        <div className="pl-2 md:pl-8 mt-2">
          {isExpanded && (
            <div className="space-y-4 mb-4 border-l-2 border-muted ml-1 md:ml-4 pb-2 animate-in slide-in-from-top-2 duration-300">
              {otherAnswers.map((ans: any) => (
                <AnswerItem key={ans.id} answer={ans} isFirst={false} onReplyClick={triggerReply} onRefresh={onRefresh} />
              ))}
            </div>
          )}
          <Button 
            variant="ghost" 
            onClick={() => setIsExpanded(!isExpanded)}
            className="h-8 text-[12px] font-bold text-muted-foreground uppercase tracking-widest hover:text-foreground ml-1 md:ml-4"
          >
            {isExpanded ? <CaretUp className="mr-2 h-3 w-3" /> : <ArrowBendDownRight className="mr-2 h-3 w-3" />}
            {isExpanded ? t('collapseReplies') : t('viewReplies', { count: otherAnswers.length })}
          </Button>
        </div>
      )}

      {/* Reply Input */}
      {showInput && (
        <div className="pl-0 md:pl-13 mt-4 flex flex-col sm:flex-row gap-2 items-stretch sm:items-start animate-in fade-in slide-in-from-bottom-2">
          <textarea
            autoFocus
            ref={inputRef}
            value={replyContent} 
            onChange={e => setReplyContent(e.target.value)} 
            placeholder={isAdmin ? t('teacherReplyPlaceholder') : t('studentReplyPlaceholder')}
            className="w-full min-h-[40px] max-h-36 rounded-xl bg-muted/30 border border-transparent focus:bg-card transition-all text-xs font-medium px-3 py-2 resize-none leading-relaxed focus:outline-none focus:ring-2 focus:ring-ring/30"
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                handleReply();
              }
            }}
            onBlur={(e) => {
              // Only close if we are not clicking the Send button
              if (!e.relatedTarget || !(e.relatedTarget as HTMLElement).closest('.send-button')) {
                // Short delay to allow click event to trigger if it was the button
                setTimeout(() => setShowInput(false), 200);
              }
            }}
          />
          <div className="flex gap-1 justify-end sm:justify-start">
            <Button
              onMouseDown={(e) => e.preventDefault()}
              disabled={isSubmitting}
              onClick={handleReply}
              size="icon"
              aria-label={t('sendReply') || 'Send reply'}
              className="h-10 w-10 rounded-xl bg-primary text-primary-foreground shrink-0 shadow-lg hover:opacity-90 send-button"
            >
              {isSubmitting ? <Spinner className="h-4 w-4 animate-spin"/> : <PaperPlaneTilt className="h-4 w-4" />}
            </Button>
            <Button onClick={() => setShowInput(false)} size="icon" variant="ghost" aria-label={t('cancel') || 'Close'} className="h-10 w-10 rounded-xl text-muted-foreground hover:bg-muted">
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
      {Dialog}
    </Card>
  );
};

export const QASystem: React.FC = () => {
  const [questions, setQuestions] = useState<any[]>([]);
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const isMobile = useIsMobile();

  // New Question State
  const [qContent, setQContent] = useState('');
  const [qFile, setQFile] = useState<File | null>(null);
  const [isPosting, setIsPosting] = useState(false);
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { user } = useAuthStore();
  const { t } = useTranslation('qaSystem');
  const isAdmin = user?.role === 'admin';

  const fetchQuestions = async () => {
    setLoading(true);
    try {
      const res = await api.get('/qa/questions/', { params: { filter, search } });
      setQuestions(res.data);
    } catch (e) { toast.error(t('loadFailed')); }
    finally { setLoading(false); }
  };

  useEffect(() => { fetchQuestions(); }, [filter, search]);

  const handlePost = async () => {
    if (!qContent.trim()) return toast.error(t('enterContent'));
    setIsPosting(true);
    const fd = new FormData();
    fd.append('content', qContent);
    if (qFile) fd.append('attachment', qFile);

    try {
      await api.post('/qa/questions/', fd);
      toast.success(t('questionSent'));
      setQContent('');
      setQFile(null);
      fetchQuestions();
    } catch (e) {
      toast.error(t('sendFailed'));
    } finally {
      setIsPosting(false);
    }
  };

  return (
    <PageWrapper title={t('pageTitle')} subtitle={t('pageSubtitle')}>
      <div className="max-w-5xl mx-auto space-y-5 md:space-y-8 animate-in fade-in duration-500">
        
        {/* Top Input Area */}
        <Card className="border-none shadow-sm bg-card rounded-2xl md:rounded-[2rem] p-4 md:p-6 border border-border/50">
          <div className="space-y-4">
            <textarea 
              value={qContent}
              onChange={e => setQContent(e.target.value)}
              placeholder={t('questionPlaceholder')}
              className="w-full min-h-[100px] p-4 rounded-2xl bg-muted/60 border border-border/50 text-sm font-medium resize-none focus:ring-2 focus:ring-ring/30 transition-all placeholder:text-muted-foreground/40"
            />
            <div className={cn(isMobile ? "flex items-center gap-2" : "flex justify-between items-center")}>
              <div className={cn("flex items-center gap-2", isMobile && "flex-1 min-w-0")}>
                <Button 
                  variant="outline" 
                  onClick={() => fileInputRef.current?.click()}
                  className={cn(
                    "rounded-xl h-10 border-dashed border-2 gap-2 text-xs font-bold text-muted-foreground hover:text-primary hover:border-primary/30 hover:bg-primary/5",
                    isMobile ? "w-full justify-start px-3 min-w-0" : "px-4",
                    qFile && "border-solid border-primary text-primary bg-primary/5"
                  )}
                >
                  <Paperclip className="h-3.5 w-3.5" />
                  {isMobile ? <span className="truncate">{qFile ? qFile.name : t('addAttachment')}</span> : (qFile ? qFile.name : t('addAttachment'))}
                </Button>
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={e => setQFile(e.target.files?.[0] || null)}
                  className="hidden"
                  accept="image/*,application/pdf,.doc,.docx,.txt"
                />
              </div>
              <Button onClick={handlePost} disabled={isPosting} className={cn("h-10 rounded-xl bg-primary text-primary-foreground font-bold shadow hover:scale-[1.02] transition-transform text-xs uppercase tracking-widest", isMobile ? "shrink-0 px-5" : "px-8")}>
                {isPosting ? <Spinner className="h-4 w-4 animate-spin"/> : t('submitQuestion')}
              </Button>
            </div>
          </div>
        </Card>

        {/* Filter Bar */}
        <div className="flex flex-col md:flex-row justify-between items-stretch md:items-center gap-4">
          <div className="w-full md:w-auto overflow-x-auto">
          <div className="inline-flex min-w-max bg-muted/30 p-1 rounded-2xl border border-border/50">
            {[
              { id: 'all', label: t('filterAll') },
              { id: 'followed', label: t('filterFollowed') },
              { id: 'unsolved', label: t('filterUnsolved') },
              { id: 'solved', label: t('filterSolved') },
              { id: 'starred', label: t('filterStarred') },
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setFilter(tab.id)}
                className={cn(
                  "px-6 py-2 rounded-xl text-xs font-bold transition-all duration-300",
                  filter === tab.id 
                    ? "bg-card text-foreground shadow-sm scale-105" 
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>
          </div>
          <div className="relative w-full md:w-auto">
            <MagnifyingGlass className="absolute left-3.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/50" />
            <Input 
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder={t('searchHistory')}
              className="pl-9 h-10 rounded-xl bg-card border-transparent hover:border-border focus:border-border shadow-sm w-full md:w-64 text-xs font-bold transition-all"
            />
          </div>
        </div>

        {/* List */}
        <div className="space-y-4 pb-10">
          {loading ? (
            <div className="py-20 text-center flex justify-center"><Spinner className="h-8 w-8 animate-spin text-muted-foreground/20"/></div>
          ) : questions.length === 0 ? (
            <div className="py-20 text-center space-y-4">
              <ChatCircleText className="h-12 w-12 mx-auto text-muted-foreground/20" />
              <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest">{t('noResults')}</p>
            </div>
          ) : (
            questions.map(q => (
              <ThreadCard key={q.id} question={q} onRefresh={fetchQuestions} isAdmin={isAdmin} />
            ))
          )}
        </div>
      </div>
    </PageWrapper>
  );
};
