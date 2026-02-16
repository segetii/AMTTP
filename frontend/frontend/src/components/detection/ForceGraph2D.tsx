'use client';

/**
 * ForceGraph2D – lightweight Canvas 2D force-directed graph
 *
 * Replaces reagraph (Three.js / WebGL) to eliminate:
 *   - 5 MB+ webpack chunk that times out in dev mode
 *   - WeakMap texture errors from Three.js
 *   - 200 s+ compilation delays
 *
 * Features:
 *   - Canvas 2D rendering (no WebGL)
 *   - Simple force-directed layout (charge + link + center)
 *   - Zoom & pan via mouse wheel / drag
 *   - Node click / hover
 *   - Node labels
 *   - Edge arrows
 *   - Works with the same data shapes as GraphExplorer
 */

import React, {
  useRef,
  useEffect,
  useCallback,
  useState,
  useImperativeHandle,
  forwardRef,
} from 'react';

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ForceNode {
  id: string;
  label: string;
  fill: string;
  data?: unknown;
  // simulation state (mutated in-place)
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  fx?: number | null; // fixed position (pinned)
  fy?: number | null;
}

export interface ForceEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
  data?: unknown;
}

export interface ForceGraph2DRef {
  centerGraph: () => void;
  zoomIn: () => void;
  zoomOut: () => void;
  fitNodesInView: () => void;
}

interface ForceGraph2DProps {
  nodes: ForceNode[];
  edges: ForceEdge[];
  onNodeClick?: (node: ForceNode) => void;
  width?: number;
  height?: number;
  backgroundColor?: string;
}

// ─── Constants ───────────────────────────────────────────────────────────────

const NODE_RADIUS = 11;
const FONT_SIZE = 9;
const ARROW_SIZE = 5;
const EDGE_COLOR = '#475569';
const EDGE_HIGHLIGHT = '#818cf8';
const LABEL_COLOR = '#e2e8f0';
const MIN_ZOOM = 0.1;
const MAX_ZOOM = 5;

// Force simulation parameters
const SIM_CHARGE = -400;       // repulsion between all nodes
const SIM_LINK_DISTANCE = 120; // ideal link length
const SIM_LINK_STRENGTH = 0.3;
const SIM_CENTER_STRENGTH = 0.05;
const SIM_FRICTION = 0.85;     // velocity damping
const SIM_ALPHA_DECAY = 0.005; // how fast the sim cools
const SIM_ALPHA_MIN = 0.001;

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Build adjacency lookup: sourceId|targetId → edge */
function buildEdgeMap(edges: ForceEdge[]): Map<string, ForceEdge[]> {
  const m = new Map<string, ForceEdge[]>();
  for (const e of edges) {
    const key = e.source;
    if (!m.has(key)) m.set(key, []);
    m.get(key)!.push(e);
    const key2 = e.target;
    if (!m.has(key2)) m.set(key2, []);
    m.get(key2)!.push(e);
  }
  return m;
}

// ─── Component ───────────────────────────────────────────────────────────────

const ForceGraph2D = forwardRef<ForceGraph2DRef, ForceGraph2DProps>(
  function ForceGraph2D(
    {
      nodes: inputNodes,
      edges: inputEdges,
      onNodeClick,
      backgroundColor = '#0f172a',
    },
    ref,
  ) {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);

    // We keep mutable simulation state in refs to avoid re-renders
    const simNodes = useRef<ForceNode[]>([]);
    const simEdges = useRef<ForceEdge[]>([]);
    const nodeMap = useRef<Map<string, ForceNode>>(new Map());

    const alpha = useRef(1);          // simulation "temperature"
    const rafId = useRef(0);
    const mounted = useRef(true);

    // Camera state
    const camera = useRef({ x: 0, y: 0, zoom: 1 });

    // Interaction state
    const [hoveredNode, setHoveredNode] = useState<string | null>(null);
    const dragNode = useRef<ForceNode | null>(null);
    const isPanning = useRef(false);
    const lastMouse = useRef({ x: 0, y: 0 });

    // Canvas dimensions
    const canvasSize = useRef({ w: 800, h: 600 });

    // ── Initialise / update simulation data ──────────────────────────────

    useEffect(() => {
      const nm = new Map<string, ForceNode>();

      // Preserve existing positions when data changes
      const oldMap = nodeMap.current;

      const newNodes: ForceNode[] = inputNodes.map((n, i) => {
        const old = oldMap.get(n.id);
        const angle = (2 * Math.PI * i) / inputNodes.length;
        const r = Math.min(canvasSize.current.w, canvasSize.current.h) * 0.3;
        return {
          ...n,
          x: old?.x ?? Math.cos(angle) * r + (Math.random() - 0.5) * 30,
          y: old?.y ?? Math.sin(angle) * r + (Math.random() - 0.5) * 30,
          vx: old?.vx ?? 0,
          vy: old?.vy ?? 0,
          fx: old?.fx ?? null,
          fy: old?.fy ?? null,
        };
        
      });

      for (const nd of newNodes) nm.set(nd.id, nd);

      simNodes.current = newNodes;
      simEdges.current = inputEdges.filter(
        (e) => nm.has(e.source) && nm.has(e.target),
      );
      nodeMap.current = nm;

      // Reheat when data changes
      alpha.current = 1;
    }, [inputNodes, inputEdges]);

    // ── Resize observer ──────────────────────────────────────────────────

    useEffect(() => {
      const container = containerRef.current;
      if (!container) return;

      const ro = new ResizeObserver((entries) => {
        for (const entry of entries) {
          const { width, height } = entry.contentRect;
          canvasSize.current = { w: width, h: height };
          const canvas = canvasRef.current;
          if (canvas) {
            const dpr = window.devicePixelRatio || 1;
            canvas.width = width * dpr;
            canvas.height = height * dpr;
            canvas.style.width = `${width}px`;
            canvas.style.height = `${height}px`;
          }
        }
      });

      ro.observe(container);
      return () => ro.disconnect();
    }, []);

    // ── Force simulation tick ────────────────────────────────────────────

    const tick = useCallback(() => {
      const nodes = simNodes.current;
      const edges = simEdges.current;
      const nm = nodeMap.current;

      if (alpha.current < SIM_ALPHA_MIN) return; // cooled – skip physics

      // 1. Charge (repulsion between every pair – O(n²), fine for <500 nodes)
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const a = nodes[i];
          const b = nodes[j];
          let dx = (b.x ?? 0) - (a.x ?? 0);
          let dy = (b.y ?? 0) - (a.y ?? 0);
          let dist = Math.sqrt(dx * dx + dy * dy) || 1;
          if (dist < 1) dist = 1;
          const force = (SIM_CHARGE * alpha.current) / (dist * dist);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          a.vx = (a.vx ?? 0) - fx;
          a.vy = (a.vy ?? 0) - fy;
          b.vx = (b.vx ?? 0) + fx;
          b.vy = (b.vy ?? 0) + fy;
        }
      }

      // 2. Link spring
      for (const e of edges) {
        const s = nm.get(e.source);
        const t = nm.get(e.target);
        if (!s || !t) continue;
        let dx = (t.x ?? 0) - (s.x ?? 0);
        let dy = (t.y ?? 0) - (s.y ?? 0);
        let dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const displacement = (dist - SIM_LINK_DISTANCE) * SIM_LINK_STRENGTH * alpha.current;
        const fx = (dx / dist) * displacement;
        const fy = (dy / dist) * displacement;
        s.vx = (s.vx ?? 0) + fx;
        s.vy = (s.vy ?? 0) + fy;
        t.vx = (t.vx ?? 0) - fx;
        t.vy = (t.vy ?? 0) - fy;
      }

      // 3. Center gravity
      for (const n of nodes) {
        n.vx = (n.vx ?? 0) - (n.x ?? 0) * SIM_CENTER_STRENGTH * alpha.current;
        n.vy = (n.vy ?? 0) - (n.y ?? 0) * SIM_CENTER_STRENGTH * alpha.current;
      }

      // 4. Integrate
      for (const n of nodes) {
        if (n.fx != null) {
          n.x = n.fx;
          n.vx = 0;
        } else {
          n.vx = (n.vx ?? 0) * SIM_FRICTION;
          n.x = (n.x ?? 0) + (n.vx ?? 0);
        }
        if (n.fy != null) {
          n.y = n.fy;
          n.vy = 0;
        } else {
          n.vy = (n.vy ?? 0) * SIM_FRICTION;
          n.y = (n.y ?? 0) + (n.vy ?? 0);
        }
      }

      // 5. Cool
      alpha.current = Math.max(alpha.current - SIM_ALPHA_DECAY, 0);
    }, []);

    // ── Draw ─────────────────────────────────────────────────────────────

    const draw = useCallback(() => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const dpr = window.devicePixelRatio || 1;
      const w = canvasSize.current.w;
      const h = canvasSize.current.h;
      const cam = camera.current;
      const nodes = simNodes.current;
      const edges = simEdges.current;
      const nm = nodeMap.current;

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      // Background
      ctx.fillStyle = backgroundColor;
      ctx.fillRect(0, 0, w, h);

      // Apply camera
      ctx.save();
      ctx.translate(w / 2 + cam.x, h / 2 + cam.y);
      ctx.scale(cam.zoom, cam.zoom);

      // ── Edges ──────────────────────────────────────────────────────────
      for (const e of edges) {
        const s = nm.get(e.source);
        const t = nm.get(e.target);
        if (!s || !t) continue;

        const sx = s.x ?? 0;
        const sy = s.y ?? 0;
        const tx = t.x ?? 0;
        const ty = t.y ?? 0;

        const isHighlighted =
          hoveredNode === e.source || hoveredNode === e.target;

        ctx.beginPath();
        ctx.moveTo(sx, sy);
        ctx.lineTo(tx, ty);
        ctx.strokeStyle = isHighlighted ? EDGE_HIGHLIGHT : EDGE_COLOR;
        ctx.lineWidth = isHighlighted ? 2 : 1;
        ctx.globalAlpha = isHighlighted ? 1 : 0.5;
        ctx.stroke();
        ctx.globalAlpha = 1;

        // Arrowhead
        const angle = Math.atan2(ty - sy, tx - sx);
        const edgeDist = Math.sqrt((tx - sx) ** 2 + (ty - sy) ** 2);
        if (edgeDist > NODE_RADIUS * 2) {
          const ax = tx - Math.cos(angle) * (NODE_RADIUS + 2);
          const ay = ty - Math.sin(angle) * (NODE_RADIUS + 2);
          ctx.beginPath();
          ctx.moveTo(ax, ay);
          ctx.lineTo(
            ax - ARROW_SIZE * Math.cos(angle - Math.PI / 6),
            ay - ARROW_SIZE * Math.sin(angle - Math.PI / 6),
          );
          ctx.lineTo(
            ax - ARROW_SIZE * Math.cos(angle + Math.PI / 6),
            ay - ARROW_SIZE * Math.sin(angle + Math.PI / 6),
          );
          ctx.closePath();
          ctx.fillStyle = isHighlighted ? EDGE_HIGHLIGHT : EDGE_COLOR;
          ctx.fill();
        }
      }

      // ── Nodes ──────────────────────────────────────────────────────────
      for (const n of nodes) {
        const x = n.x ?? 0;
        const y = n.y ?? 0;
        const isHovered = hoveredNode === n.id;

        // Glow for hovered
        if (isHovered) {
          ctx.beginPath();
          ctx.arc(x, y, NODE_RADIUS + 6, 0, Math.PI * 2);
          ctx.fillStyle = n.fill + '33'; // 20% opacity
          ctx.fill();
        }

        // Node circle
        ctx.beginPath();
        ctx.arc(x, y, NODE_RADIUS, 0, Math.PI * 2);
        ctx.fillStyle = n.fill;
        ctx.fill();

        // Outline
        ctx.strokeStyle = isHovered ? '#ffffff' : 'rgba(255,255,255,0.15)';
        ctx.lineWidth = isHovered ? 2 : 1;
        ctx.stroke();

        // Label
        ctx.fillStyle = LABEL_COLOR;
        ctx.font = `${FONT_SIZE}px ui-monospace, SFMono-Regular, Menlo, monospace`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        const labelText =
          n.label.length > 14 ? n.label.slice(0, 12) + '…' : n.label;
        ctx.fillText(labelText, x, y + NODE_RADIUS + 4);
      }

      ctx.restore();
    }, [backgroundColor, hoveredNode]);

    // ── Animation loop ───────────────────────────────────────────────────

    useEffect(() => {
      mounted.current = true;

      const loop = () => {
        if (!mounted.current) return;
        tick();
        draw();
        rafId.current = requestAnimationFrame(loop);
      };

      rafId.current = requestAnimationFrame(loop);

      return () => {
        mounted.current = false;
        cancelAnimationFrame(rafId.current);
      };
    }, [tick, draw]);

    // ── Hit-testing helper ───────────────────────────────────────────────

    const screenToWorld = useCallback((sx: number, sy: number) => {
      const cam = camera.current;
      const w = canvasSize.current.w;
      const h = canvasSize.current.h;
      return {
        x: (sx - w / 2 - cam.x) / cam.zoom,
        y: (sy - h / 2 - cam.y) / cam.zoom,
      };
    }, []);

    const hitTest = useCallback(
      (sx: number, sy: number): ForceNode | null => {
        const { x, y } = screenToWorld(sx, sy);
        // Iterate in reverse so top-drawn nodes are hit first
        const nodes = simNodes.current;
        for (let i = nodes.length - 1; i >= 0; i--) {
          const n = nodes[i];
          const dx = (n.x ?? 0) - x;
          const dy = (n.y ?? 0) - y;
          if (dx * dx + dy * dy <= (NODE_RADIUS + 4) ** 2) return n;
        }
        return null;
      },
      [screenToWorld],
    );

    // ── Mouse handlers ───────────────────────────────────────────────────

    const getCanvasPos = useCallback((e: React.MouseEvent | MouseEvent) => {
      const canvas = canvasRef.current;
      if (!canvas) return { x: 0, y: 0 };
      const rect = canvas.getBoundingClientRect();
      return { x: e.clientX - rect.left, y: e.clientY - rect.top };
    }, []);

    const handleMouseDown = useCallback(
      (e: React.MouseEvent<HTMLCanvasElement>) => {
        const pos = getCanvasPos(e);
        const node = hitTest(pos.x, pos.y);
        if (node) {
          dragNode.current = node;
          node.fx = node.x;
          node.fy = node.y;
          alpha.current = Math.max(alpha.current, 0.3); // reheat slightly
        } else {
          isPanning.current = true;
        }
        lastMouse.current = pos;
      },
      [getCanvasPos, hitTest],
    );

    const handleMouseMove = useCallback(
      (e: React.MouseEvent<HTMLCanvasElement>) => {
        const pos = getCanvasPos(e);

        if (dragNode.current) {
          const { x, y } = screenToWorld(pos.x, pos.y);
          dragNode.current.fx = x;
          dragNode.current.fy = y;
          dragNode.current.x = x;
          dragNode.current.y = y;
          alpha.current = Math.max(alpha.current, 0.1);
        } else if (isPanning.current) {
          camera.current.x += pos.x - lastMouse.current.x;
          camera.current.y += pos.y - lastMouse.current.y;
        } else {
          // Hover detection
          const node = hitTest(pos.x, pos.y);
          setHoveredNode(node?.id ?? null);
          const canvas = canvasRef.current;
          if (canvas) canvas.style.cursor = node ? 'pointer' : 'grab';
        }

        lastMouse.current = pos;
      },
      [getCanvasPos, hitTest, screenToWorld],
    );

    const handleMouseUp = useCallback(() => {
      if (dragNode.current) {
        // Unpin the node so simulation can settle
        dragNode.current.fx = null;
        dragNode.current.fy = null;
        dragNode.current = null;
      }
      isPanning.current = false;
    }, []);

    const handleClick = useCallback(
      (e: React.MouseEvent<HTMLCanvasElement>) => {
        const pos = getCanvasPos(e);
        const node = hitTest(pos.x, pos.y);
        if (node && onNodeClick) {
          onNodeClick(node);
        }
      },
      [getCanvasPos, hitTest, onNodeClick],
    );

    const handleWheel = useCallback((e: React.WheelEvent<HTMLCanvasElement>) => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.1 : 0.9;
      camera.current.zoom = Math.max(
        MIN_ZOOM,
        Math.min(MAX_ZOOM, camera.current.zoom * factor),
      );
    }, []);

    // ── Imperative API ───────────────────────────────────────────────────

    useImperativeHandle(
      ref,
      () => ({
        centerGraph() {
          camera.current = { x: 0, y: 0, zoom: 1 };
        },
        zoomIn() {
          camera.current.zoom = Math.min(MAX_ZOOM, camera.current.zoom * 1.3);
        },
        zoomOut() {
          camera.current.zoom = Math.max(MIN_ZOOM, camera.current.zoom / 1.3);
        },
        fitNodesInView() {
          const nodes = simNodes.current;
          if (nodes.length === 0) return;
          let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
          for (const n of nodes) {
            const nx = n.x ?? 0;
            const ny = n.y ?? 0;
            if (nx < minX) minX = nx;
            if (nx > maxX) maxX = nx;
            if (ny < minY) minY = ny;
            if (ny > maxY) maxY = ny;
          }
          const bw = maxX - minX || 1;
          const bh = maxY - minY || 1;
          const padding = 80;
          const zoom = Math.min(
            (canvasSize.current.w - padding * 2) / bw,
            (canvasSize.current.h - padding * 2) / bh,
            2,
          );
          camera.current = {
            x: -((minX + maxX) / 2) * zoom,
            y: -((minY + maxY) / 2) * zoom,
            zoom,
          };
        },
      }),
      [],
    );

    // ── Render ───────────────────────────────────────────────────────────

    return (
      <div
        ref={containerRef}
        style={{ width: '100%', height: '100%', position: 'relative' }}
      >
        <canvas
          ref={canvasRef}
          style={{ width: '100%', height: '100%', display: 'block', cursor: 'grab' }}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          onClick={handleClick}
          onWheel={handleWheel}
        />
      </div>
    );
  },
);

export default ForceGraph2D;
