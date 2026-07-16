"use client";

import { useEffect, useRef } from "react";
import cytoscape, { type Core } from "cytoscape";
import type { GraphData } from "@/lib/api";
import { SURFACE, sentimentColor, edgeFamily, type EdgeFamilyKey } from "@/lib/palette";

interface Props {
  data: GraphData;
  /** edge families currently visible (default: all) */
  visibleFamilies?: Set<EdgeFamilyKey>;
  onSelectNode?: (id: string | null) => void;
  selectedNode?: string | null;
  /** compact mode for inline chat cards: no pan/zoom, lighter labels */
  compact?: boolean;
  className?: string;
}

/** Lighten a #rrggbb color toward white by k (0..1), bright node cores. */
function lighten(hex: string, k: number): string {
  const p = hex.replace("#", "").match(/../g)!.map((h) => parseInt(h, 16));
  return `#${p.map((v) => Math.round(v + (255 - v) * k).toString(16).padStart(2, "0")).join("")}`;
}

export function GraphCanvas({
  data,
  visibleFamilies,
  onSelectNode,
  selectedNode,
  compact = false,
  className = "",
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const onSelectRef = useRef(onSelectNode);
  onSelectRef.current = onSelectNode;

  // (re)build the graph when data changes
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const elements = [
      ...data.nodes.map((n) => {
        const color = sentimentColor(n.sentiment);
        return {
          data: {
            id: n.id,
            label: n.id,
            color,
            // full stop list in one field, cytoscape can't compose data() mappers
            stops: `${lighten(color, 0.55)} ${color}`,
            size: n.is_center ? 30 : 12 + Math.min(n.article_count, 4) * 2.5,
            isCenter: n.is_center ? 1 : 0,
            hasSignal: n.sentiment !== null ? 1 : 0,
          },
        };
      }),
      ...data.edges.map((e, i) => {
        const fam = edgeFamily(e.rel_type);
        return {
          data: {
            id: `e${i}`,
            source: e.source,
            target: e.target,
            color: fam.color,
            family: fam.key,
            width: 0.7 + (e.confidence ?? 0.5) * 1.1,
          },
        };
      }),
    ];

    const cy = cytoscape({
      container,
      elements,
      style: [
        {
          // gradient core (bright center → sentiment color) + soft halo ring
          selector: "node",
          style: {
            "background-fill": "radial-gradient",
            "background-gradient-stop-colors": "data(stops)",
            "background-gradient-stop-positions": "0 85",
            width: "data(size)",
            height: "data(size)",
            "border-width": compact ? 4 : 7,
            "border-color": "data(color)",
            "border-opacity": 0.14,
            label: "data(label)",
            color: "#7e8798",
            "font-size": compact ? 8 : 9.5,
            "font-family": "ui-monospace, SFMono-Regular, monospace",
            "text-valign": "bottom",
            "text-margin-y": compact ? 4 : 6,
            "text-outline-width": 2,
            "text-outline-color": SURFACE,
            "text-outline-opacity": 0.9,
            "transition-property": "opacity",
            "transition-duration": 150,
          } as never,
        },
        {
          selector: "node[isCenter = 1]",
          style: {
            "border-width": 2,
            "border-color": "#22d3ee",
            "border-opacity": 1,
            color: "#e8ecf3",
            "font-size": compact ? 9 : 11,
            "font-weight": "bold",
            "text-margin-y": compact ? 5 : 8,
          } as never,
        },
        {
          selector: "node[hasSignal = 0]",
          style: { opacity: 0.55 } as never,
        },
        {
          selector: "node.selected",
          style: {
            "border-width": 2.5,
            "border-color": "#f2f4f8",
            "border-opacity": 1,
            color: "#f2f4f8",
          } as never,
        },
        {
          selector: "node.dimmed, edge.dimmed",
          style: { opacity: 0.1 } as never,
        },
        {
          // edges: whisper-thin arcs, no arrowheads by default
          selector: "edge",
          style: {
            "line-color": "data(color)",
            width: "data(width)",
            opacity: 0.42,
            "curve-style": "unbundled-bezier",
            "control-point-distances": "12",
            "control-point-weights": "0.5",
            "target-arrow-shape": "none",
            "transition-property": "opacity",
            "transition-duration": 150,
          } as never,
        },
        {
          // direction is only meaningful for supply-chain edges
          selector: 'edge[family = "supply"]',
          style: {
            "target-arrow-shape": "vee",
            "target-arrow-color": "data(color)",
            "arrow-scale": 0.55,
          } as never,
        },
        { selector: "edge.hidden-family", style: { display: "none" } as never },
      ],
      layout: {
        name: "cose",
        animate: false,
        nodeRepulsion: () => (compact ? 16000 : 34000),
        idealEdgeLength: () => (compact ? 62 : 110),
        padding: compact ? 16 : 48,
      } as never,
      userZoomingEnabled: !compact,
      userPanningEnabled: !compact,
      boxSelectionEnabled: false,
      autoungrabify: compact,
      pixelRatio: Math.min(typeof window !== "undefined" ? window.devicePixelRatio : 1, 2),
    });

    // background must match the validated surface for the palette to hold
    container.style.background = SURFACE;

    cy.on("tap", "node", (ev) => onSelectRef.current?.(ev.target.id()));
    cy.on("tap", (ev) => {
      if (ev.target === cy) onSelectRef.current?.(null);
    });

    // hover: spotlight the neighborhood
    if (!compact) {
      cy.on("mouseover", "node", (ev) => {
        const hood = ev.target.closedNeighborhood();
        cy.elements().not(hood).addClass("dimmed");
      });
      cy.on("mouseout", "node", () => cy.elements().removeClass("dimmed"));
    }

    cyRef.current = cy;
    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [data, compact]);

  // family visibility without relayout
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.edges().forEach((edge) => {
      const fam = edge.data("family") as EdgeFamilyKey;
      const show = !visibleFamilies || visibleFamilies.has(fam);
      edge.toggleClass("hidden-family", !show);
    });
    // hide nodes stranded with no visible edges (center always stays)
    cy.nodes().forEach((node) => {
      const visible =
        node.data("isCenter") === 1 ||
        node.connectedEdges().filter((e) => !e.hasClass("hidden-family")).length > 0;
      node.style("display", visible ? "element" : "none");
    });
  }, [visibleFamilies, data]);

  // selection highlight
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes().removeClass("selected");
    if (selectedNode) cy.getElementById(selectedNode).addClass("selected");
  }, [selectedNode, data]);

  // Outer div owns layout sizing; cytoscape mutates the inner div's inline
  // position (forcing `relative`), which would collapse an absolutely
  // positioned container to zero height.
  return (
    <div className={className}>
      <div ref={containerRef} className="h-full w-full" />
    </div>
  );
}
