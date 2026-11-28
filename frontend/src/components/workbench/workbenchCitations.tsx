import { createContext, type ComponentType } from 'react';
import type { Root, RootContent, Text } from 'mdast';
import type { Components } from 'react-markdown';
import type { Plugin } from 'unified';
import type { SourceAnchor, WorkbenchCitation } from '@/types/workbench';
import { AssetCitationLink, CitationPill, type AssetCitation } from './CitationPill';

interface CitationContext {
  conversationId: string;
  onSelect: (anchor: SourceAnchor) => void;
}

export const WorkbenchCitationContext = createContext<CitationContext | null>(null);

const keyPattern = String.raw`(?:S\d+#C\d+(?:[LT]\d+)?|[NAW]\d+#L\d+|V\d+#T\d+)`;
const marker = new RegExp(String.raw`\[(${keyPattern}(?:\s*[,，]\s*${keyPattern})*)\]`, 'g');
const trailingMarker = /\[(?:[SNAVW]\d+#(?:[CLT]\d+[LT]?\d*)?\s*[,，]\s*)*[SNAVW]\d*(?:#[CLT]?\d*[LT]?\d*)?$/;

export function stripStreamingCitations(content: string) {
  return content.replace(marker, '').replace(trailingMarker, '');
}

export function splitCitationMarkers(content: string) {
  const parts: (string | { keys: string[] })[] = [];
  let start = 0;
  for (const match of content.matchAll(marker)) {
    if (start < match.index) parts.push(content.slice(start, match.index));
    parts.push({ keys: match[1].split(/\s*[,，]\s*/) });
    start = match.index + match[0].length;
  }
  if (start < content.length) parts.push(content.slice(start));
  return parts;
}

const remarkWorkbenchCitations: Plugin<[], Root> = () => tree => {
  function transform(node: Root | RootContent) {
    if (!('children' in node) || node.type === 'link' || node.type === 'linkReference') return;
    const children: RootContent[] = node.children;
    const transformed = children.flatMap((child): RootContent[] => {
      if (child.type !== 'text') {
        transform(child);
        return [child];
      }
      if (!child.value.includes('[')) return [child];
      return splitCitationMarkers(child.value).flatMap((part): RootContent[] => {
        if (typeof part === 'string') return [{ type: 'text', value: part } satisfies Text];
        return part.keys.map(key => ({
          type: 'emphasis', children: [],
          data: { hName: 'span', hProperties: { 'data-workbench-cite': key } },
        }));
      });
    });
    children.splice(0, children.length, ...transformed);
  }
  transform(tree);
};

export function workbenchCitationMarkdown(citations: WorkbenchCitation[], context: CitationContext | null, components?: Components, assets: AssetCitation[] = []) {
  const byKey = new Map(citations.map(citation => [citation.cite_key, citation]));
  const assetsByKey = new Map(assets.map(citation => [citation.key, citation]));
  return {
    extraRemarkPlugins: [remarkWorkbenchCitations],
    components: {
      ...components,
      span: props => {
        const key = props.node?.properties['data-workbench-cite'];
        if (typeof key === 'string') {
          const asset = assetsByKey.get(key);
          if (asset) return <AssetCitationLink citation={asset} />;
          const citation = byKey.get(key);
          return citation && context ? <CitationPill citation={citation} {...context} /> : null;
        }
        const Span = components?.span as ComponentType<typeof props> | undefined;
        if (Span) return <Span {...props} />;
        const attributes = { ...props };
        delete attributes.node;
        return <span {...attributes} />;
      },
    } satisfies Components,
  };
}
