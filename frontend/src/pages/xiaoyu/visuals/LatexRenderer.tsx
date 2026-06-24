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
  return (
    <div className="p-5 space-y-5">
      {payload.title && (
        <h3 className="text-[15px] font-semibold tracking-tight text-foreground">{payload.title}</h3>
      )}
      <div className="space-y-0">
        {steps.map((step, i) => (
          <div key={i} className="relative pl-5 pb-5 last:pb-0">
            {/* Vertical connector line */}
            {i < steps.length - 1 && (
              <div className="absolute left-[3px] top-[10px] bottom-0 w-px bg-foreground/10" />
            )}
            {/* Dot */}
            <div className="absolute left-0 top-[6px] w-[7px] h-[7px] rounded-full bg-foreground/20" />
            {/* Step number */}
            <div className="text-[10px] font-medium text-foreground/30 tabular-nums mb-1.5">
              {String(i + 1).padStart(2, '0')}
            </div>
            {/* Formula */}
            <div className="py-1">
              <MarkdownContent content={`$$${deduplicateLatex(step.latex)}$$`} />
            </div>
            {/* Note */}
            {step.note && (
              <p className="text-[13px] text-foreground/45 leading-relaxed mt-1">{step.note}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
