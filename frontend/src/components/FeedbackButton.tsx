import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Chat, X, PaperPlaneTilt, Bug, Lightbulb, Question } from '@phosphor-icons/react';
import { toast } from 'sonner';
import api from '@/lib/api';
import { useTranslation } from 'react-i18next';

const CATEGORIES = [
  { key: 'bug', icon: Bug, label: 'Bug 反馈', color: 'bg-red-50 text-red-600 border-red-100' },
  { key: 'feature', icon: Lightbulb, label: '功能建议', color: 'bg-amber-50 text-amber-600 border-amber-100' },
  { key: 'other', icon: Question, label: '其他', color: 'bg-blue-50 text-blue-600 border-blue-100' },
] as const;

export function FeedbackButton() {
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState<string>('bug');
  const [content, setContent] = useState('');
  const [contact, setContact] = useState('');
  const [sending, setSending] = useState(false);

  const handleSubmit = async () => {
    if (!content.trim()) {
      toast.error('请输入反馈内容');
      return;
    }
    setSending(true);
    try {
      await api.post('/users/feedback/', {
        category,
        content: content.trim(),
        contact: contact.trim(),
        page_url: window.location.pathname,
      });
      toast.success('感谢您的反馈！');
      setContent('');
      setContact('');
      setOpen(false);
    } catch {
      toast.error('提交失败，请稍后重试');
    } finally {
      setSending(false);
    }
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 z-50 h-12 w-12 rounded-full bg-black text-white shadow-lg flex items-center justify-center hover:scale-110 transition-transform"
        aria-label="反馈"
      >
        <Chat className="h-5 w-5" />
      </button>
    );
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 w-80 bg-white rounded-2xl shadow-2xl border border-black/5 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-black/5">
        <span className="text-sm font-bold">意见反馈</span>
        <button onClick={() => setOpen(false)} className="text-muted-foreground hover:text-foreground">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="p-4 space-y-4">
        <div className="flex gap-2">
          {CATEGORIES.map(cat => {
            const Icon = cat.icon;
            return (
              <button
                key={cat.key}
                onClick={() => setCategory(cat.key)}
                className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-bold border transition-all ${
                  category === cat.key ? cat.color : 'bg-slate-50 text-muted-foreground border-transparent'
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                {cat.label}
              </button>
            );
          })}
        </div>

        <textarea
          value={content}
          onChange={e => setContent(e.target.value)}
          placeholder="描述您遇到的问题或建议..."
          className="w-full bg-slate-50 border-none rounded-xl p-3 min-h-[100px] text-sm focus:outline-none focus:ring-1 focus:ring-black/10 resize-none"
          maxLength={2000}
        />

        <Input
          value={contact}
          onChange={e => setContact(e.target.value)}
          placeholder="联系方式（选填，方便我们回复）"
          className="bg-slate-50 border-none h-9 rounded-xl text-xs"
        />

        <Button
          onClick={handleSubmit}
          disabled={sending || !content.trim()}
          className="w-full h-10 bg-black text-white rounded-xl text-xs font-bold"
        >
          <PaperPlaneTilt className="mr-2 h-3.5 w-3.5" />
          {sending ? '提交中...' : '提交反馈'}
        </Button>
      </div>
    </div>
  );
}
