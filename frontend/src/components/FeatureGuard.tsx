import { useInstitutionStore } from '@/store/useInstitutionStore';
import { Spinner, Lock } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';

const FEATURE_LABELS: Record<string, string> = {
  'ai.assistant': '小宇',
  'full.report': '学习记录',
  'quiz.exam': '智能刷题',
  'knowledge.graph': '知识地图',
  'faq.system': '答疑系统',
  'study.room': '在线自习室',
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
  const { hasFeature, loading, featuresError, fetchFeatures } = useInstitutionStore();

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (featuresError) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center p-4">
        <div className="text-center max-w-md">
          <p className="text-muted-foreground text-sm mb-4">加载功能配置失败</p>
          <Button variant="outline" onClick={() => fetchFeatures()}>重试</Button>
        </div>
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
          <Lock className="w-6 h-6 text-muted-foreground mx-auto mb-4" />
          <h2 className="text-xl font-bold mb-2">{featureName}暂未开放</h2>
          <p className="text-muted-foreground text-sm mb-6">
            该功能尚未向你的账号开放，请联系管理员。
          </p>
        </div>
      </div>
    </>
  );
}
