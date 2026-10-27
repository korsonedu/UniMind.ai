import { formatApiErrorToast } from '@/lib/apiError';
import type { QAQuestion, QAAnswer } from '@/types/api';
import React, { useCallback, useState, useEffect, useRef } from 'react';
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { ChatCircleText, MagnifyingGlass, Paperclip, PaperPlaneTilt, DotsThree, Star, Trash, CheckCircle, Circle, ArrowLeft, Spinner, ChatCircle, PencilSimple, ThumbsUp, Eye } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
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
import { MarkdownContent } from '@/components/MarkdownContent';
import '@/styles/qa.css';

// --- Sub-Components ---

const AnswerItem = ({ answer, onReplyClick, onRefresh }: { answer: QAAnswer, onReplyClick: () => void, onRefresh: () => void }) => {
  const user = useAuthStore(s => s.user);
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(answer.content);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Like State
  const [likesCount, setLikesCount] = useState(answer.likes_count || 0);
  const [isLiked, setIsLiked] = useState(answer.is_liked || false);
  const { confirm, Dialog } = useConfirm();


  const handleEdit = async () => {
    if (!editContent.trim()) return;
    setIsSubmitting(true);
    try {
      await api.patch(`/qa/answers/${answer.id}/`, { content: editContent });
      toast.success('回复已更新');
      setIsEditing(false);
      onRefresh();
    } catch { toast.error('更新失败'); }
    finally { setIsSubmitting(false); }
  };

  const handleDelete = async () => {
    if (!(await confirm('确认删除这条回复？'))) return;
    try {
      await api.delete(`/qa/answers/${answer.id}/`);
      toast.success('回复已删除');
      onRefresh();
    } catch { toast.error('删除失败'); }
  };

  const handleLike = async (e: React.MouseEvent) => {
      e.stopPropagation();
      try {
          const res = await api.patch(`/qa/answers/${answer.id}/action/`, { toggle_like: true });
          setIsLiked(res.data.is_liked);
          setLikesCount(res.data.likes_count);
      } catch { toast.error('操作失败'); }
  };

  return (
    <div className="um-qa-answer flex gap-3 text-left group/answer relative">
      <Avatar className="um-qa-answer-avatar h-8 w-8 shrink-0">
        <AvatarImage src={answer.user_detail.avatar_url} />
        <AvatarFallback className={cn("font-bold", answer.is_teacher ? "bg-indigo-100 text-indigo-700" : "bg-muted")}>
          {answer.user_detail.username[0]}
        </AvatarFallback>
      </Avatar>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-1">
          <div className="um-qa-answer-meta flex items-center gap-2">
            <span className={cn("text-[11px] font-bold", answer.is_teacher ? "text-indigo-600" : "text-foreground")}>
              {answer.user_detail.nickname || answer.user_detail.username}
            </span>
            {answer.is_teacher && <Badge variant="secondary" className="um-qa-teacher-badge">老师</Badge>}
            <span className="text-[11px] text-muted-foreground tabular-nums">
              {new Date(answer.created_at).toLocaleString(navigator.language || 'zh-CN', {month: '2-digit', day: '2-digit', hour: '2-digit', minute:'2-digit'})}
            </span>
          </div>

          {/* Action Menu (Only visible on hover for owner/admin) */}
          {(user?.username === answer.user_detail.username) && !isEditing && (
            <DropdownMenu modal={false}>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" aria-label="回复操作" className="um-qa-menu-button h-8 w-8 transition-opacity">
                  <DotsThree className="h-5 w-5 text-muted-foreground" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => { setEditContent(answer.content); setIsEditing(true); }} className="gap-2 text-xs">
                  <PencilSimple className="h-3 w-3" /> 编辑
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handleDelete} className="gap-2 text-xs text-red-600 focus:text-red-700 focus:bg-red-50">
                  <Trash className="h-3 w-3" /> 删除
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>

        {isEditing ? (
          <div className="space-y-2 animate-in fade-in slide-in-from-bottom-1 duration-200">
            <textarea
              value={editContent}
              onChange={e => setEditContent(e.target.value)}
              className="w-full text-xs p-3 rounded-xl border border-input bg-muted/30 focus:bg-card min-h-[80px] transition-colors resize-none"
            />
            <div className="flex justify-end gap-2">
              <Button size="sm" variant="ghost" onClick={() => setIsEditing(false)} className="h-7 text-xs rounded-lg hover:bg-muted">取消</Button>
              <Button size="sm" onClick={handleEdit} disabled={isSubmitting} className="h-7 text-xs bg-primary text-primary-foreground rounded-lg hover:opacity-90">保存</Button>
            </div>
          </div>
        ) : (
          <div>
            <div
                className={cn(
                "um-qa-answer-bubble text-sm leading-relaxed break-words relative",
                answer.is_teacher ? "um-qa-answer-bubble-teacher" : "text-foreground"
                )}
            >
                <MarkdownContent className="prose prose-sm dark:prose-invert max-w-none" content={processMathContent(answer.content)} />
            </div>
            {/* Like Button */}
            <div className="flex items-center gap-2 mt-1 ml-1">
                <button onClick={handleLike} aria-label={isLiked ? '取消点赞回复' : '点赞回复'} aria-pressed={isLiked} className={cn("um-qa-like flex items-center gap-1.5 text-xs transition-colors px-2 py-1 rounded-lg", isLiked ? "is-active" : "text-muted-foreground")}>
                    <ThumbsUp className={cn("h-4 w-4", isLiked && "fill-current")} />
                    {likesCount > 0 && <span>{likesCount}</span>}
                </button>
                <button onClick={onReplyClick} className="um-qa-text-action">{answer.is_teacher ? '追问' : '回复'}</button>
            </div>
          </div>
        )}
      </div>
      {Dialog}
    </div>
  );
};

const ThreadCard = ({ question, onRefresh, isAdmin, detail = false, onDelete }: { question: QAQuestion, onRefresh: () => void, isAdmin: boolean, detail?: boolean, onDelete?: () => void }) => {
  const location = useLocation();
  const [replyContent, setReplyContent] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const submittingRef = useRef(false);
  const [isContentExpanded, setIsContentExpanded] = useState(false);
  const user = useAuthStore(s => s.user);
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


  const firstAnswer = question.first_answer;
  const teacherAnswer = question.answers.find((answer: QAAnswer) => answer.is_teacher);
  const canReply = !!firstAnswer || isAdmin || !!user?.is_institution_teacher;
  const isLongQuestion = question.content.length > 280 || question.content.split('\n').length > 6;

  // Auto-detect image attachment
  const isImageAttachment = question.attachment?.match(/\.(jpeg|jpg|gif|png|webp)$/i);

  const handleFollow = async () => {
    try {
        const { data } = await api.patch(`/qa/questions/${question.id}/action/`, { toggle_follow: true });
        setIsFollowed(data.is_followed);
        toast.success(data.is_followed ? '已关注' : '已取消关注');
    } catch { toast.error('操作失败'); }
  };

  const handleLike = async (e: React.MouseEvent) => {
      e.stopPropagation();
      try {
          const res = await api.patch(`/qa/questions/${question.id}/action/`, { toggle_like: true });
          setIsLiked(res.data.is_liked);
          setLikesCount(res.data.likes_count);
      } catch { toast.error('操作失败'); }
  };

  const handleUpdate = async () => {
     if (!editContent.trim()) return;
     try {
        await api.patch(`/qa/questions/${question.id}/`, { content: editContent });
        toast.success('已更新');
        setIsEditing(false);
        onRefresh();
     } catch { toast.error('更新失败'); }
  };

  const handleAction = async (action: string) => {
    try {
      if (action === 'delete') {
        if (!(await confirm('确认删除这个提问？'))) return;
        await api.delete(`/qa/questions/${question.id}/`);
        toast.success('提问已删除');
        if (onDelete) { onDelete(); return; }
      } else {
        await api.patch(`/qa/questions/${question.id}/action/`, { [action]: true });
        toast.success('状态已更新');
      }
      onRefresh();
    } catch { toast.error('操作失败'); }
  };

  const handleReply = async () => {
    if (submittingRef.current) return toast.info('正在提交', {
      id: 'qa-submit-pending',
      description: '收到了。第二次点击没有让它更收到。',
      classNames: { description: 'italic text-muted-foreground' },
    });
    if (!replyContent.trim()) return;
    submittingRef.current = true;
    setIsSubmitting(true);
    try {
      await api.post('/qa/answers/', { question: question.id, content: replyContent });
      setReplyContent('');
      onRefresh();
      toast.success('回复已提交');
    } catch (e: unknown) {
      toast.error(formatApiErrorToast(e, '回复失败'));
    } finally {
      submittingRef.current = false;
      setIsSubmitting(false);
    }
  };

  const triggerReply = () => {
    if (!canReply) return;
    inputRef.current?.focus();
  };

  return (
    <article className={cn('um-qa-thread group', detail && 'is-detail')} aria-label={`${question.user_detail.nickname || question.user_detail.username}的提问`}>
      {/* Header */}
      <div className="um-qa-thread-header flex justify-between items-start">
        <div className="flex items-center gap-3 min-w-0">
          <Avatar className="um-qa-question-avatar h-10 w-10 shrink-0">
            <AvatarImage src={question.user_detail.avatar_url} />
            <AvatarFallback>{question.user_detail.username[0]}</AvatarFallback>
          </Avatar>
          <div className="min-w-0">
            <div className="um-qa-author text-sm text-foreground flex items-center gap-2">
              <h4 className="font-semibold">{question.user_detail.nickname || question.user_detail.username}</h4>
              <time className="um-qa-time text-xs text-muted-foreground tabular-nums" dateTime={question.created_at}>
                {new Date(question.created_at).toLocaleString('zh-CN', {month: '2-digit', day: '2-digit', hour: '2-digit', minute:'2-digit'})}
              </time>
              {question.is_starred && <span className="um-qa-featured"><Star className="h-3 w-3" weight="fill" />精选</span>}
              {question.is_solved ? (
                <Badge variant="outline" className="um-qa-status is-solved text-[11px] h-5 px-1.5">已解决</Badge>
              ) : (
                <Badge variant="outline" className="um-qa-status text-[11px] h-5 px-1.5">{firstAnswer ? '讨论中' : '待回复'}</Badge>
              )}
            </div>
          </div>
        </div>

        {!isEditing && (
          <DropdownMenu modal={false}>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" aria-label="问题操作" className="um-qa-menu-button h-8 w-8 rounded-full text-muted-foreground hover:text-foreground">
                <DotsThree className="h-5 w-5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="rounded-xl">
              <DropdownMenuItem onClick={handleFollow} className="gap-2 text-xs font-bold">
                 <Eye className="h-3.5 w-3.5" /> {isFollowed ? '取消关注' : '关注问题'}
              </DropdownMenuItem>

              {(isAdmin || user?.username === question.user_detail.username) && <DropdownMenuSeparator />}

              {isAdmin && (
                <>
                  <DropdownMenuItem onClick={() => handleAction('toggle_star')} className="gap-2 text-xs font-bold">
                    <Star className="h-3.5 w-3.5" /> {question.is_starred ? '取消星标' : '设为精选'}
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleAction('toggle_solved')} className="gap-2 text-xs font-bold">
                    {question.is_solved ? <Circle className="h-3.5 w-3.5"/> : <CheckCircle className="h-3.5 w-3.5"/>}
                    {question.is_solved ? '标记未解决' : '标记已解决'}
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                </>
              )}
              {(isAdmin || user?.username === question.user_detail.username) && (
                <>
                  <DropdownMenuItem onClick={() => { setEditContent(question.content); setIsEditing(true); }} className="gap-2 text-xs font-bold">
                    <PencilSimple className="h-3.5 w-3.5" /> 编辑内容
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => handleAction('delete')} className="gap-2 text-xs font-bold text-red-600 focus:text-red-700 focus:bg-red-50">
                    <Trash className="h-3.5 w-3.5" /> 删除提问
                  </DropdownMenuItem>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>

      {/* Question Content */}
      <div className="um-qa-thread-content">
        {isEditing ? (
             <div className="space-y-2 animate-in fade-in slide-in-from-bottom-1 duration-200">
             <textarea
               value={editContent}
               onChange={e => setEditContent(e.target.value)}
               className="w-full text-sm p-4 rounded-xl border border-input bg-muted/30 focus:bg-card min-h-[120px] transition-colors resize-none leading-relaxed"
             />
             <div className="flex justify-end gap-2">
               <Button size="sm" variant="ghost" onClick={() => setIsEditing(false)} className="rounded-lg">取消</Button>
               <Button size="sm" onClick={handleUpdate} className="bg-primary text-primary-foreground rounded-lg hover:opacity-90">保存</Button>
             </div>
           </div>
        ) : (
          <div className={cn("um-qa-question-body text-sm text-foreground leading-relaxed", isLongQuestion && !isContentExpanded && !detail && 'is-collapsed')}>
            <MarkdownContent className="prose prose-sm dark:prose-invert max-w-none" content={processMathContent(question.content)} />
          </div>
        )}
        {!isEditing && isLongQuestion && !detail && (
          <button className="um-qa-text-action um-qa-read-more" onClick={() => setIsContentExpanded(!isContentExpanded)} aria-expanded={isContentExpanded}>
            {isContentExpanded ? '收起正文' : '展开全文'}
          </button>
        )}

        {/* Attachment Display */}
        {question.attachment && (
          <div className="mt-3">
            {isImageAttachment ? (
              <div className="um-qa-attachment-image rounded-xl overflow-hidden border border-border/50 max-w-sm group/img relative">
                <img src={question.attachment} alt="问题附件" className="w-full h-auto max-h-[300px] object-contain" loading="lazy" />
                <a href={question.attachment} target="_blank" rel="noreferrer" aria-label="查看原图" className="absolute top-2 right-2 p-1.5 bg-[#0b0d10]/50 text-white rounded-lg opacity-100 md:opacity-0 group-hover/img:opacity-100 focus:opacity-100 transition-opacity">
                  <Paperclip className="h-3.5 w-3.5" />
                </a>
              </div>
            ) : (
              <a href={question.attachment} target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl bg-muted/50 border border-border/50 text-xs font-bold text-primary hover:bg-muted transition-colors">
                <Paperclip className="h-3.5 w-3.5" /> 附件下载
              </a>
            )}
          </div>
        )}

        {!detail && teacherAnswer && !isEditing && (
          <div className="um-qa-answer-preview">
            <span>{teacherAnswer.user_detail.nickname || teacherAnswer.user_detail.username} · 老师解答</span>
            <div><MarkdownContent className="prose prose-sm dark:prose-invert max-w-none" content={processMathContent(teacherAnswer.content)} /></div>
          </div>
        )}

        {!isEditing && (
            <div className="um-qa-thread-actions flex items-center gap-2 mt-3">
                {detail ? <span className="um-qa-discussion-button"><ChatCircle className="h-[18px] w-[18px]" />讨论 {question.reply_count ?? question.answers.length}</span> : <Link to={`/qa/${question.id}${location.search}`} className="um-qa-discussion-button">
                  <ChatCircle className="h-[18px] w-[18px]" />
                  <span>{`讨论 ${question.reply_count ?? question.answers.length}`}</span>
                </Link>}
                <button onClick={handleFollow} className={cn('um-qa-follow-button', isFollowed && 'is-active')} aria-pressed={isFollowed}>
                  <Eye className="h-[18px] w-[18px]" />{isFollowed ? '已关注' : '关注'}
                </button>
                <button onClick={handleLike} aria-label={isLiked ? '取消点赞问题' : '点赞问题'} aria-pressed={isLiked} className={cn("um-qa-like flex items-center gap-1.5 text-xs transition-colors px-2 py-1 rounded-lg", isLiked ? "is-active" : "text-muted-foreground")}>
                    <ThumbsUp className={cn("h-4 w-4", isLiked && "fill-current")} />
                    {likesCount > 0 && <span>{likesCount}</span>}
                </button>
            </div>
        )}

      </div>

      {detail && !isEditing && question.answers.length > 0 && (
        <section className="um-qa-reply-list" aria-label="全部回复">
          {question.answers.map((answer: QAAnswer) => (
            <AnswerItem key={answer.id} answer={answer} onReplyClick={triggerReply} onRefresh={onRefresh} />
          ))}
        </section>
      )}

      {detail && !firstAnswer && (
        <p className="um-qa-discussion-empty">{canReply ? '还没有回复，你可以提交第一个回答。' : '等待老师解答，你可以关注问题，接收后续回复通知。'}</p>
      )}

      {detail && canReply && !isEditing && (
        <div className="um-qa-reply-composer flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={replyContent}
            onChange={e => setReplyContent(e.target.value)}
            aria-label={firstAnswer ? '回复内容' : '回答内容'}
            placeholder={firstAnswer ? '写下你的回复…' : '写下你的解答…'}
            className="w-full min-h-[40px] max-h-36 rounded-xl bg-muted/30 border border-transparent focus:bg-card transition-all text-xs font-medium px-3 py-2 resize-none leading-relaxed focus:outline-none focus:ring-2 focus:ring-ring/30"
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                handleReply();
              }
            }}
          />
          <div className="flex gap-1 justify-end sm:justify-start">
            <Button
              onMouseDown={(e) => e.preventDefault()}
              disabled={!replyContent.trim()}
              aria-disabled={isSubmitting || !replyContent.trim()}
              aria-busy={isSubmitting}
              onClick={handleReply}
              size="icon"
              aria-label="发送回复"
              className="h-9 w-9 rounded-full bg-primary text-primary-foreground shrink-0 hover:opacity-90 send-button aria-disabled:cursor-wait aria-disabled:opacity-50"
            >
              {isSubmitting ? <Spinner className="h-4 w-4 animate-spin"/> : <PaperPlaneTilt className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      )}
      {Dialog}
    </article>
  );
};

export const QASystem: React.FC = () => {
  const [questions, setQuestions] = useState<QAQuestion[]>([]);
  const [searchParams, setSearchParams] = useSearchParams();
  const filter = searchParams.get('filter') || 'all';
  const search = searchParams.get('search') || '';
  const [loading, setLoading] = useState(true);
  const [nextPage, setNextPage] = useState<number | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const questionsRequestRef = useRef(0);
  const loadedPagesRef = useRef(1);

  // New Question State
  const [qContent, setQContent] = useState('');
  const [qFile, setQFile] = useState<File | null>(null);
  const [isPosting, setIsPosting] = useState(false);
  const postingRef = useRef(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const questionInputRef = useRef<HTMLTextAreaElement>(null);
  const user = useAuthStore(s => s.user);
  const isAdmin = false;

  const updateQuery = (name: string, value: string) => {
    setSearchParams(params => {
      if (value && value !== 'all') params.set(name, value);
      else params.delete(name);
      return params;
    }, { replace: true });
  };

  const [questionQuery, setQuestionQuery] = useState({ filter, search });
  if (questionQuery.filter !== filter || questionQuery.search !== search) {
    setQuestionQuery({ filter, search });
    setLoading(true);
    loadedPagesRef.current = 1;
  }

  const fetchQuestions = useCallback(async (background = false, page = 1) => {
    const requestId = ++questionsRequestRef.current;
    if (page > 1) setLoadingMore(true);
    const lastPage = background && page === 1 ? loadedPagesRef.current : page;
    try {
      const items: QAQuestion[] = [];
      let currentPage = page;
      let hasNext = false;
      for (; currentPage <= lastPage; currentPage++) {
        const { data } = await api.get('/qa/questions/', { params: { filter, search, page: currentPage } });
        if (requestId !== questionsRequestRef.current) return;
        items.push(...(Array.isArray(data) ? data : data.results));
        hasNext = !Array.isArray(data) && !!data.next;
        if (!hasNext || currentPage === lastPage) break;
      }
      if (requestId !== questionsRequestRef.current) return;
      setQuestions(previous => page === 1 ? items : [...previous, ...items.filter(item => !previous.some(question => question.id === item.id))]);
      loadedPagesRef.current = currentPage;
      setNextPage(hasNext ? currentPage + 1 : null);
    } catch {
      if (requestId === questionsRequestRef.current) toast.error('加载失败');
    } finally {
      if (requestId === questionsRequestRef.current) {
        setLoadingMore(false);
        if (!background) setLoading(false);
      }
    }
  }, [filter, search]);
  const refreshFetchQuestions = useCallback((background = false) => {
    if (!background) setLoading(true);
    return fetchQuestions(background);
  }, [fetchQuestions]);


  useEffect(() => { fetchQuestions(); }, [fetchQuestions, filter, search]);

  useEffect(() => {
    const input = questionInputRef.current;
    if (!input) return;
    input.style.height = 'auto';
    input.style.height = `${Math.min(input.scrollHeight, 176)}px`;
    input.style.overflowY = input.scrollHeight > 176 ? 'auto' : 'hidden';
  }, [qContent]);

  const handlePost = async () => {
    if (postingRef.current) return toast.info('正在提交', {
      id: 'qa-submit-pending',
      description: '收到了。第二次点击没有让它更收到。',
      classNames: { description: 'italic text-muted-foreground' },
    });
    if (!qContent.trim()) return toast.error('请输入问题内容');
    postingRef.current = true;
    setIsPosting(true);
    const fd = new FormData();
    fd.append('content', qContent);
    if (qFile) fd.append('attachment', qFile);

    try {
      await api.post('/qa/questions/', fd);
      toast.success('提问已发送');
      setQContent('');
      setQFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      refreshFetchQuestions();
    } catch {
      toast.error('发送失败');
    } finally {
      postingRef.current = false;
      setIsPosting(false);
    }
  };

  return (
    <PageWrapper title="答疑" subtitle="学术疑问 · 权威解答 · 深度探讨">
      <div className="um-qa max-w-4xl mx-auto">
        {/* Filter Bar */}
        <div className="um-qa-toolbar flex flex-col md:flex-row justify-between items-stretch md:items-center gap-3">
          <div className="w-full md:w-auto overflow-x-auto">
          <div className="um-qa-filters inline-flex min-w-max">
            {[
              { id: 'all', label: '全部' },
              { id: 'followed', label: '关注' },
              { id: 'unsolved', label: '待解答' },
              { id: 'solved', label: '已解决' },
              { id: 'starred', label: '精选' },
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => updateQuery('filter', tab.id)}
                aria-pressed={filter === tab.id}
                className={cn(
                  "um-qa-filter px-4 py-2 text-[13px] font-medium transition-colors",
                  filter === tab.id
                    ? "is-active text-primary"
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
              onChange={e => updateQuery('search', e.target.value)}
              placeholder="搜索历史问答..."
              aria-label="搜索问答"
              className="um-qa-search pl-9 h-10 w-full md:w-64 text-[13px] transition-colors"
            />
          </div>
        </div>

        <div className="um-qa-composer" role="group" aria-label="提问">
          <div className="um-qa-new-question">
            <Avatar className="um-qa-composer-avatar h-9 w-9 shrink-0"><AvatarImage src={user?.avatar_url} /><AvatarFallback>{(user?.nickname || user?.username || '我')[0]}</AvatarFallback></Avatar>
            <div className="um-qa-composer-field min-w-0">
              <textarea
                ref={questionInputRef}
                rows={2}
                value={qContent}
                onChange={e => setQContent(e.target.value)}
                placeholder="你遇到了什么问题？"
                aria-label="问题内容"
                className="um-qa-composer-input w-full text-sm resize-none"
              />
              <div className="um-qa-composer-actions flex items-center gap-2">
                <Button variant="ghost" onClick={() => fileInputRef.current?.click()} className="um-qa-attachment-button gap-2 text-xs">
                  <Paperclip className="h-5 w-5 shrink-0" />
                  <span className="truncate">{qFile ? qFile.name : '添加附件'}</span>
                </Button>
                <Button onClick={handlePost} disabled={!qContent.trim()} aria-disabled={isPosting || !qContent.trim()} aria-busy={isPosting} className="um-qa-submit shrink-0 px-4 text-xs aria-disabled:cursor-wait aria-disabled:opacity-50">
                  {isPosting ? <Spinner className="h-4 w-4 animate-spin" /> : '提交问题'}
                </Button>
              </div>
            </div>
          </div>
          <input type="file" ref={fileInputRef} onChange={e => setQFile(e.target.files?.[0] || null)} className="hidden" accept="image/*,application/pdf,.doc,.docx,.txt" />
        </div>

        {/* List */}
        <section className="um-qa-list pb-10" aria-label="问题流">
          {loading ? (
            <div className="py-20 text-center flex justify-center"><Spinner className="h-8 w-8 animate-spin text-muted-foreground/20"/></div>
          ) : questions.length === 0 ? (
            <div className="py-20 text-center space-y-4">
              <ChatCircleText className="h-12 w-12 mx-auto text-muted-foreground/20" />
              <p className="text-sm text-muted-foreground">暂无相关问题</p>
              <p className="text-xs italic text-muted-foreground">答案是 42，但我们得先知道问题。——《银河搭车客指南》</p>
            </div>
          ) : (
            questions.map(q => (
              <ThreadCard key={q.id} question={q} onRefresh={() => refreshFetchQuestions(true)} isAdmin={isAdmin} />
            ))
          )}
          {!loading && nextPage && (
            <Button variant="ghost" disabled={loadingMore} onClick={() => fetchQuestions(true, nextPage)} className="w-full mt-4">
              {loadingMore ? '加载中…' : '加载更多'}
            </Button>
          )}
        </section>
      </div>
    </PageWrapper>
  );
};

export const QuestionDetail: React.FC = () => {
  const { id } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const user = useAuthStore(s => s.user);
  const [question, setQuestion] = useState<QAQuestion | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const returnPath = `/qa${location.search}`;

  const refresh = async () => {
    try {
      const { data } = await api.get(`/qa/questions/${id}/`);
      setQuestion(data);
    } catch { toast.error('加载问题失败，请重试'); }
  };

  const [loadingQuestionId, setLoadingQuestionId] = useState(id);
  if (loadingQuestionId !== id) {
    setLoadingQuestionId(id);
    setLoading(true); setFailed(false); setQuestion(null);
  }

  useEffect(() => {
    let active = true;
    api.get(`/qa/questions/${id}/`).then(({ data }) => {
      if (active) setQuestion(data);
    }).catch(() => {
      if (active) setFailed(true);
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [id]);

  return (
    <PageWrapper title="问题详情">
      <div className="um-qa um-qa-detail">
        <Link to={returnPath} className="um-qa-back"><ArrowLeft className="h-[18px] w-[18px]" />返回问题流</Link>
        {loading ? <div className="py-16 flex justify-center"><Spinner className="h-6 w-6 animate-spin text-muted-foreground" /></div> : failed ? (
          <p className="py-16 text-center text-sm text-muted-foreground">暂时无法查看这个问题，请返回问题流重试。</p>
        ) : question && (
          <ThreadCard key={question.id} question={question} detail isAdmin={false} onRefresh={refresh} onDelete={() => navigate(returnPath)} />
        )}
      </div>
    </PageWrapper>
  );
};
