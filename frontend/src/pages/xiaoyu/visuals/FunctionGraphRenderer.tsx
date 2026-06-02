import React, { useMemo } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceDot, ReferenceLine, Label,
} from 'recharts';

interface FunctionPoint {
  x: number;
  y: number;
  label?: string;
}

interface Expression {
  label?: string;
  color?: string;
  points?: Array<{ x: number; y: number }>;
}

interface FunctionGraphPayload {
  title?: string;
  expressions?: Expression[];
  points?: FunctionPoint[];
  xRange?: [number, number];
  yRange?: [number, number];
  xLabel?: string;
  yLabel?: string;
  formula?: string;
}

function sampleFormula(formula: string, xMin: number, xMax: number, steps = 200) {
  const data: Array<{ x: number; y: number }> = [];
  const safe = formula
    .replace(/\^/g, '**')
    .replace(/sin/g, 'Math.sin')
    .replace(/cos/g, 'Math.cos')
    .replace(/tan/g, 'Math.tan')
    .replace(/sqrt/g, 'Math.sqrt')
    .replace(/abs/g, 'Math.abs')
    .replace(/log/g, 'Math.log')
    .replace(/exp/g, 'Math.exp')
    .replace(/pi/gi, 'Math.PI')
    .replace(/(?<![a-zA-Z.])x(?![a-zA-Z0-9_])/g, '(__x__)');

  for (let i = 0; i <= steps; i++) {
    const x = xMin + (xMax - xMin) * (i / steps);
    try {
      // eslint-disable-next-line no-new-func
      const y = new Function('__x__', `return ${safe.replace(/__x__/g, String(x))}`)();
      if (Number.isFinite(y)) data.push({ x: Math.round(x * 1000) / 1000, y: Math.round(y * 10000) / 10000 });
    } catch {
      // skip
    }
  }
  return data;
}

// Muted, distinguishable palette
const COLORS = ['#525252', '#9f1239', '#1e6b45', '#7c3aed'];

const CustomTooltip = ({ active, payload }: { active?: boolean; payload?: Array<{ payload: { x: number; y: number } }> }) => {
  if (!active || !payload?.length) return null;
  const { x, y } = payload[0].payload;
  return (
    <div className="bg-background border border-border px-2 py-1 text-[11px] shadow-sm">
      <span className="text-foreground/40">x </span><span className="font-medium">{x}</span>
      <span className="text-foreground/40 ml-2">y </span><span className="font-medium">{y}</span>
    </div>
  );
};

export const FunctionGraphRenderer: React.FC<{ payload: FunctionGraphPayload }> = ({ payload }) => {
  const xMin = payload.xRange?.[0] ?? -5;
  const xMax = payload.xRange?.[1] ?? 5;

  const allData = useMemo(() => {
    return (payload.expressions || []).map(expr => expr.points || []);
  }, [payload.expressions]);

  const quickData = useMemo(() => {
    if (!payload.formula) return null;
    return sampleFormula(payload.formula, xMin, xMax);
  }, [payload.formula, xMin, xMax]);

  const points = payload.points || [];

  const mergedData = useMemo(() => {
    if (quickData) return quickData;
    const xMap = new Map<number, Record<string, number>>();
    allData.forEach((pts, i) => {
      pts.forEach((p: { x: number; y: number }) => {
        if (!xMap.has(p.x)) xMap.set(p.x, { x: p.x });
        xMap.get(p.x)![`expr_${i}`] = p.y;
      });
    });
    return Array.from(xMap.values()).sort((a, b) => a.x - b.x);
  }, [allData, quickData]);

  return (
    <div className="p-5 space-y-3">
      {payload.title && (
        <h3 className="text-[15px] font-semibold tracking-tight text-foreground">{payload.title}</h3>
      )}

      {mergedData.length > 0 ? (
        <div className="w-full" style={{ height: 300 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={mergedData} margin={{ top: 16, right: 20, bottom: 20, left: 20 }}>
              <CartesianGrid strokeDasharray="2 4" stroke="#e4e4e7" />
              <XAxis
                dataKey="x"
                type="number"
                domain={[xMin, xMax]}
                tick={{ fontSize: 10, fill: '#a1a1aa' }}
                axisLine={{ stroke: '#d4d4d8' }}
                tickLine={false}
              >
                {payload.xLabel && <Label value={payload.xLabel} position="bottom" offset={6} style={{ fontSize: 10, fill: '#a1a1aa' }} />}
              </XAxis>
              <YAxis
                domain={payload.yRange ? [payload.yRange[0], payload.yRange[1]] : ['auto', 'auto']}
                tick={{ fontSize: 10, fill: '#a1a1aa' }}
                axisLine={{ stroke: '#d4d4d8' }}
                tickLine={false}
              >
                {payload.yLabel && <Label value={payload.yLabel} position="insideLeft" angle={-90} offset={6} style={{ fontSize: 10, fill: '#a1a1aa' }} />}
              </YAxis>
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine y={0} stroke="#d4d4d8" strokeWidth={1} />
              <ReferenceLine x={0} stroke="#d4d4d8" strokeWidth={1} />

              {quickData ? (
                <Line
                  type="monotone" dataKey="y"
                  stroke={COLORS[0]} strokeWidth={1.5} dot={false}
                />
              ) : (
                allData.map((_, i) => (
                  <Line
                    key={i} type="monotone" dataKey={`expr_${i}`}
                    stroke={payload.expressions?.[i]?.color || COLORS[i % COLORS.length]}
                    strokeWidth={1.5} dot={false}
                    name={payload.expressions?.[i]?.label || `f${i + 1}(x)`}
                  />
                ))
              )}

              {points.map((pt, i) => (
                <ReferenceDot
                  key={i} x={pt.x} y={pt.y}
                  r={4} fill="#ef4444" stroke="#fff" strokeWidth={1.5}
                >
                  {pt.label && (
                    <Label
                      value={pt.label} position="top" offset={8}
                      style={{ fontSize: 10, fontWeight: 500, fill: '#525252' }}
                    />
                  )}
                </ReferenceDot>
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="flex items-center justify-center h-48 text-[12px] text-foreground/25">
          暂无函数数据
        </div>
      )}

      {allData.length > 1 && payload.expressions && (
        <div className="flex flex-wrap gap-4">
          {payload.expressions.map((expr, i) => (
            <div key={i} className="flex items-center gap-1.5 text-[11px] text-foreground/40">
              <span className="w-3 border-t" style={{ borderColor: expr.color || COLORS[i % COLORS.length] }} />
              {expr.label || `f${i + 1}(x)`}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
