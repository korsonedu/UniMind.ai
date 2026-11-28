import { ArrowUpRight, Books, Sparkle, Spinner } from '@phosphor-icons/react';
import { t } from '@/i18n';
import { useWorkbenchOverview } from '@/lib/workbenchApi';
import { MarkdownContent } from '@/components/MarkdownContent';
import type { ProjectSourceSummary } from '@/types/workbench';

export function WorkbenchOverviewBanner({ projectId, totalCount, selected, canSend, onSend }: {
  projectId: number;
  totalCount: number;
  selected: ProjectSourceSummary[];
  canSend: boolean;
  onSend: (text: string) => void;
}) {
  const { overview, pending, error, regenerate } = useWorkbenchOverview(projectId, selected);

  if (!totalCount) return <section className="um-wb-overview um-wb-overview-empty">
    <div className="um-wb-overview-icon"><Books size={25} weight="duotone" /></div>
    <h2>{t('把学习资料放进同一个项目')}</h2>
    <p>{t('在右侧栏的「资料源」中添加课件、视频和笔记。')}</p>
  </section>;

  if (!selected.length) return <section className="um-wb-overview um-wb-overview-empty">
    <div className="um-wb-overview-icon"><Books size={25} weight="duotone" /></div>
    <h2>{t('从项目资料开始提问')}</h2>
    <p>{t('勾选解析完成的资料后，小宇会结合原文回答，并标出引用位置。')}</p>
  </section>;

  return <section className="um-wb-overview">
    <header><Sparkle weight="duotone" size={20} /><h2>{t('资料全景导读')}</h2></header>
    {overview?.overview && <MarkdownContent className="um-wb-overview-text" content={overview.overview} />}
    {pending && <p className="um-wb-muted" role="status"><Spinner size={14} className="um-wb-spin" />{t('正在整理资料导读…')}</p>}
    {error && <button className="um-agent-button" onClick={() => void regenerate()}>{t('导读生成失败，重试')}</button>}
    {!!overview?.suggested_questions.length && <>
      <h3>{t('推荐问题')}</h3>
      <div className="um-wb-questions">{overview.suggested_questions.map((question, index) =>
        <button key={index} className="um-wb-question" type="button" disabled={!canSend} onClick={() => onSend(question)}>
          <span>{question}</span><ArrowUpRight size={15} />
        </button>
      )}</div>
    </>}
  </section>;
}
