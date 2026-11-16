import type { KnowledgeTreeBuildDetail } from '../types/knowledgeBuilder.ts';

export function knowledgeBuildPlanningPrompt(tree: KnowledgeTreeBuildDetail, selectedIds: ReadonlySet<number>): string {
  const targets = tree.blocks.filter(b => selectedIds.has(b.id));
  const included = new Set(targets.map(b => b.id));
  const retained = tree.block_edges.filter(e => e.is_retained);
  let changed = true;
  while (changed) {
    changed = false;
    for (const edge of retained) {
      if (included.has(edge.to_block) && !included.has(edge.from_block)) { included.add(edge.from_block); changed = true; }
      if (edge.edge_kind === 'bidirectional' && included.has(edge.from_block) && !included.has(edge.to_block)) { included.add(edge.to_block); changed = true; }
    }
  }
  const blocks = new Map(tree.blocks.map(b => [b.id, `${b.code} ${b.short_title}`]));
  const entries = tree.blocks.filter(b => b.is_entry_block).map(b => blocks.get(b.id));
  const relations = retained.filter(e => included.has(e.from_block) && included.has(e.to_block))
    .map(e => `${blocks.get(e.from_block)} ${e.edge_kind === 'bidirectional' ? '↔' : '→'} ${blocks.get(e.to_block)}`);
  return [
    `请结合当前小宇学习项目，为知识树《${tree.subject}》规划阶段学习路径。`,
    `知识树 ID：${tree.id}。目标学习块：${targets.map(b => blocks.get(b.id)).join('、')}。`,
    `图谱推荐起点：${entries.join('、') || '请根据前置关系确定'}。`,
    `目标块及其前置关系：\n${relations.join('\n') || '这些目标块暂无跨块前置关系。'}`,
    tree.requirements && Object.keys(tree.requirements).length ? `本次构建需求：${JSON.stringify(tree.requirements)}` : '',
    '请保留所有客观前置知识，结合我已有的基础标记推荐起点，安排核心与拓展内容、阶段任务和检查方式。先给出可确认的计划。',
  ].filter(Boolean).join('\n');
}
