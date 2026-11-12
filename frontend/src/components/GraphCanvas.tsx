import { useMemo, useState } from 'react';
import type { GraphEdge, GraphNode } from '../api/types';
import { layoutGraph, nodeAccent } from '../lib/graph';
import { NODE_KIND } from '../lib/format';

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  highlight?: string[];
  onSelect?: (nodeId: string | null) => void;
  selected?: string | null;
}

const COLUMN_WIDTH = 200;

/**
 * The provenance canvas.
 *
 * Columns encode epistemic status (what PayPal says, what the parties say, what
 * the model concluded, what is missing) and edges carry the reasoning. This is an
 * analysis view, not a presentation graphic: stable column order, thin rules, and
 * no layout animation, so the same case always renders the same way.
 */
export default function GraphCanvas({ nodes, edges, highlight = [], onSelect, selected }: Props) {
  const layout = useMemo(() => layoutGraph(nodes, edges), [nodes, edges]);
  const [hovered, setHovered] = useState<string | null>(null);

  if (!nodes.length) {
    return <div className="empty">This revision has no nodes.</div>;
  }

  const focus = new Set<string>([...(highlight ?? []), ...(selected ? [selected] : [])]);
  if (hovered) focus.add(hovered);

  return (
    <div className="graph">
      <div className="graph-toolbar">
        <div className="legend">
          <span><i style={{ background: 'var(--authority)' }} />PayPal fact</span>
          <span><i style={{ background: 'var(--claim)' }} />Party claim</span>
          <span><i style={{ background: 'var(--inference)' }} />Model inference</span>
          <span><i style={{ background: 'var(--risk)' }} />Missing evidence</span>
          <span><i style={{ background: 'var(--ink)' }} />Action</span>
          <span style={{ color: 'var(--risk)' }}>┄ contradiction</span>
        </div>
      </div>

      <div className="graph-scroll">
        <div className="graph-canvas" style={{ width: layout.width, height: layout.height }}>
          {layout.columns.map((column) => (
            <div
              key={column.type}
              className="graph-colhead"
              style={{ left: column.x, width: COLUMN_WIDTH }}
            >
              <span>{NODE_KIND[column.type] ?? column.type}</span>
              <span>{column.count}</span>
            </div>
          ))}

          <svg className="graph-edges" width={layout.width} height={layout.height} aria-hidden="true">
            <defs>
              <marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#8b8b7b" />
              </marker>
              <marker id="ar-bad" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#8c2f22" />
              </marker>
            </defs>
            {layout.edges.map(({ edge, path, contradicted }) => {
              const active = !focus.size || focus.has(edge.source_node_id) || focus.has(edge.target_node_id);
              return (
                <path
                  key={edge.edge_id}
                  d={path}
                  className={`edge ${contradicted ? 'edge-bad' : ''} ${active ? 'edge-focus' : 'edge-dim'}`}
                  style={{ color: contradicted ? 'var(--risk)' : '#8b8b7b' }}
                  markerEnd={contradicted ? 'url(#ar-bad)' : 'url(#ar)'}
                />
              );
            })}
          </svg>

          {layout.nodes.map(({ node, x, y }) => {
            const isFocus = focus.has(node.node_id);
            return (
              <button
                type="button"
                key={node.node_id}
                className={`node t-${nodeAccent(node.node_type)} ${isFocus ? '' : 'is-dim'}`}
                style={{ left: x, top: y, width: COLUMN_WIDTH, opacity: focus.size && !isFocus ? 0.45 : 1 }}
                onClick={() => onSelect?.(selected === node.node_id ? null : node.node_id)}
                onMouseEnter={() => setHovered(node.node_id)}
                onMouseLeave={() => setHovered(null)}
                aria-pressed={selected === node.node_id}
                title={node.statement}
              >
                <span className="kind">{NODE_KIND[node.node_type] ?? node.node_type}</span>
                <span className="title">{node.title}</span>
                <span className="body">{node.statement}</span>
                <span className="foot">
                  <span>{node.source_ref ? `${node.source_ref}@${node.source_revision}` : node.node_id}</span>
                  {typeof node.confidence === 'number' && node.confidence >= 0 && (
                    <span>{Math.round(node.confidence * 100)}%</span>
                  )}
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
