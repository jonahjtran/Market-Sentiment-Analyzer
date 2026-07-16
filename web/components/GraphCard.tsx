"use client";

import Link from "next/link";
import type { GraphData } from "@/lib/api";
import { GraphCanvas } from "./GraphCanvas";
import { EDGE_FAMILIES, edgeFamily } from "@/lib/palette";

/* Inline evidence in the chat stream, set like an editorial figure:
   hairline top rule with a mono figure label, edge-to-edge canvas,
   legend as a quiet caption underneath. No box. */
export function GraphCard({ data }: { data: GraphData }) {
  const families = new Set(data.edges.map((e) => edgeFamily(e.rel_type).key));
  const legend = EDGE_FAMILIES.filter((f) => families.has(f.key));
  const label = data.center
    ? `fig · ${data.center} neighborhood, ${data.nodes.length} companies / ${data.edges.length} links`
    : `fig · sentiment scan, ${data.nodes.length} companies`;

  return (
    <figure className="anim-fade-in my-1">
      <div className="flex items-baseline justify-between gap-3 border-t border-line-strong pt-2">
        <figcaption className="truncate font-mono text-[0.68rem] uppercase tracking-[0.12em] text-ink-3">
          {label}
        </figcaption>
        {data.center && (
          <Link
            href={`/graph?ticker=${encodeURIComponent(data.center)}`}
            className="shrink-0 font-mono text-[0.68rem] uppercase tracking-[0.12em] text-brand transition-opacity hover:opacity-75"
          >
            explore →
          </Link>
        )}
      </div>
      {data.edges.length > 0 ? (
        <GraphCanvas data={data} compact className="mt-2 h-60 w-full" />
      ) : (
        <div className="flex h-20 items-center justify-center font-mono text-[0.72rem] text-ink-3">
          no relationship edges in this lookup
        </div>
      )}
      {legend.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-line pb-2 font-mono text-[0.65rem] uppercase tracking-[0.1em] text-ink-3">
          {legend.map((f) => (
            <span key={f.key} className="inline-flex items-center gap-1.5">
              <span className="h-px w-4" style={{ background: f.color }} />
              {f.label}
            </span>
          ))}
        </div>
      )}
    </figure>
  );
}
