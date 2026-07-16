/* Validated data-viz palette (dataviz six-checks, dark surface #0b0e14).
   Node fill encodes sentiment (diverging); edge hue encodes relationship kind
   (categorical, fixed order); direction is carried by the arrowhead. */

import type { EdgeType } from "./api";

export const SURFACE = "#0b0e14";

export const SENTIMENT = {
  pos: "#0ea371",
  neu: "#64748b",
  neg: "#e5484d",
  unknown: "#2a3140", // no scored articles, recedes toward the surface
} as const;

/** Diverging scale: interpolate mark color from a score in [-1, 1]. */
export function sentimentColor(score: number | null): string {
  if (score === null || Number.isNaN(score)) return SENTIMENT.unknown;
  const t = Math.max(-1, Math.min(1, score));
  const mix = (a: string, b: string, k: number) => {
    const pa = a.match(/\w\w/g)!.map((h) => parseInt(h, 16));
    const pb = b.match(/\w\w/g)!.map((h) => parseInt(h, 16));
    return `#${pa
      .map((v, i) => Math.round(v + (pb[i] - v) * k).toString(16).padStart(2, "0"))
      .join("")}`;
  };
  return t >= 0 ? mix(SENTIMENT.neu, SENTIMENT.pos, t) : mix(SENTIMENT.neu, SENTIMENT.neg, -t);
}

export function sentimentLabel(score: number | null): string {
  if (score === null) return "No recent signal";
  if (score >= 0.45) return "Strongly upbeat";
  if (score >= 0.15) return "Upbeat";
  if (score > -0.15) return "Mixed / neutral";
  if (score > -0.45) return "Downbeat";
  return "Strongly downbeat";
}

/** Edge families: hue = relationship kind; SUPPLIED_BY folds into supply
    (same relationship read backwards, the arrow carries direction). */
export const EDGE_FAMILIES = [
  { key: "supply", label: "Supply chain", color: "#3987e5", types: ["SUPPLIES_TO", "SUPPLIED_BY"] },
  { key: "compete", label: "Competitors", color: "#d95926", types: ["COMPETES_WITH"] },
  { key: "etf", label: "ETF co-holding", color: "#9085e9", types: ["CO_HOLDS_ETF"] },
  { key: "peer", label: "Sector peers", color: "#c98500", types: ["SECTOR_PEER"] },
] as const;

export type EdgeFamilyKey = (typeof EDGE_FAMILIES)[number]["key"];

export function edgeFamily(relType: EdgeType): (typeof EDGE_FAMILIES)[number] {
  return EDGE_FAMILIES.find((f) => (f.types as readonly string[]).includes(relType)) ?? EDGE_FAMILIES[0];
}
