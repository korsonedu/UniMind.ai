import { useState } from 'react';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import { useAuthStore } from '@/store/useAuthStore';
import { Loader2, Lock, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { UpgradeModal } from '@/components/UpgradeModal';

const FEATURE_LABELS: Record<string, string> = {
  'ai.assistant': 'AI 助教',
  'quiz.exam': '智能刷题',
  'knowledge.graph': '知识地图',
  'faq.system': '答疑系统',
  'study.room': '在线自习室',
  'pdf.mock': '模拟考试',
  'interview.mock': 'AI 模拟面试',
  'course.video': '视频课程',
  'wrong.review': '错题回顾',
};

export function FeatureGuard({
  feature,
  children,
}: {
  feature: string;
  children: React.ReactNode;
}) {
  const { hasFeature, loading } = useInstitutionStore();
  const user = useAuthStore(s => s.user);
  const [showUpgrade, setShowUpgrade] = useState(false);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (hasFeature(feature)) {
    return <>{children}</>;
  }

  const featureName = FEATURE_LABELS[feature] || feature;

  return (
    <>
      <div className="min-h-[60vh] flex items-center justify-center p-4">
        <div className="text-center max-w-md">
          <div className="w-16 h-16 rounded-2xl bg-muted flex items-center justify-center mx-auto mb-5">
            <Lock className="w-8 h-8 text-muted-foreground" />
          </div>
          <h2 className="text-xl font-bold mb-2">{featureName}暂未开放</h2>
          <p className="text-muted-foreground text-sm mb-6">
            该功能需要升级方案后使用，请联系机构管理员开通。
          </p>
          <Button onClick={() => setShowUpgrade(true)} className="rounded-full px-6">
            <Sparkles className="w-4 h-4 mr-2" />
            升级方案
          </Button>
        </div>
      </div>
      <UpgradeModal
        open={showUpgrade}
        onOpenChange={setShowUpgrade}
        feature={feature}
        currentPlan={user?.membership_tier || 'free'}
      />
    </>
  );
}
