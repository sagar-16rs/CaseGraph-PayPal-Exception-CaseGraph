import type { GraphEdge, GraphNode } from '../api/types';

/**
 * Deterministic graph layout.
 *
 * CaseGraph outputs are epistemic, not force-directed: nodes belong to named
 * columns (authoritative facts, claims, inferences, gaps, action) and the
 * interesting information is the edge between two specific nodes. A stable
 * column layout is therefore both easier to read and reproducible in a demo or
 * a screenshot, which a physics simulation is not.
 */
export const NODE_COLUMNS = [
  'VERIFIED_FACT',
  'CUSTOMER_CLAIM',
  'MERCHANT_CLAIM',
  'EVENT',
  'MISSING_EVIDENCE',
  'AI_INFERENCE',
  'ACTION',
] as const;

export type NodeType = (typeof NODE_COLUMNS)[number];

export const NODE_LABEL: Record<string, string> = {
  VERIFIED_FACT: 'Verified PayPal fact',
  CUSTOMER_CLAIM: 'Customer claim',
  MERCHANT_CLAIM: 'Merchant claim',
  EVENT: 'Event',
  MISSING_EVIDENCE: 'Missing evidence',
  AI_INFERENCE: 'AI inference',
  ACTION: 'Action',
};

const COLUMN_WIDTH = 200;
const COLUMN_GAP = 44;
const NODE_HEIGHT = 96;
const NODE_GAP = 14;
const PAD = 24;
const HEADER_SPACE = 24;
const SPACING = NODE_HEIGHT + NODE_GAP;

export interface LaidOutNode {
  node: GraphNode;
  x: number;
  y: number;
  column: number;
}

export interface LaidOutEdge {
  edge: GraphEdge;
  path: string;
  from: LaidOutNode;
  to: LaidOutNode;
  contradicted: boolean;
}

export interface GraphLayout {
  width: number;
  height: number;
  nodes: LaidOutNode[];
  edges: LaidOutEdge[];
  columns: { type: string; label: string; x: number; count: number }[];
}

export function layoutGraph(nodes: GraphNode[], edges: GraphEdge[]): GraphLayout {
  const columns = NODE_COLUMNS.filter((type) => nodes.some((node) => node.node_type === type));
  const byColumn = new Map<string, GraphNode[]>();
  for (const type of columns) {
    byColumn.set(type, nodes.filter((node) => node.node_type === type));
  }

  // Every column starts on the same baseline and stacks downwards. A layered
  // "average of parents" placement was tried and rejected: root nodes (claims,
  // facts) have no parents, so they fell to the bottom of the canvas and dragged
  // the provenance edges into long diagonals. Predictable beats clever here.
  const top = PAD + HEADER_SPACE;
  const tallest = Math.max(1, ...columns.map((type) => byColumn.get(type)!.length));
  const height = top + tallest * NODE_HEIGHT + (tallest - 1) * NODE_GAP + PAD;
  const width = PAD * 2 + columns.length * COLUMN_WIDTH + Math.max(0, columns.length - 1) * COLUMN_GAP;

  const positioned = new Map<string, LaidOutNode>();
  const laidOutNodes: LaidOutNode[] = [];
  columns.forEach((type, columnIndex) => {
    byColumn.get(type)!.forEach((node, index) => {
      const laid: LaidOutNode = {
        node,
        column: columnIndex,
        x: PAD + columnIndex * (COLUMN_WIDTH + COLUMN_GAP),
        y: top + index * (NODE_HEIGHT + NODE_GAP),
      };
      positioned.set(node.node_id, laid);
      laidOutNodes.push(laid);
    });
  });

  const laidOutEdges: LaidOutEdge[] = [];
  for (const edge of edges) {
    const from = positioned.get(edge.source_node_id);
    const to = positioned.get(edge.target_node_id);
    if (!from || !to) continue;
    const contradicted = edge.relation_type === 'CONTRADICTS';
    laidOutEdges.push({
      edge,
      from,
      to,
      contradicted,
      path: curve(from, to, contradicted),
    });
  }

  return {
    width,
    height,
    nodes: laidOutNodes,
    edges: laidOutEdges,
    columns: columns.map((type, index) => ({
      type,
      label: NODE_LABEL[type] ?? type,
      x: PAD + index * (COLUMN_WIDTH + COLUMN_GAP),
      count: byColumn.get(type)!.length,
    })),
  };
}

function curve(from: LaidOutNode, to: LaidOutNode, contradicted: boolean): string {
  const fromRight = from.x + COLUMN_WIDTH;
  const toLeft = to.x;
  const sameColumn = from.column === to.column;
  const forward = toLeft >= fromRight;
  const startX = sameColumn || !forward ? fromRight - 12 : fromRight;
  const endX = sameColumn || !forward ? toLeft + COLUMN_WIDTH - 12 : toLeft;
  const startY = from.y + NODE_HEIGHT / 2;
  const endY = to.y + NODE_HEIGHT / 2;
  const bow = sameColumn || !forward ? 54 : Math.max(36, Math.abs(endX - startX) / 2.2);
  const lift = contradicted ? 0 : 0;
  return [
    `M ${startX} ${startY + lift}`,
    `C ${startX + bow} ${startY + lift}, ${endX - bow} ${endY}, ${endX} ${endY}`,
  ].join(' ');
}

export function nodeAccent(type: string): string {
  switch (type) {
    case 'VERIFIED_FACT':
      return 'fact';
    case 'CUSTOMER_CLAIM':
      return 'customer';
    case 'MERCHANT_CLAIM':
      return 'merchant';
    case 'AI_INFERENCE':
      return 'inference';
    case 'MISSING_EVIDENCE':
      return 'gap';
    case 'ACTION':
      return 'action';
    default:
      return 'event';
  }
}

