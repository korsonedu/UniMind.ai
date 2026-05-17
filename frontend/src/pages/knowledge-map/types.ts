export interface KPNode {
  id: number;
  name: string;
  description: string;
  parent: number | null;
  level?: string;
  order?: number;
  questions_count?: number;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
}
