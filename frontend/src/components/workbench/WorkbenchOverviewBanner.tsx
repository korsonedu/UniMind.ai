import { ArrowUpRight, Books, Plus, Sparkle, Spinner } from '@phosphor-icons/react';
import { t } from '@/i18n';
import { useWorkbenchOverview } from '@/lib/workbenchApi';
import { MarkdownContent } from '@/components/MarkdownContent';
import type { ProjectSourceSummary } from '@/types/workbench';

export function WorkbenchOverviewBanner({ projectId, totalCount, selected, canSend, onAdd, onSend }: {
  projectId: number;
  totalCount: number;
  selected: ProjectSourceSummary[];
  canSend: boolean;
  onAdd: () => void;
  onSend: (text: string) => void;
}) {
  const { overview, pending, error, regenerate } = useWorkbenchOverview(projectId, selected);

  if (!totalCount) return <section className="um-wb-overview um-wb-overview-empty">
    <div className="um-wb-overview-icon"><Books size={25} weight="duotone" /></div>
    <h2>{t('把学习资料放进同一个项目')}</h2>
    <p>{t('上传课件 PDF、PPT、课程视频，或通过浏览器插件导入 B站 / YouTube 网课，开始跨资料伴学问答。')}</p>
    <button className="um-agent-button um-agent-button-primary" type="button" onClick={onAdd}><Plus size={16} />{t('上传第一份资料')}</button>
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
