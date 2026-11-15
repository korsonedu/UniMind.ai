import { Link, useLocation } from 'react-router-dom';
import { ProjectLearningContent } from '@/components/ProjectLearningPanel';

export default function ProjectKnowledge() {
  const location = useLocation();
  return <div className="um-learning-page"><header className="um-learning-page-header"><Link to="/xiaoyu">返回小宇</Link><h1>知识关系</h1><Link to={{ pathname: "/knowledge-builder", search: location.search }}>知识结构图谱构建器</Link></header><ProjectLearningContent knowledgeOnly /></div>;
}
