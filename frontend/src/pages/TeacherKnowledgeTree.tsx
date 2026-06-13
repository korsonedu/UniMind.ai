/**
 * 教师端知识树 — 从维护中心知识图谱 tab 迁出。
 */
import { KnowledgeSystemPanel } from './maintenance/KnowledgeSystemPanel';

export default function TeacherKnowledgeTree() {
  return (
    <div className="h-full p-4 md:p-6">
      <KnowledgeSystemPanel />
    </div>
  );
}
