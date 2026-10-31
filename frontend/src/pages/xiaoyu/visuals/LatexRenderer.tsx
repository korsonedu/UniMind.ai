import React from 'react';
import { MarkdownContent } from '@/components/MarkdownContent';

interface LatexDerivationPayload {
  title: string;
  steps: Array<{ latex: string; note?: string }>;
}

/**
 * Enhanced dedup: handles multiple failure modes from LLM output.
 * 1. $$A$$ $$A$$ → keep first
 * 2. "x=2x=2" → split by repeated substring
 * 3. Inline doubled content within a single formula
 */
function deduplicateLatex(raw: string): string {
  if (!raw) return raw;

  const parts = raw.split(/\$\$/).map(s => s.trim()).filter(Boolean);
  if (parts.length > 1) {
    const seen = new Set<string>();
    const unique: string[] = [];
    for (const part of parts) {
      const key = part.replace(/\s+/g, '').toLowerCase();
      if (!seen.has(key)) {
        seen.add(key);
        unique.push(part);
      }
    }
    return unique.join(' $$ ');
  }

  const stripped = raw.trim();
  const halfLen = Math.floor(stripped.length / 2);
  if (halfLen >= 2) {
    const firstHalf = stripped.slice(0, halfLen);
    const secondHalf = stripped.slice(halfLen);
    const normalize = (s: string) => s.replace(/\s+/g, '').toLowerCase();
    if (normalize(firstHalf) === normalize(secondHalf)) {
      return firstHalf.trim();
    }
  }

  return raw;
}

export const LatexRenderer: React.FC<{ payload: LatexDerivationPayload }> = ({ payload }) => {
  const steps = payload?.steps;
  if (!Array.isArray(steps)) return null;
  return <div className="um-visual-steps">
    {payload.title && <h3>{payload.title}</h3>}
    <ol className="um-visual-step-list">{steps.map((step, index) => <li key={index}>
      <span className="um-visual-step-number" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
      <div><div className="um-visual-formula"><MarkdownContent content={`$$${deduplicateLatex(step.latex)}$$`} /></div>
        {step.note && <p className="um-visual-note">{step.note}</p>}</div>
    </li>)}</ol>
  </div>;
};
