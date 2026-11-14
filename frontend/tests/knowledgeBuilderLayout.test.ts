import test from 'node:test';
import assert from 'node:assert/strict';
import type { KnowledgeTreeBuildDetail } from '../src/types/knowledgeBuilder.ts';
import {
  adaptKnowledgeTree,
  computeColumnLayout,
  computeOuterWireRoutes,
  roundedOrthoPath,
  type BoxRect,
} from '../src/lib/knowledgeBuilderLayout.ts';

function makeSampleTree(): KnowledgeTreeBuildDetail {
  return {
    id: 'build-1',
    subject: '私募股权基金基础知识',
    status: 'COMPLETED',
    current_stage: 'done',
    archetype: 'institution_mechanism_theory',
    dispatch_profile: {},
    stats: {},
    error_message: '',
    created_at: '2026-11-15T00:00:00Z',
    updated_at: '2026-11-15T00:00:00Z',
    completed_at: '2026-11-15T00:01:00Z',
    modules: [
      { id: 1, parent: null, code: 'M1', title: '概念域', path: 'M1', depth: 1, order: 1 },
      { id: 2, parent: 1, code: 'M1.1', title: '基金界定', path: 'M1/M1.1', depth: 2, order: 1 },
      { id: 3, parent: null, code: 'M2', title: '运作域', path: 'M2', depth: 1, order: 2 },
      { id: 4, parent: null, code: 'M3', title: '未使用模块', path: 'M3', depth: 1, order: 3 },
    ],
    atoms: [
      {
        id: 101,
        module: 2,
        code: 'A1',
        name: '私募股权基金定义',
        goal_statement: '掌握PE基金核心特征',
        parent_path: 'M1/M1.1',
        goal_type: 'concept',
        granularity_minutes: 10,
        cognitive_level: 'understand',
        key_elements: ['非公开募集'],
        prerequisites_hint: [],
        common_misconceptions: ['混同公募'],
        branch_condition: '',
        order: 1,
      },
      {
        id: 102,
        module: 2,
        code: 'A2',
        name: '合格投资者门槛',
        goal_statement: '区分机构与个人门槛',
        parent_path: 'M1/M1.1',
        goal_type: 'rule',
        granularity_minutes: 8,
        cognitive_level: 'apply',
        key_elements: [],
        prerequisites_hint: [],
        common_misconceptions: [],
        branch_condition: '',
        order: 2,
      },
      {
        id: 103,
        module: 3,
        code: 'A3',
        name: '基金募集流程',
        goal_statement: '掌握备案前募集顺序',
        parent_path: 'M2',
        goal_type: 'process',
        granularity_minutes: 12,
        cognitive_level: 'apply',
        key_elements: [],
        prerequisites_hint: [],
        common_misconceptions: [],
        branch_condition: '',
        order: 3,
      },
    ],
    atom_edges: [],
    blocks: [
      {
        id: 10,
        code: 'B1',
        short_title: '私募股权基金如何界定？',
        narrative_summary: '从定义到门槛',
        layer: 1,
        contraction_group: 'G1',
        is_entry_block: true,
        node_shape: { entry: true },
        order: 1,
        steps: [
          {
            id: 1001,
            step_index: 2,
            step_title: '准入边界',
            step_role: '制度/规则',
            branch_condition: '',
            intra_lines: [],
            step_atoms: [{ atom: 102, membership_type: 'extension', position: 1 }],
          },
          {
            id: 1000,
            step_index: 1,
            step_title: '本质特征',
            step_role: '核心概念',
            branch_condition: '',
            intra_lines: [
              { from_atom_code: 'A1', to_atom_code: 'A2', kind: 'progression', reason: '界定后明确投资者边界' },
            ],
            step_atoms: [{ atom: 101, membership_type: 'core', position: 1 }],
          },
        ],
      },
      {
        id: 20,
        code: 'B2',
        short_title: '募集与设立如何合规开展？',
        narrative_summary: '依门槛开展特定对象募集',
        layer: 2,
        contraction_group: 'G2',
        is_entry_block: false,
        node_shape: {},
        order: 2,
        steps: [
          {
            id: 2000,
            step_index: 1,
            step_title: '特定对象确定',
            step_role: '流程机制',
            branch_condition: '仅面向合格投资者',
            intra_lines: [],
            step_atoms: [{ atom: 103, membership_type: 'core', position: 1 }],
          },
        ],
      },
    ],
    block_edges: [
      {
        id: 500,
        from_block: 10,
        to_block: 20,
        edge_kind: 'unidirectional',
        directness_score: 0.9,
        hard_constraint_count: 1,
        hard_net: 1,
        similarity: 0.5,
        is_retained: true,
        exclusion_reason: '',
        rationale: '定义与合格投资者门槛决定募集对象合法性',
      },
      {
        id: 501,
        from_block: 20,
        to_block: 10,
        edge_kind: 'bidirectional',
        directness_score: 0.4,
        hard_constraint_count: 0,
        hard_net: 0,
        similarity: 0.7,
        is_retained: false,
        exclusion_reason: '弱反馈候选边',
        rationale: '实务反哺界定',
      },
    ],
    interfaces: [
      {
        id: 900,
        block_edge: 500,
        from_atom: 102,
        to_atom: 103,
        interface_role: '准入前置',
        bridge_explanation: '只有识别合格投资者，才能合法完成特定对象确定与推介',
      },
    ],
  };
}

test('adaptKnowledgeTree resolves root domains, sorted steps, interface jumps, and counts', () => {
  const adapted = adaptKnowledgeTree(makeSampleTree());

  assert.equal(adapted.entryBlockId, 10);
  assert.equal(adapted.retainedCount, 1);
  assert.equal(adapted.retainedUniCount, 1);
  assert.equal(adapted.retainedBiCount, 0);
  assert.equal(adapted.totalEdgeCount, 2);
  assert.equal(adapted.atomCount, 3);

  // Unused root module M3 must not pollute domain legend.
  assert.deepEqual(
    adapted.domains.map(d => d.code),
    ['M1', 'M2']
  );

  const b1 = adapted.blockById.get(10)!;
  assert.equal(b1.domainTitle, '概念域');
  assert.equal(b1.color, '#5476a5');
  assert.equal(b1.coreCount, 1);
  assert.equal(b1.extensionCount, 1);
  assert.deepEqual(
    b1.steps.map(s => s.stepIndex),
    [1, 2]
  );
  assert.equal(b1.steps[1].atoms[0].isInterfacePoint, true);

  const b2 = adapted.blockById.get(20)!;
  assert.equal(b2.steps[0].dependencies.length, 1);
  assert.equal(b2.steps[0].dependencies[0].sourceBlockId, 10);
  assert.equal(b2.steps[0].dependencies[0].fromAtomName, '合格投资者门槛');
});

test('computeColumnLayout reduces edge crossings via barycenter and clears pad when block is open', () => {
  const tree = makeSampleTree();
  // Create 2 blocks on layer 1 (B1, B1b) and 2 blocks on layer 2 (B2, B2b) intentionally crossed.
  const b1Top = { ...tree.blocks[0], id: 1, code: 'B1', layer: 1, order: 1 };
  const b1Bot = { ...tree.blocks[0], id: 2, code: 'B1b', layer: 1, order: 2 };
  const b2Top = { ...tree.blocks[1], id: 3, code: 'B2', layer: 2, order: 1 };
  const b2Bot = { ...tree.blocks[1], id: 4, code: 'B2b', layer: 2, order: 2 };
  const adapted = adaptKnowledgeTree({
    ...tree,
    blocks: [b1Top, b1Bot, b2Top, b2Bot],
    block_edges: [
      { ...tree.block_edges[0], id: 1, from_block: 1, to_block: 4, is_retained: true },
      { ...tree.block_edges[0], id: 2, from_block: 2, to_block: 3, is_retained: true },
    ],
    interfaces: [],
  });

  const retained = adapted.edges.filter(e => e.isRetained);
  const collapsed = computeColumnLayout(adapted.blocks, retained, new Set());
  assert.equal(collapsed.columns.length, 2);
  // Layer 2 order should flip to match [4, 3] (or layer 1 flips to [2, 1]) so edges do not cross.
  const l1Order = collapsed.columns[0].blocks.map(b => b.id);
  const l2Order = collapsed.columns[1].blocks.map(b => b.id);
  const idx1 = l1Order.indexOf(1);
  const idx2 = l1Order.indexOf(2);
  const idx4 = l2Order.indexOf(4);
  const idx3 = l2Order.indexOf(3);
  assert.ok((idx1 - idx2) * (idx4 - idx3) > 0, 'expected crossing edges to uncross');
  assert.equal(collapsed.columns[0].colPadPx, 56);

  const opened = computeColumnLayout(adapted.blocks, retained, new Set([1]));
  assert.equal(opened.columns[0].colPadPx, 0);
});

test('computeOuterWireRoutes emits same-column, adjacent Bezier, and corridor-avoiding orthogonal paths', () => {
  const tree = makeSampleTree();
  const adapted = adaptKnowledgeTree(tree);
  const eSameCol = { ...adapted.edges[0], id: 1, from: 10, to: 11 };
  const eAdj = { ...adapted.edges[0], id: 2, from: 10, to: 20 };
  const eLong = { ...adapted.edges[0], id: 3, from: 10, to: 30 };

  const blockBoxes = new Map<number, BoxRect>([
    [10, { x: 40, y: 120, w: 188, h: 120 }],
    [11, { x: 40, y: 310, w: 188, h: 120 }],
    [20, { x: 346, y: 140, w: 188, h: 160 }],
    [30, { x: 652, y: 130, w: 188, h: 120 }],
  ]);
  const headerBoxes = new Map<number, BoxRect>(blockBoxes);
  const colMap = new Map<number, number>([
    [10, 0],
    [11, 0],
    [20, 1],
    [30, 2],
  ]);

  const wires = computeOuterWireRoutes({
    blockBoxes,
    headerBoxes,
    columnIndexByBlockId: colMap,
    activeEdges: [eSameCol, eAdj, eLong],
  });

  assert.equal(wires.length, 3);
  assert.match(wires[0].d, /^M .* L /);
  assert.match(wires[1].d, / C /);
  assert.match(wires[2].d, / Q /);
  assert.equal(roundedOrthoPath([[0, 0], [50, 0], [50, 50]], 10).includes('Q 50.0 0.0'), true);
});
