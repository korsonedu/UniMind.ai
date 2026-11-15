import { t, useLocale } from '@/i18n';
import { Link } from 'react-router-dom';
import { ProjectLearningContent } from '@/components/ProjectLearningPanel';

export default function ProjectKnowledge() {
  useLocale();
  return <div className="um-learning-page"><header className="um-learning-page-header"><Link to="/xiaoyu">{t('返回小宇')}</Link><h1>{t('知识关系')}</h1></header><ProjectLearningContent knowledgeOnly /></div>;
}
