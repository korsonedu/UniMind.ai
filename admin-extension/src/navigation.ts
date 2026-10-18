import { BookOpen, Users, Layers, History, ListChecks, FolderTree, MessagesSquare, Workflow, Settings, Receipt, Package } from 'lucide-vue-next';

export const sections = [
  { id: 'workbench', name: '教学工作台', group: '教学', icon: MessagesSquare },
  { id: 'questions', name: '题库', group: '教学', icon: ListChecks },
  { id: 'knowledge', name: '知识目录', group: '教学', icon: FolderTree },
  { id: 'tasks', name: '内容任务', group: '教学', icon: Workflow },
  { id: 'courses', name: '课程', group: '课程', icon: BookOpen },
  { id: 'modules', name: '模块', group: '课程', icon: Layers },
  { id: 'people', name: '学员', group: '学员与服务', icon: Users },
  { id: 'products', name: 'AI 加量', group: '学员与服务', icon: Package },
  { id: 'orders', name: '订单', group: '学员与服务', icon: Receipt },
  { id: 'settings', name: 'AI 配置', group: '系统', icon: Settings },
  { id: 'audit', name: '操作记录', group: '系统', icon: History },
] as const;

export function currentSection(value?: string) {
  return sections.find(section => section.id === value)?.id || 'workbench';
}
