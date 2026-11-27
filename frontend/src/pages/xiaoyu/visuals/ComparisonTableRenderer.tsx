import React from 'react';
import { MarkdownContent } from '@/components/MarkdownContent';

export interface ComparisonTableRow {
  dimension: string;
  cells: string[];
  pitfall?: string;
}

export interface ComparisonTablePayload {
  title: string;
  subtitle?: string;
  columns: string[];
  rows: ComparisonTableRow[];
}

export const ComparisonTableRenderer: React.FC<{ payload: ComparisonTablePayload }> = ({ payload }) => {
  const columns = Array.isArray(payload?.columns) ? payload.columns : [];
  const rows = Array.isArray(payload?.rows) ? payload.rows : [];
  if (!columns.length || !rows.length) return null;
  const hasPitfall = rows.some(row => Boolean(row.pitfall?.trim()));

  return (
    <div className="um-comparison-table">
      <div className="um-visual-heading">
        {payload.title && <h3>{payload.title}</h3>}
        {payload.subtitle && <p>{payload.subtitle}</p>}
      </div>
      <div className="um-comparison-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">对比维度</th>
              {columns.map((col, index) => (
                <th key={index} scope="col">{col}</th>
              ))}
              {hasPitfall && <th scope="col">⚠️ 易混防坑</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                <th scope="row">{row.dimension}</th>
                {columns.map((_, colIndex) => (
                  <td key={colIndex}>
                    <MarkdownContent
                      content={row.cells?.[colIndex] ?? '—'}
                      className="prose prose-sm max-w-none dark:prose-invert"
                    />
                  </td>
                ))}
                {hasPitfall && (
                  <td className="um-comparison-pitfall">
                    {row.pitfall ? <span className="um-comparison-pitfall-chip">{row.pitfall}</span> : '—'}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
