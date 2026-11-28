import { useState } from 'react';
import { Play } from '@phosphor-icons/react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { parseSeekSeconds, sendTabMessage, UNIMIND_SEEK_VIDEO } from '../shared/bridge';

interface MarkdownNode {
  type: string;
  value?: string;
  url?: string;
  children?: MarkdownNode[];
}

export function formatVideoTime(seconds: number): string {
  const total = Math.floor(seconds);
  const minutes = Math.floor(total / 60);
  const remainder = String(total % 60).padStart(2, '0');
  return minutes >= 60
    ? `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}:${remainder}`
    : `${String(minutes).padStart(2, '0')}:${remainder}`;
}

// Transform text nodes, keeping code, existing links, and formulae intact.
function remarkSeekTimestamps() {
  return (tree: MarkdownNode) => {
    function visit(node: MarkdownNode) {
      if (!node.children || ['link', 'code', 'inlineCode', 'math', 'inlineMath'].includes(node.type)) return;
      node.children = node.children.flatMap(child => {
        if (child.type !== 'text' || !child.value) {
          visit(child);
          return [child];
        }
        const nodes: MarkdownNode[] = [];
        const matches = child.value.matchAll(/\[(?:\d+:)?\d+:\d{2}\]/g);
        let cursor = 0;
        for (const match of matches) {
          const seconds = parseSeekSeconds(match[0]);
          if (seconds === null) continue;
          const start = match.index;
          if (start > cursor) nodes.push({ type: 'text', value: child.value.slice(cursor, start) });
          nodes.push({ type: 'link', url: `#seek:${seconds}`, children: [{ type: 'text', value: match[0] }] });
          cursor = start + match[0].length;
        }
        if (!cursor) return [child];
        if (cursor < child.value.length) nodes.push({ type: 'text', value: child.value.slice(cursor) });
        return nodes;
      });
    }
    visit(tree);
  };
}

export async function seekActiveVideo(seconds: number): Promise<void> {
  const tab = (await chrome.tabs.query({ active: true, lastFocusedWindow: true }))[0];
  if (tab?.id === undefined) throw new Error('请先打开正在播放的视频页面。');
  const result = await sendTabMessage(tab.id, UNIMIND_SEEK_VIDEO, { seconds });
  if (!result?.ok) throw new Error('当前页面暂时无法跳播。');
}

export function MarkdownMessage({ content, onSeek }: {
  content: string;
  onSeek?: (seconds: number) => void | Promise<void>;
}) {
  const [seekError, setSeekError] = useState('');
  async function seek(seconds: number) {
    setSeekError('');
    try { await (onSeek ?? seekActiveVideo)(seconds); }
    catch (error) { setSeekError(error instanceof Error ? error.message : '当前页面暂时无法跳播。'); }
  }
  return <div className="markdown-message">
    <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath, remarkSeekTimestamps]} rehypePlugins={[rehypeKatex]}
      components={{
        a({ href, children }) {
          const seconds = parseSeekSeconds(href ?? '');
          return seconds !== null
            ? <button type="button" className="seek-pill" title={`跳播到 ${formatVideoTime(seconds)}`}
                aria-label={`跳播到 ${formatVideoTime(seconds)}`} onClick={() => void seek(seconds)}><Play size={11} weight="fill" aria-hidden="true" />{formatVideoTime(seconds)}</button>
            : <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
        },
      }}>{content}</ReactMarkdown>
    {seekError && <p className="inline-error" role="status">{seekError}</p>}
  </div>;
}
