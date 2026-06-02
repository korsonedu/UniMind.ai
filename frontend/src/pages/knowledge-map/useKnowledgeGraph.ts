import type { KPNode } from './types';
import { sortNodes } from './types';

export const buildStableLayout = (nodes: KPNode[]) => {
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const childrenMap = new Map<number, KPNode[]>();
  const roots: KPNode[] = [];

  for (const node of nodes) {
    if (node.parent && nodeMap.has(node.parent)) {
      const bucket = childrenMap.get(node.parent) || [];
      bucket.push(node);
      childrenMap.set(node.parent, bucket);
    } else {
      roots.push(node);
    }
  }

  for (const children of childrenMap.values()) children.sort(sortNodes);
  roots.sort(sortNodes);

  const rootCount = Math.max(roots.length, 1);
  const sectorWidth = (Math.PI * 2) / rootCount;
  const rootRadius = rootCount > 1 ? 260 : 0;
  const depthSpacing = 140;
  const positions = new Map<number, { x: number; y: number }>();

  const collectDescendants = (nodeId: number, acc: KPNode[]) => {
    const children = childrenMap.get(nodeId) || [];
    for (const child of children) {
      acc.push(child);
      collectDescendants(child.id, acc);
    }
  };

  const getDepthFromRoot = (node: KPNode, rootId: number) => {
    let depth = 0;
    let current: KPNode | undefined = node;
    while (current && current.id !== rootId) {
      depth += 1;
      current = current.parent ? nodeMap.get(current.parent) : undefined;
      if (!current) break;
    }
    return depth;
  };

  roots.forEach((root, idx) => {
    const sectorStart = -Math.PI / 2 + idx * sectorWidth;
    const sectorEnd = sectorStart + sectorWidth;
    const sectorCenter = (sectorStart + sectorEnd) / 2;

    positions.set(root.id, {
      x: Math.cos(sectorCenter) * rootRadius,
      y: Math.sin(sectorCenter) * rootRadius,
    });

    const descendants: KPNode[] = [];
    collectDescendants(root.id, descendants);
    if (!descendants.length) return;

    descendants.forEach((node, order) => {
      const t = (order + 1) / (descendants.length + 1);
      const angle = sectorStart + t * (sectorEnd - sectorStart);
      const depth = getDepthFromRoot(node, root.id);
      const radius = rootRadius + depth * depthSpacing;
      positions.set(node.id, {
        x: Math.cos(angle) * radius,
        y: Math.sin(angle) * radius,
      });
    });
  });

  return positions;
};
