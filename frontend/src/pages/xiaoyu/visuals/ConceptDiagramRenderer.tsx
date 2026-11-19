import React from 'react';
import { MarkdownContent } from '@/components/MarkdownContent';

export interface ConceptDiagramNode {
  id: string;
  label: string;
  detail?: string;
  badge?: string;
  highlight?: boolean;
}

export interface ConceptDiagramEdge {
  from: string;
  to: string;
  label?: string;
}

export interface ConceptDiagramPayload {
  title: string;
  subtitle?: string;
  layout?: 'flow' | 'hierarchy' | 'cycle' | 'compare';
  nodes: ConceptDiagramNode[];
  edges?: ConceptDiagramEdge[];
}

export const ConceptDiagramRenderer: React.FC<{ payload: ConceptDiagramPayload }> = ({ payload }) => {
  const nodes = Array.isArray(payload?.nodes) ? payload.nodes : [];
  const edges = Array.isArray(payload?.edges) ? payload.edges : [];
  if (!nodes.length) return null;

  const nodeMap = new Map(nodes.map(n => [n.id, n]));
  const layout = payload.layout ?? 'flow';
  const edgeBetween = (fromId: string, toId: string) =>
    edges.find(e => e.from === fromId && e.to === toId);

  return (
    <div className={`um-concept-diagram is-${layout}`}>
      <div className="um-visual-heading">
        {payload.title && <h3>{payload.title}</h3>}
        {payload.subtitle && <p>{payload.subtitle}</p>}
      </div>

      <ol className={`um-concept-nodes is-${layout}`}>
        {nodes.map((node, index) => {
          const nextNode = nodes[index + 1];
          const connector = nextNode ? edgeBetween(node.id, nextNode.id) : undefined;
          return (
            <React.Fragment key={node.id || index}>
              <li className={`um-concept-node${node.highlight ? ' is-highlight' : ''}`}>
                <div className="um-concept-node-head">
                  <span className="um-concept-node-index">{String(index + 1).padStart(2, '0')}</span>
                  <strong className="um-concept-node-label">{node.label}</strong>
                  {node.badge && <span className="um-concept-node-badge">{node.badge}</span>}
                </div>
                {node.detail && (
                  <div className="um-concept-node-detail">
                    <MarkdownContent content={node.detail} className="prose prose-sm max-w-none dark:prose-invert" />
                  </div>
                )}
              </li>
              {nextNode && layout === 'flow' && (
                <li className="um-concept-connector" aria-hidden="true">
                  <span className="um-concept-arrow">↓</span>
                  {connector?.label && <span className="um-concept-edge-label">{connector.label}</span>}
                </li>
              )}
            </React.Fragment>
          );
        })}
      </ol>

      {edges.length > 0 && layout !== 'flow' && (
        <ul className="um-concept-relations" aria-label="关系连线">
          {edges.map((edge, idx) => {
            const fromLabel = nodeMap.get(edge.from)?.label ?? edge.from;
            const toLabel = nodeMap.get(edge.to)?.label ?? edge.to;
            return (
              <li key={`${edge.from}-${edge.to}-${idx}`}>
                <span>{fromLabel}</span>
                <span className="um-concept-rel-arrow">→</span>
                {edge.label && <em className="um-concept-edge-label">{edge.label}</em>}
                {edge.label && <span className="um-concept-rel-arrow">→</span>}
                <span>{toLabel}</span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};
