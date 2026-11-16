import { t } from '@/i18n';
import type { Note, Notebook } from './notes';

/** Local learning samples, independent of server content and permissions. */
export function createDemoNotebooks(): Notebook[] {
  return [{ id: 1, name: t('离线学习体验'), parent: null, position: 0 }];
}
export function createDemoNotes(): Note[] {
  return [{
    id: 1, title: t('欢迎离线体验 UniMind'),
    content: t('这篇笔记可以编辑，修改保存在本机，与真实账号隔离。连接服务器后可使用完整学习服务。'),
    notebook: 1, tags: [], is_favorite: true, version: 1, deleted_at: null,
    updated_at: '2026-11-16T00:00:00Z', backlinks: [],
  }];
}
export function demoPractice() {
  return {
    question: t('有效复习更适合采用哪种方式？'),
    options: [t('间隔复习并主动回忆'), t('只在考试前连续阅读')],
    explanation: t('回答正确。间隔复习与主动回忆有助于巩固学习。'),
    retry: t('请再试一次：想一想如何检查自己是否真正记住。'),
  };
}
