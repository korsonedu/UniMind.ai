// 知识图边类型定义

export type EdgeType = 'contains' | 'prerequisite' | 'similar' | 'contrast' | 'confusion' | 'co_occur' | 'derivation';
export type EdgeSource = 'tree' | 'llm' | 'manual' | 'data';

export interface KPNode {
  id: number;
  name: string;
  code: string;
  level: string;
  parent: number | null;
  parent_name?: string;
  subject: string;
  order?: number;
  x?: number;
  y?: number;
}

export interface KEdge {
  id: number;
  source: number;
  source_name: string;
  source_code: string;
  target: number;
  target_name: string;
  target_code: string;
  edge_type: EdgeType;
  weight: number;
  source_type: EdgeSource;
  is_active: boolean;
  institution: number | null;
  created_at: string;
}

// 边类型 → 颜色
export const EDGE_COLORS: Record<EdgeType, string> = {
  contains:     '#6B7280',  // gray-500
  similar:      '#10B981',  // emerald-500
  prerequisite: '#F59E0B',  // amber-500
  derivation:   '#8B5CF6',  // violet-500
  contrast:     '#EF4444',  // red-500
  confusion:    '#EC4899',  // pink-500
  co_occur:     '#06B6D4',  // cyan-500
};

// 边类型 → 中文标签
export const EDGE_LABELS: Record<EdgeType, string> = {
  contains:     '包含',
  similar:      '相似',
  prerequisite: '前驱',
  derivation:   '推导',
  contrast:     '对立',
  confusion:    '混淆',
  co_occur:     '共现',
};

// 边类型 → 默认权重
export const EDGE_DEFAULTS: Record<EdgeType, number> = {
  contains:     0.8,
  prerequisite: 0.7,
  derivation:   0.6,
  similar:      0.3,
  contrast:     0.3,
  confusion:    0.5,
  co_occur:     0.2,
};

// 非对称边：创建时需要生成低权重反向边
export const ASYMMETRIC_TYPES: EdgeType[] = ['prerequisite', 'derivation'];

// 来源 → 中文
export const SOURCE_LABELS: Record<EdgeSource, string> = {
  tree:   '系统',
  llm:    'AI建议',
  manual: '手动',
  data:   '数据',
};

// SEC 分组色盘（循环使用）
export const SEC_COLORS = [
  '#E0E7FF', '#CCFBF1', '#FEF3C7', '#FCE7F3',
  '#E0F2FE', '#F3E8FF', '#FFE4E6', '#D1FAE5',
];
