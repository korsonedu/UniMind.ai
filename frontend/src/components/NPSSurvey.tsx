import React, { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import api from '@/lib/api';
import { toast } from 'sonner';
import { X, Star } from 'lucide-react';
import { useAuthStore } from '@/store/useAuthStore';

export const NPSSurvey: React.FC = () => {
  const [visible, setVisible] = useState(false);
  const [score, setScore] = useState<number | null>(null);
  const [feedback, setFeedback] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const user = useAuthStore(s => s.user);

  const checkStatus = useCallback(async () => {
    try {
      const res = await api.get('/users/nps/status/');
      if (res.data.should_show) {
        // 延迟 3 秒弹出，不打断用户操作
        setTimeout(() => setVisible(true), 3000);
      }
    } catch {
      // 静默失败，不影响用户体验
    }
  }, []);

  useEffect(() => {
    if (!user) return;
    // 每次页面加载检查一次
    const lastCheck = sessionStorage.getItem('nps_checked');
    if (!lastCheck) {
      checkStatus();
      sessionStorage.setItem('nps_checked', '1');
    }
  }, [checkStatus, user]);

  const handleSubmit = async () => {
    if (score === null) return;
    setSubmitting(true);
    try {
      await api.post('/users/nps/submit/', { score, feedback });
      setSubmitted(true);
      toast.success('感谢你的反馈！');
      setTimeout(() => setVisible(false), 2000);
    } catch {
      toast.error('提交失败，请稍后重试');
    } finally {
      setSubmitting(false);
    }
  };

  if (!visible) return null;

  return (
    <div className="fixed bottom-6 right-6 z-50 animate-in slide-in-from-bottom-4 duration-500">
      <div className="w-[380px] bg-white rounded-2xl border border-black/[0.08] shadow-[0_4px_24px_rgba(0,0,0,0.12)] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-5 pb-2">
          <div className="flex items-center gap-2">
            <Star className="h-4 w-4 text-amber-500 fill-amber-500" />
            <span className="text-sm font-semibold">产品满意度调查</span>
          </div>
          <button
            onClick={() => setVisible(false)}
            className="p-1 rounded-full hover:bg-[#F5F5F7] transition-colors"
          >
            <X className="h-4 w-4 text-[#8E8E93]" />
          </button>
        </div>

        {submitted ? (
          <div className="px-5 pb-5 pt-4 text-center">
            <div className="text-3xl mb-2">🎉</div>
            <p className="text-sm font-medium">感谢你的反馈！</p>
            <p className="text-xs text-[#8E8E93] mt-1">我们会持续改进产品体验</p>
          </div>
        ) : (
          <div className="px-5 pb-5 space-y-4">
            {/* Question */}
            <p className="text-sm text-[#6E6E73]">
              你有多大可能向朋友推荐 UniMind？
            </p>

            {/* Score buttons */}
            <div className="flex gap-1">
              {Array.from({ length: 11 }, (_, i) => (
                <button
                  key={i}
                  onClick={() => setScore(i)}
                  className={cn(
                    "flex-1 h-9 rounded-lg text-xs font-medium transition-all",
                    score === i
                      ? i >= 9 ? 'bg-emerald-500 text-white shadow-sm'
                        : i >= 7 ? 'bg-amber-500 text-white shadow-sm'
                        : 'bg-red-500 text-white shadow-sm'
                      : "bg-[#F5F5F7] text-[#6E6E73] hover:bg-[#E8E8ED]"
                  )}
                >
                  {i}
                </button>
              ))}
            </div>

            <div className="flex justify-between text-[10px] text-[#AEAEB2] px-0.5">
              <span>完全不推荐</span>
              <span>非常推荐</span>
            </div>

            {/* Feedback */}
            <Textarea
              value={feedback}
              onChange={e => setFeedback(e.target.value)}
              placeholder="有什么建议想告诉我们？（可选）"
              className="min-h-[72px] text-sm rounded-xl border-black/[0.08] resize-none"
            />

            {/* Submit */}
            <Button
              onClick={handleSubmit}
              disabled={score === null || submitting}
              className="w-full rounded-xl h-10 text-sm font-medium"
            >
              {submitting ? '提交中...' : '提交反馈'}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
};
