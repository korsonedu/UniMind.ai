export interface KPNode {
  id: number;
  name: string;
  description: string;
  parent: number | null;
  level: string;
  order?: number;
  questions_count?: number;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
}

export interface TreeNodeData extends KPNode {
  children: TreeNodeData[];
}

export const LEVEL_ORDER: Record<string, number> = { sub: 0, ch: 1, sec: 2, kp: 3 };

export const LEVEL_COLORS: Record<string, string> = {
  sub: 'text-indigo-700 bg-indigo-50 border-indigo-200',
  ch: 'text-blue-700 bg-blue-50 border-blue-200',
  sec: 'text-sky-700 bg-sky-50 border-sky-200',
  kp: 'text-emerald-700 bg-emerald-50 border-emerald-200',
};

export const sortNodes = (a: KPNode, b: KPNode) =>
  (LEVEL_ORDER[a.level] ?? 99) - (LEVEL_ORDER[b.level] ?? 99) || a.name.localeCompare(b.name);
