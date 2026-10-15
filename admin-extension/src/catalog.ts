import type { KnowledgeNode } from './types';

export const levels = [{ value: 'sub', label: '科目' }, { value: 'ch', label: '篇章' }, { value: 'sec', label: '小节' }, { value: 'kp', label: '考点' }];
export const difficulties = [{ value: 'entry', label: '入门' }, { value: 'easy', label: '简单' }, { value: 'normal', label: '适当' }, { value: 'hard', label: '困难' }, { value: 'extreme', label: '极限' }];
export const subjectiveTypes = [{ value: 'noun', label: '名词解释' }, { value: 'short', label: '简答题' }, { value: 'essay', label: '论述题' }, { value: 'calculate', label: '计算题' }];

export function catalogOptions(nodes: KnowledgeNode[]) {
  const byId = new Map(nodes.map(node => [node.id, node]));
  const children = new Map<number | null, KnowledgeNode[]>();
  for (const node of nodes) {
    const parent = node.parent !== null && byId.has(node.parent) ? node.parent : null;
    children.set(parent, [...(children.get(parent) || []), node]);
  }
  const result: (KnowledgeNode & { depth: number; label: string; ancestors: number[] })[] = [];
  const seen = new Set<number>();
  const walk = (roots: KnowledgeNode[]) => {
    const queue = roots.slice().reverse().map(node => ({ node, ancestors: [] as number[], names: [] as string[] }));
    while (queue.length) {
      const { node, ancestors, names } = queue.pop()!;
      if (seen.has(node.id)) continue;
      seen.add(node.id);
      const path = [...names, node.name];
      result.push({ ...node, depth: ancestors.length, ancestors, label: `${node.subject ? node.subject + ' / ' : ''}${path.join(' / ')}${node.code ? ` [${node.code}]` : ''}` });
      for (const child of (children.get(node.id) || []).slice().reverse()) {
        queue.push({ node: child, ancestors: [...ancestors, node.id], names: path });
      }
    }
  };
  walk(children.get(null) || []);
  walk(nodes.filter(node => !seen.has(node.id)));
  return result;
}
