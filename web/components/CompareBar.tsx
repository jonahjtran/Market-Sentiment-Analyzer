/* Paired comparison bar: graph (blue) vs flat (orange), direct-labeled.
   Colors are the validated edge-supply / edge-compete tokens; kept distinct in
   CVD. Graph always on top so the eye reads "ours vs baseline" consistently. */

const GRAPH = "var(--color-edge-supply)"; // #3987e5
const FLAT = "var(--color-edge-compete)"; // #d95926

export function CompareBar({
  label,
  graph,
  flat,
  max,
  format = (v: number) => `${Math.round(v * 100)}%`,
}: {
  label: string;
  graph: number;
  flat: number;
  max: number;
  format?: (v: number) => string;
}) {
  const pct = (v: number) => `${Math.max(0, Math.min(100, (v / max) * 100))}%`;
  return (
    <div className="py-4">
      <div className="mb-2.5 font-mono text-[0.72rem] uppercase tracking-[0.12em] text-ink-2">
        {label}
      </div>
      {[
        { who: "Graph", v: graph, color: GRAPH },
        { who: "Flat", v: flat, color: FLAT },
      ].map((r) => (
        <div key={r.who} className="mb-1.5 flex items-center gap-3 last:mb-0">
          <span className="w-11 shrink-0 font-mono text-[0.68rem] uppercase tracking-[0.1em] text-ink-3">
            {r.who}
          </span>
          <div className="relative h-6 flex-1">
            <div
              className="absolute inset-y-0 left-0 rounded-r-[4px] transition-[width] duration-700 ease-out"
              style={{ width: pct(r.v), background: r.color, minWidth: "2px" }}
            />
          </div>
          <span
            className="w-12 shrink-0 text-right font-mono text-[0.8rem] tabular-nums"
            style={{ color: r.who === "Graph" ? "var(--color-ink)" : "var(--color-ink-2)" }}
          >
            {format(r.v)}
          </span>
        </div>
      ))}
    </div>
  );
}
