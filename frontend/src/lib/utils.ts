import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDuration(seconds: number): string {
  if (!seconds || seconds <= 0) return '00:00';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

/** Normalize options to array format — handles legacy dict-format data. */
export function normalizeOptions(options: any): string[] {
  if (Array.isArray(options)) return options;
  if (options && typeof options === 'object') {
    return Object.keys(options).sort().map(k => options[k]);
  }
  return [];
}

export function processMathContent(content: string) {
  if (!content) return "";
  
  // 1. Fix double backslashes ONLY when they precede a command letter.
  // This avoids breaking LaTeX newlines (\\) while fixing escaped commands (\\frac).
  let processed = content.replace(/\\\\([a-zA-Z])/g, '\\$1');

  // 2. Comprehensive unescape and autocorrect within math blocks ($...$ or $$...$$)
  // Use negative lookbehind/lookahead to skip currency $ (e.g. $100, $50 and $100)
  processed = processed.replace(/(?<![a-zA-Z0-9])(\$\$?)([\s\S]*?)(\$\$?)(?![a-zA-Z0-9])/g, (_match, open, inner, close) => {
    let math = inner
      .replace(/&gt;/g, '>')
      .replace(/&lt;/g, '<')
      .replace(/&amp;/g, '&')
      .replace(/\\_/g, '_')
      .replace(/\\\*/g, '*')
      .replace(/\\\{/g, '{')
      .replace(/\\\}/g, '}')
      .replace(/\\\^/g, '^');

    // Autocorrect: convert /command to \command (e.g., /frac to \frac)
    // Refined: only for lowercase commands of length >= 2 to avoid capturing division like V/D
    math = math.replace(/\/([a-z]{2,})/g, '\\$1');

    return open + math + close;
  });

  // 3. Delimiter Standardization
  return processed
    .replace(/\\\$/g, '$')
    .replace(/\\\[/g, '\n\n$$\n')
    .replace(/\\\]/g, '\n$$\n\n')
    .replace(/\\\(/g, '$')
    .replace(/\\\)/g, '$');
}
