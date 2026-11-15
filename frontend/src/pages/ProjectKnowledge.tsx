import { t, useLocale } from '@/i18n';
import { Navigate, useLocation } from 'react-router-dom';

export default function ProjectKnowledge() {
  useLocale();
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  params.set('learning_view', 'knowledge');
  return <Navigate to={`/xiaoyu?${params}`} replace />;
}
