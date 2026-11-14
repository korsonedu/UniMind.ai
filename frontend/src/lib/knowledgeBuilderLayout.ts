import type {
  BlockEdge,
  BlockIntraLine,
  BlockNodeShape,
  KnowledgeTreeBuildDetail,
  LearningBlock,
  TreeAtomPoint,
  TreeModule,
} from '../types/knowledgeBuilder.ts';

export type EdgeFilterMode = 'retained' | 'all';

export interface DomainLegendItem {
  id: number;
  code: string;
  title: string;
  color: string;
}

export interface StepDependencyItem {
  key: string;
  sourceBlockId: number;
  sourceBlockCode: string;
  sourceBlockTitle: string;
  fromAtomName: string;
  toAtomName: string;
  role: string;
  explanation: string;
}

export interface AdaptedAtomItem {
  atom: TreeAtomPoint;
  membership: 'core' | 'extension';
  isInterfacePoint: boolean;
  tooltip: string;
}

export interface AdaptedStep {
  id: number;
  stepIndex: number;
  title: string;
  role: string;
  branchCondition: string;
  atoms: AdaptedAtomItem[];
  dependencies: StepDependencyItem[];
  intraLines: BlockIntraLine[];
}

export interface AdaptedBlock {
  id: number;
  code: string;
  shortTitle: string;
  narrativeSummary: string;
  layer: number;
  order: number;
  contractionGroup: string;
  isEntry: boolean;
  nodeShape: BlockNodeShape;
  shapeTags: string[];
  structureType: string;
  domainId: number | null;
  domainTitle: string;
  color: string;
  coreCount: number;
  extensionCount: number;
  totalAtoms: number;
  steps: AdaptedStep[];
}

export interface AdaptedEdge {
  id: number;
  from: number;
  to: number;
  fromCode: string;
  toCode: string;
  kind: 'unidirectional' | 'bidirectional';
  isRetained: boolean;
  exclusionReason: string;
  rationale: string;
  directnessScore: number;
}

export interface AdaptedKnowledgeTree {
  buildId: string;
  subject: string;
  archetype: string;
  blocks: AdaptedBlock[];
  blockById: Map<number, AdaptedBlock>;
  edges: AdaptedEdge[];
  domains: DomainLegendItem[];
  atomCount: number;
  retainedUniCount: number;
  retainedBiCount: number;
  retainedCount: number;
  totalEdgeCount: number;
  entryBlockId: number | null;
}

export interface BoxRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface ComputedOuterWire {
  edge: AdaptedEdge;
  d: string;
}

export interface ColumnLayoutResult {
  columns: {
    layer: number;
    blocks: AdaptedBlock[];
    colPadPx: number;
  }[];
  rowSlots: Map<number, number>;
}

// 431 sage-compatible domain palette (starts with the exact 431 v3 4-domain colors).
const DOMAIN_PALETTE = [
  '#5476a5',
  '#b88648',
  '#558b6e',
  '#8868a5',
  '#b2656b',
  '#3e878b',
  '#7c8b4e',
  '#9a6c8e',
  '#4d7d96',
];

const DEFAULT_BLOCK_COLOR = '#558b6e';

function resolveRootModuleMap(modules: TreeModule[]): {
  rootOfModuleId: Map<number, TreeModule>;
  rootColorById: Map<number, string>;
  orderedRoots: TreeModule[];
} {
  const byId = new Map(modules.map(m => [m.id, m]));
  const rootOfModuleId = new Map<number, TreeModule>();
  const findRoot = (mod: TreeModule): TreeModule => {
    const visited = new Set<number>([mod.id]);
    let curr = mod;
    while (curr.parent !== null) {
      const parent = byId.get(curr.parent);
      if (!parent || visited.has(parent.id)) break;
      visited.add(parent.id);
      curr = parent;
    }
    return curr;
  };
  for (const mod of modules) {
    rootOfModuleId.set(mod.id, findRoot(mod));
  }
  const orderedRoots = [...new Set(rootOfModuleId.values())].sort(
    (a, b) => a.order - b.order || a.code.localeCompare(b.code)
  );
  const rootColorById = new Map<number, string>();
  orderedRoots.forEach((root, idx) => {
    rootColorById.set(root.id, DOMAIN_PALETTE[idx % DOMAIN_PALETTE.length]);
  });
  return { rootOfModuleId, rootColorById, orderedRoots };
}

const INTERFACE_ROLE_LABELS: Record<string, string> = {
  prerequisite_handoff: '先修前置',
  contrast_bridge: '对比辨析',
  application_transfer: '应用迁移',
  diagnostic_escalation: '排障进阶',
  mechanism_input: '机制输入',
};

function formatInterfaceRole(role: string): string {
  const key = role.trim();
  return INTERFACE_ROLE_LABELS[key] ?? key;
}

function buildShapeTags(shape: BlockNodeShape, isEntry: boolean): string[] {
  const tags: string[] = [];
  if (isEntry || shape.entry) tags.push('入口');
  if (shape.overview) tags.push('总览');
  if (shape.merge) tags.push('多路汇合');
  if (shape.end) tags.push('终局应用');
  return tags;
}

function buildStructureType(steps: { step_role: string }[], shapeTags: string[]): string {
  const roles = [...new Set(steps.map(s => s.step_role.trim()).filter(Boolean))];
  if (roles.length >= 2) return `${roles[0]}＋${roles[1]}`;
  if (roles.length === 1) return roles[0];
  if (shapeTags.length > 0) return shapeTags.join(' · ');
  return '知识结构块';
}

function buildAtomTooltip(atom: TreeAtomPoint): string {
  const lines = [`目标：${atom.goal_statement}`];
  if (atom.goal_type || atom.cognitive_level || atom.granularity_minutes) {
    lines.push(`${atom.goal_type} · ${atom.cognitive_level} · 约 ${atom.granularity_minutes} 分钟`);
  }
  if (atom.common_misconceptions?.length) {
    lines.push(`易错点：${atom.common_misconceptions.join('；')}`);
  }
  return lines.join('\n');
}

export function adaptKnowledgeTree(tree: KnowledgeTreeBuildDetail): AdaptedKnowledgeTree {
  const { rootOfModuleId, rootColorById, orderedRoots } = resolveRootModuleMap(tree.modules);
  const atomById = new Map(tree.atoms.map(a => [a.id, a]));
  const rawBlockById = new Map(tree.blocks.map(b => [b.id, b]));
  const rawEdgeById = new Map(tree.block_edges.map(e => [e.id, e]));

  // Map every atom -> owning LearningBlock so cross-block interfaces resolve source block reliably.
  const blockByAtomId = new Map<number, LearningBlock>();
  for (const block of tree.blocks) {
    for (const step of block.steps) {
      for (const sa of step.step_atoms) {
        blockByAtomId.set(sa.atom, block);
      }
    }
  }

  const interfaceAtomIds = new Set<number>();
  // Map to_atom ID -> list of prerequisite handoffs targeting that atom inside its block.
  const incomingInterfacesByToAtom = new Map<number, StepDependencyItem[]>();
  const seenDepKeys = new Set<string>();

  for (const ifc of tree.interfaces) {
    interfaceAtomIds.add(ifc.from_atom);
    interfaceAtomIds.add(ifc.to_atom);
    const fromAtom = atomById.get(ifc.from_atom);
    const toAtom = atomById.get(ifc.to_atom);
    const sourceBlock = blockByAtomId.get(ifc.from_atom);
    const targetBlock = blockByAtomId.get(ifc.to_atom);
    const edge = rawEdgeById.get(ifc.block_edge);
    if (!fromAtom || !toAtom || !sourceBlock || !targetBlock) continue;
    if (sourceBlock.id === targetBlock.id) continue;
    // Skip reverse direction unless explicit edge aligns from sourceBlock -> targetBlock.
    if (edge && edge.from_block !== sourceBlock.id) continue;

    const depKey = `${sourceBlock.id}:${fromAtom.id}:${toAtom.id}`;
    if (seenDepKeys.has(depKey)) continue;
    seenDepKeys.add(depKey);

    const list = incomingInterfacesByToAtom.get(toAtom.id) ?? [];
    list.push({
      key: depKey,
      sourceBlockId: sourceBlock.id,
      sourceBlockCode: sourceBlock.code,
      sourceBlockTitle: sourceBlock.short_title,
      fromAtomName: fromAtom.name,
      toAtomName: toAtom.name,
      role: formatInterfaceRole(ifc.interface_role),
      explanation: ifc.bridge_explanation,
    });
    incomingInterfacesByToAtom.set(toAtom.id, list);
  }

  const usedRootIds = new Set<number>();
  const adaptedBlocks: AdaptedBlock[] = [...tree.blocks]
    .sort((a, b) => a.order - b.order || a.code.localeCompare(b.code))
    .map(block => {
      const domainCounts = new Map<number, number>();
      let coreCount = 0;
      let extensionCount = 0;

      const sortedSteps = [...block.steps].sort((a, b) => a.step_index - b.step_index);
      const adaptedSteps: AdaptedStep[] = sortedSteps.map(step => {
        const sortedAtoms = [...step.step_atoms].sort((a, b) => a.position - b.position);
        const stepDeps: StepDependencyItem[] = [];
        const stepDepDedupe = new Set<string>();

        const atomItems: AdaptedAtomItem[] = sortedAtoms
          .map(sa => {
            const atom = atomById.get(sa.atom);
            if (!atom) return null;
            if (sa.membership_type === 'extension') extensionCount++;
            else coreCount++;

            const root = rootOfModuleId.get(atom.module);
            if (root) {
              domainCounts.set(root.id, (domainCounts.get(root.id) ?? 0) + 1);
            }

            const atomDeps = incomingInterfacesByToAtom.get(atom.id) ?? [];
            for (const dep of atomDeps) {
              const stepDepKey = `${dep.sourceBlockId}:${dep.fromAtomName}`;
              if (!stepDepDedupe.has(stepDepKey)) {
                stepDepDedupe.add(stepDepKey);
                stepDeps.push(dep);
              }
            }

            return {
              atom,
              membership: sa.membership_type,
              isInterfacePoint: interfaceAtomIds.has(atom.id),
              tooltip: buildAtomTooltip(atom),
            };
          })
          .filter((item): item is AdaptedAtomItem => item !== null);

        return {
          id: step.id,
          stepIndex: step.step_index,
          title: step.step_title,
          role: step.step_role,
          branchCondition: step.branch_condition,
          atoms: atomItems,
          dependencies: stepDeps,
          intraLines: step.intra_lines ?? [],
        };
      });

      // Pick dominant root module for block color.
      let dominantRoot: TreeModule | null = null;
      let bestCount = -1;
      for (const root of orderedRoots) {
        const count = domainCounts.get(root.id) ?? 0;
        if (count > bestCount) {
          bestCount = count;
          dominantRoot = root;
        }
      }
      if (dominantRoot && bestCount > 0) {
        usedRootIds.add(dominantRoot.id);
      } else {
        dominantRoot = null;
      }

      const shapeTags = buildShapeTags(block.node_shape ?? {}, block.is_entry_block);
      return {
        id: block.id,
        code: block.code,
        shortTitle: block.short_title,
        narrativeSummary: block.narrative_summary,
        layer: block.layer,
        order: block.order,
        contractionGroup: block.contraction_group,
        isEntry: block.is_entry_block,
        nodeShape: block.node_shape ?? {},
        shapeTags,
        structureType: buildStructureType(sortedSteps, shapeTags),
        domainId: dominantRoot ? dominantRoot.id : null,
        domainTitle: dominantRoot ? dominantRoot.title : '通用模块',
        color: dominantRoot ? (rootColorById.get(dominantRoot.id) ?? DEFAULT_BLOCK_COLOR) : DEFAULT_BLOCK_COLOR,
        coreCount,
        extensionCount,
        totalAtoms: coreCount + extensionCount,
        steps: adaptedSteps,
      };
    });

  const blockById = new Map(adaptedBlocks.map(b => [b.id, b]));
  const adaptedEdges: AdaptedEdge[] = tree.block_edges
    .filter(e => blockById.has(e.from_block) && blockById.has(e.to_block))
    .map((e: BlockEdge) => ({
      id: e.id,
      from: e.from_block,
      to: e.to_block,
      fromCode: rawBlockById.get(e.from_block)?.code ?? String(e.from_block),
      toCode: rawBlockById.get(e.to_block)?.code ?? String(e.to_block),
      kind: e.edge_kind,
      isRetained: e.is_retained,
      exclusionReason: e.exclusion_reason,
      rationale: e.rationale,
      directnessScore: e.directness_score,
    }));

  const retainedEdges = adaptedEdges.filter(e => e.isRetained);
  const domains: DomainLegendItem[] = orderedRoots
    .filter(root => usedRootIds.has(root.id))
    .map(root => ({
      id: root.id,
      code: root.code,
      title: root.title,
      color: rootColorById.get(root.id) ?? DEFAULT_BLOCK_COLOR,
    }));

  const entryBlock =
    adaptedBlocks.find(b => b.isEntry) ?? adaptedBlocks[0] ?? null;

  return {
    buildId: tree.id,
    subject: tree.subject,
    archetype: tree.archetype,
    blocks: adaptedBlocks,
    blockById,
    edges: adaptedEdges,
    domains,
    atomCount: tree.atoms.length,
    retainedUniCount: retainedEdges.filter(e => e.kind !== 'bidirectional').length,
    retainedBiCount: retainedEdges.filter(e => e.kind === 'bidirectional').length,
    retainedCount: retainedEdges.length,
    totalEdgeCount: adaptedEdges.length,
    entryBlockId: entryBlock ? entryBlock.id : null,
  };
}

/**
 * 431 v3 / 6E 32-pass barycenter column layout reducing edge crossings
 * and adding natural vertical breathing room to sparse columns.
 */
export function computeColumnLayout(
  blocks: AdaptedBlock[],
  activeEdges: AdaptedEdge[],
  openIds: Set<number>
): ColumnLayoutResult {
  const layerMap = new Map<number, number>();
  const groups = new Map<number, AdaptedBlock[]>();

  for (const b of blocks) {
    layerMap.set(b.id, b.layer);
    const arr = groups.get(b.layer) ?? [];
    arr.push(b);
    groups.set(b.layer, arr);
  }

  const layerNums = [...groups.keys()].sort((a, b) => a - b);
  for (const l of layerNums) {
    groups.get(l)!.sort((a, b) => a.order - b.order || a.code.localeCompare(b.code));
  }

  if (layerNums.length === 0) {
    return { columns: [], rowSlots: new Map() };
  }

  const groupIds = new Map<number, number[]>();
  const rank = new Map<number, number>();
  for (const l of layerNums) {
    const ids = groups.get(l)!.map(b => b.id);
    groupIds.set(l, ids);
    ids.forEach((id, idx) => rank.set(id, idx));
  }

  const byId = new Map(blocks.map(b => [b.id, b]));

  const countCrossings = (orderRank: Map<number, number>): number => {
    let n = 0;
    for (let i = 0; i < activeEdges.length; i++) {
      const a = activeEdges[i];
      const laFrom = layerMap.get(a.from);
      const laTo = layerMap.get(a.to);
      if (laFrom === undefined || laTo === undefined || laFrom === laTo) continue;
      for (let j = i + 1; j < activeEdges.length; j++) {
        const b = activeEdges[j];
        const lbFrom = layerMap.get(b.from);
        const lbTo = layerMap.get(b.to);
        if (laFrom === lbFrom && laTo === lbTo) {
          const diffFrom = (orderRank.get(a.from) ?? 0) - (orderRank.get(b.from) ?? 0);
          const diffTo = (orderRank.get(a.to) ?? 0) - (orderRank.get(b.to) ?? 0);
          if (diffFrom * diffTo < 0) n++;
        }
      }
    }
    return n;
  };

  let bestGroups = new Map<number, number[]>(
    layerNums.map(l => [l, [...(groupIds.get(l) ?? [])]])
  );
  let bestCrossings = countCrossings(rank);

  for (let pass = 0; pass < 32; pass++) {
    const ls = pass % 2 ? [...layerNums].reverse() : [...layerNums];
    for (const l of ls) {
      const ids = groupIds.get(l) ?? [];
      ids.sort((idA, idB) => {
        const bary = (id: number): number => {
          const neighbors = activeEdges
            .filter(e => e.from === id || e.to === id)
            .map(e => (e.from === id ? e.to : e.from))
            .filter(nid => {
              const nl = layerMap.get(nid);
              return nl !== undefined && (pass % 2 ? nl > l : nl < l);
            });
          if (!neighbors.length) return rank.get(id) ?? 0;
          return neighbors.reduce((sum, nid) => sum + (rank.get(nid) ?? 0), 0) / neighbors.length;
        };
        const diff = bary(idA) - bary(idB);
        if (Math.abs(diff) > 1e-9) return diff;
        const ba = byId.get(idA)!;
        const bb = byId.get(idB)!;
        return ba.order - bb.order || ba.code.localeCompare(bb.code);
      });
      ids.forEach((id, idx) => rank.set(id, idx));
    }
    const c = countCrossings(rank);
    if (c < bestCrossings) {
      bestCrossings = c;
      bestGroups = new Map(layerNums.map(l => [l, [...(groupIds.get(l) ?? [])]]));
    }
  }

  const rowSlots = new Map<number, number>();
  const columns = layerNums.map(layer => {
    const orderedIds = bestGroups.get(layer) ?? [];
    const colBlocks = orderedIds.map(id => byId.get(id)!);
    colBlocks.forEach((b, idx) => {
      const slot = colBlocks.length === 1 ? 2 : Math.round((idx * 4) / (colBlocks.length - 1));
      rowSlots.set(b.id, slot);
    });
    const hasOpen = colBlocks.some(b => openIds.has(b.id));
    let colPadPx = 0;
    if (!hasOpen && colBlocks.length === 1) {
      colPadPx = (rowSlots.get(colBlocks[0].id) ?? 2) * 86;
    } else if (!hasOpen && colBlocks.length === 2) {
      colPadPx = 56;
    }
    return { layer, blocks: colBlocks, colPadPx };
  });

  return { columns, rowSlots };
}

export function roundedOrthoPath(pts: [number, number][], radius = 12): string {
  if (pts.length < 2) return '';
  let d = `M ${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`;
  for (let i = 1; i < pts.length - 1; i++) {
    const prev = pts[i - 1];
    const curr = pts[i];
    const next = pts[i + 1];
    const v1x = curr[0] - prev[0];
    const v1y = curr[1] - prev[1];
    const v2x = next[0] - curr[0];
    const v2y = next[1] - curr[1];
    const len1 = Math.hypot(v1x, v1y);
    const len2 = Math.hypot(v2x, v2y);
    if (len1 < 1 || len2 < 1) {
      d += ` L ${curr[0].toFixed(1)} ${curr[1].toFixed(1)}`;
      continue;
    }
    const r = Math.min(radius, len1 / 2, len2 / 2);
    const p1x = curr[0] - (v1x / len1) * r;
    const p1y = curr[1] - (v1y / len1) * r;
    const p2x = curr[0] + (v2x / len2) * r;
    const p2y = curr[1] + (v2y / len2) * r;
    d += ` L ${p1x.toFixed(1)} ${p1y.toFixed(1)} Q ${curr[0].toFixed(1)} ${curr[1].toFixed(1)} ${p2x.toFixed(1)} ${p2y.toFixed(1)}`;
  }
  const last = pts[pts.length - 1];
  d += ` L ${last[0].toFixed(1)} ${last[1].toFixed(1)}`;
  return d;
}

/**
 * 3-tier outer block-edge routing faithfully matching 431 v3:
 * 1) Same-column vertical connectors
 * 2) Adjacent-column direct cubic Bezier S-curves with vertically sorted ports
 * 3) Multi-column corridor orthogonal rounded paths avoiding every intermediate card
 */
export function computeOuterWireRoutes(params: {
  blockBoxes: Map<number, BoxRect>;
  headerBoxes: Map<number, BoxRect>;
  columnIndexByBlockId: Map<number, number>;
  activeEdges: AdaptedEdge[];
}): ComputedOuterWire[] {
  const { blockBoxes, headerBoxes, columnIndexByBlockId, activeEdges } = params;

  const outList = new Map<number, AdaptedEdge[]>();
  const inList = new Map<number, AdaptedEdge[]>();
  for (const id of blockBoxes.keys()) {
    outList.set(id, []);
    inList.set(id, []);
  }

  for (const edge of activeEdges) {
    const c1 = columnIndexByBlockId.get(edge.from);
    const c2 = columnIndexByBlockId.get(edge.to);
    if (c1 === undefined || c2 === undefined || c1 === c2) continue;
    outList.get(edge.from)?.push(edge);
    inList.get(edge.to)?.push(edge);
  }

  for (const list of outList.values()) {
    list.sort(
      (a, b) =>
        ((headerBoxes.get(a.to)?.y ?? 0) - (headerBoxes.get(b.to)?.y ?? 0)) ||
        a.id - b.id
    );
  }
  for (const list of inList.values()) {
    list.sort(
      (a, b) =>
        ((headerBoxes.get(a.from)?.y ?? 0) - (headerBoxes.get(b.from)?.y ?? 0)) ||
        a.id - b.id
    );
  }

  const getOutPort = (blockId: number, edge: AdaptedEdge): [number, number] => {
    const box = headerBoxes.get(blockId)!;
    const list = outList.get(blockId) ?? [];
    const idx = list.indexOf(edge);
    const count = list.length;
    const spanH = Math.min(48, Math.max(12, box.h - 24));
    const offset = count <= 1 ? 0 : (idx / (count - 1) - 0.5) * spanH;
    return [box.x + box.w, box.y + box.h / 2 + offset];
  };

  const getInPort = (blockId: number, edge: AdaptedEdge): [number, number] => {
    const box = headerBoxes.get(blockId)!;
    const list = inList.get(blockId) ?? [];
    const idx = list.indexOf(edge);
    const count = list.length;
    const spanH = Math.min(48, Math.max(12, box.h - 24));
    const offset = count <= 1 ? 0 : (idx / (count - 1) - 0.5) * spanH;
    return [box.x, box.y + box.h / 2 + offset];
  };

  const allCards = [...blockBoxes.values()];
  const maxBottom = allCards.length ? Math.max(...allCards.map(c => c.y + c.h)) : 400;
  const candidateLanes: number[] = [];
  for (let y = 104; y <= maxBottom + 56; y += 8) candidateLanes.push(y);
  // Top corridor sits strictly above the column "第 N 层" pill (which renders at y ~ 56..80).
  for (let y = 14; y <= 46; y += 7) candidateLanes.push(y);

  const usedLanes: { y: number; x1: number; x2: number }[] = [];

  const findCleanLane = (
    xMin: number,
    xMax: number,
    yPref: number,
    excludeFrom: number,
    excludeTo: number
  ): number => {
    const valid = candidateLanes.filter(y => {
      if (usedLanes.some(u => Math.abs(u.y - y) < 7 && !(xMax < u.x1 || xMin > u.x2))) {
        return false;
      }
      for (const [bid, c] of blockBoxes.entries()) {
        if (bid === excludeFrom || bid === excludeTo) continue;
        if (c.x + c.w > xMin + 4 && c.x < xMax - 4) {
          if (y >= c.y - 10 && y <= c.y + c.h + 10) return false;
        }
      }
      return true;
    });
    if (!valid.length) {
      const fallbackY = 14 + (usedLanes.length % 5) * 7;
      usedLanes.push({ y: fallbackY, x1: xMin, x2: xMax });
      return fallbackY;
    }
    valid.sort((a, b) => Math.abs(a - yPref) - Math.abs(b - yPref));
    const chosen = valid[0];
    usedLanes.push({ y: chosen, x1: xMin, x2: xMax });
    return chosen;
  };

  const results: ComputedOuterWire[] = [];
  let longIdx = 0;

  for (const edge of activeEdges) {
    const boxFrom = blockBoxes.get(edge.from);
    const boxTo = blockBoxes.get(edge.to);
    const headFrom = headerBoxes.get(edge.from);
    const headTo = headerBoxes.get(edge.to);
    const c1 = columnIndexByBlockId.get(edge.from);
    const c2 = columnIndexByBlockId.get(edge.to);
    if (!boxFrom || !boxTo || !headFrom || !headTo || c1 === undefined || c2 === undefined) {
      continue;
    }

    if (c1 === c2) {
      const topCard = boxFrom.y < boxTo.y ? boxFrom : boxTo;
      const botCard = boxFrom.y < boxTo.y ? boxTo : boxFrom;
      const xMid = topCard.x + Math.min(88, topCard.w / 2);
      const yStart = topCard.y + topCard.h + 2;
      const yEnd = botCard.y - 2;
      results.push({ edge, d: `M ${xMid.toFixed(1)} ${yStart.toFixed(1)} L ${xMid.toFixed(1)} ${yEnd.toFixed(1)}` });
      continue;
    }

    const [x1, y1] = getOutPort(edge.from, edge);
    const [x2, y2] = getInPort(edge.to, edge);
    const span = Math.abs(c2 - c1);

    if (span === 1 && c2 > c1 && x2 > x1) {
      const dx = (x2 - x1) * 0.48;
      const d = `M ${x1.toFixed(1)} ${y1.toFixed(1)} C ${(x1 + dx).toFixed(1)} ${y1.toFixed(1)}, ${(x2 - dx).toFixed(1)} ${y2.toFixed(1)}, ${x2.toFixed(1)} ${y2.toFixed(1)}`;
      results.push({ edge, d });
      continue;
    }

    const stubOffset = 18 + (longIdx % 5) * 6;
    longIdx++;
    const xOut = x1 + stubOffset;
    const xIn = x2 - stubOffset;
    const yPref = (y1 + y2) / 2;
    const laneY = findCleanLane(
      Math.min(xOut, xIn),
      Math.max(xOut, xIn),
      yPref,
      edge.from,
      edge.to
    );
    const d = roundedOrthoPath(
      [
        [x1, y1],
        [xOut, y1],
        [xOut, laneY],
        [xIn, laneY],
        [xIn, y2],
        [x2, y2],
      ],
      12
    );
    results.push({ edge, d });
  }

  return results;
}
