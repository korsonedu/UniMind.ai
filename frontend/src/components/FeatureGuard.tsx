import { Navigate } from 'react-router-dom';
import { useInstitutionStore } from '@/store/useInstitutionStore';
import { Loader2 } from 'lucide-react';

export function FeatureGuard({
  feature,
  children,
}: {
  feature: string;
  children: React.ReactNode;
}) {
  const { hasFeature, loading } = useInstitutionStore();

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

  return <Navigate to="/" replace />;
}
