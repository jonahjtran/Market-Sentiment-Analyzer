"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Wordmark } from "./Wordmark";
import { GraphCanvas } from "./GraphCanvas";
import { fetchEntities, fetchGraph, type GraphResponse } from "@/lib/api";
import {
  EDGE_FAMILIES,
  sentimentColor,
  sentimentLabel,
  type EdgeFamilyKey,
} from "@/lib/palette";

const ALL_FAMILIES = new Set<EdgeFamilyKey>(EDGE_FAMILIES.map((f) => f.key));

export function GraphExplorer() {
  const params = useSearchParams();
  const initialTicker = params.get("ticker") ?? "NVDA";

  const [query, setQuery] = useState(initialTicker);
  const [matches, setMatches] = useState<string[]>([]);
  const [showMatches, setShowMatches] = useState(false);
  const [hops, setHops] = useState(2);
  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [families, setFamilies] = useState<Set<EdgeFamilyKey>>(new Set(ALL_FAMILIES));
  const [selected, setSelected] = useState<string | null>(null);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async (ticker: string, h: number) => {
    setLoading(true);
    setError(null);
    setSelected(null);
    try {
      setGraph(await fetchGraph(ticker, h));
      setQuery(ticker);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load the graph.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(initialTicker, 2);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // autocomplete
  const onQueryChange = (v: string) => {
    setQuery(v);
    if (debounce.current) clearTimeout(debounce.current);
    if (!v.trim()) {
      setMatches([]);
      return;
    }
    debounce.current = setTimeout(async () => {
      setMatches(await fetchEntities(v));
      setShowMatches(true);
    }, 180);
  };

  const toggleFamily = (key: EdgeFamilyKey) =>
    setFamilies((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        if (next.size > 1) next.delete(key); // never allow zero families
      } else {
        next.add(key);
      }
      return next;
    });

  const selectedNode = graph?.nodes.find((n) => n.id === selected) ?? null;
  const selectedArticles = (selected && graph?.articles[selected]) || [];
  const selectedEdges =
    (selected &&
      graph?.edges.filter((e) => e.source === selected || e.target === selected)) ||
    [];

  return (
    <div className="relative h-svh overflow-hidden bg-surface-1">
      {graph && (
        <GraphCanvas
          data={graph}
          visibleFamilies={families}
          selectedNode={selected}
          onSelectNode={setSelected}
          className="absolute inset-0"
        />
      )}

      {/* loading / error states */}
      {loading && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-surface-1/60 backdrop-blur-sm">
          <div className="flex items-center gap-3 font-mono text-[0.75rem] uppercase tracking-[0.14em] text-ink-2">
            <span className="h-3.5 w-3.5 animate-spin rounded-full border border-brand/30 border-t-brand" />
            Traversing the graph
          </div>
        </div>
      )}
      {error && !loading && (
        <div className="absolute inset-x-0 top-24 z-20 mx-auto w-fit rounded-xl border border-neg/40 bg-neg/10 px-5 py-3 text-sm text-neg-text">
          {error}
        </div>
      )}

      {/* ── top bar: brand + search + hops ── */}
      <div className="absolute inset-x-0 top-0 z-30 flex flex-wrap items-start justify-between gap-3 p-4">
        <div className="flex flex-wrap items-start gap-3">
          <Link
            href="/"
            className="flex h-10 items-center px-1 transition-opacity hover:opacity-75"
          >
            <Wordmark size={17} />
          </Link>

          <div className="relative">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                setShowMatches(false);
                if (query.trim()) load(query.trim(), hops);
              }}
              className="flex h-10 items-center gap-1 border-b border-line-strong bg-surface-1/60 pl-2 pr-1 backdrop-blur-md focus-within:border-brand/60"
            >
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" className="text-ink-3">
                <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.5" />
                <path d="m10.5 10.5 3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
              <input
                value={query}
                onChange={(e) => onQueryChange(e.target.value)}
                onFocus={() => matches.length && setShowMatches(true)}
                onBlur={() => setTimeout(() => setShowMatches(false), 150)}
                placeholder="Search a company…"
                className="w-44 bg-transparent px-2 text-sm placeholder:text-ink-3 focus:outline-none sm:w-56"
                aria-label="Search a company"
              />
              <select
                value={hops}
                onChange={(e) => {
                  const h = Number(e.target.value);
                  setHops(h);
                  if (query.trim()) load(query.trim(), h);
                }}
                aria-label="Traversal depth"
                className="h-7 border-0 bg-transparent px-1 font-mono text-[0.7rem] text-ink-2 focus:outline-none"
              >
                <option value={1}>1 hop</option>
                <option value={2}>2 hops</option>
                <option value={3}>3 hops</option>
              </select>
              <button
                type="submit"
                className="h-7 rounded-md bg-ink px-3 font-mono text-[0.7rem] font-semibold uppercase tracking-[0.08em] text-surface-1 transition-transform hover:scale-[1.04]"
              >
                Map
              </button>
            </form>
            {showMatches && matches.length > 0 && (
              <ul className="absolute left-0 right-0 top-11 z-40 overflow-hidden rounded-md border border-line bg-surface-2/95 backdrop-blur-xl">
                {matches.slice(0, 8).map((m) => (
                  <li key={m}>
                    <button
                      onMouseDown={() => {
                        setShowMatches(false);
                        load(m, hops);
                      }}
                      className="w-full px-3.5 py-2 text-left text-sm text-ink-2 transition-colors hover:bg-surface-3 hover:text-ink"
                    >
                      {m}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <Link
          href={graph?.center ? `/chat?q=${encodeURIComponent(`What's the latest ripple effect around ${graph.center}?`)}` : "/chat"}
          className="group flex h-10 items-center gap-1.5 text-[0.85rem] text-ink-2 underline decoration-line-strong underline-offset-[6px] transition-colors hover:text-ink hover:decoration-brand"
        >
          Ask about this graph
          <span className="text-brand">→</span>
        </Link>
      </div>

      {/* ── legend: edge family toggles + sentiment scale ── */}
      <div className="absolute bottom-5 left-5 z-30 flex flex-col gap-2.5 border-l border-line-strong bg-surface-1/55 py-1 pl-4 pr-2 backdrop-blur-md">
        <span className="text-[0.68rem] font-medium uppercase tracking-[0.14em] text-ink-3">
          Relationships
        </span>
        <div className="flex flex-col gap-1.5">
          {EDGE_FAMILIES.map((f) => {
            const on = families.has(f.key);
            return (
              <button
                key={f.key}
                onClick={() => toggleFamily(f.key)}
                aria-pressed={on}
                className={`flex items-center gap-2.5 rounded-lg px-2 py-1 text-left text-[0.8rem] transition-all ${
                  on ? "text-ink" : "text-ink-3 opacity-50"
                } hover:bg-surface-2`}
              >
                <span
                  className="h-[3px] w-5 rounded-full transition-opacity"
                  style={{ background: f.color, opacity: on ? 1 : 0.35 }}
                />
                {f.label}
              </button>
            );
          })}
        </div>
        <div className="mt-1 border-t border-line pt-2.5">
          <span className="text-[0.68rem] font-medium uppercase tracking-[0.14em] text-ink-3">
            Node sentiment
          </span>
          <div className="mt-2 flex items-center gap-2 text-[0.7rem] text-ink-3">
            <span>Down</span>
            <span
              className="h-2 w-24 rounded-full"
              style={{
                background: `linear-gradient(90deg, ${sentimentColor(-1)}, ${sentimentColor(0)}, ${sentimentColor(1)})`,
              }}
            />
            <span>Up</span>
          </div>
        </div>
      </div>

      {/* ── detail panel ── */}
      <aside
        className={`slim-scroll absolute bottom-0 right-0 top-0 z-30 w-[21rem] overflow-y-auto border-l border-line bg-surface-1/90 backdrop-blur-2xl transition-all duration-300 ${
          selectedNode ? "translate-x-0 opacity-100" : "pointer-events-none translate-x-6 opacity-0"
        }`}
        aria-hidden={!selectedNode}
      >
        {selectedNode && (
          <div className="flex flex-col gap-4 p-5">
            <div className="flex items-start justify-between gap-2">
              <div>
                <h2 className="font-mono text-lg font-semibold tracking-tight">{selectedNode.id}</h2>
                <span
                  className="mt-1.5 inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[0.72rem] font-medium"
                  style={{
                    background: `${sentimentColor(selectedNode.sentiment)}22`,
                    color:
                      selectedNode.sentiment === null
                        ? "var(--text-muted)"
                        : selectedNode.sentiment >= 0.15
                          ? "var(--pos-text)"
                          : selectedNode.sentiment <= -0.15
                            ? "var(--neg-text)"
                            : "var(--text-secondary)",
                  }}
                >
                  <span
                    className="h-1.5 w-1.5 rounded-full"
                    style={{ background: sentimentColor(selectedNode.sentiment) }}
                  />
                  {sentimentLabel(selectedNode.sentiment)}
                </span>
              </div>
              <button
                onClick={() => setSelected(null)}
                aria-label="Close details"
                className="rounded-lg p-1.5 text-ink-3 transition-colors hover:bg-surface-2 hover:text-ink"
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="m3.5 3.5 7 7m0-7-7 7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </button>
            </div>

            {!selectedNode.is_center && (
              <button
                onClick={() => load(selectedNode.id, hops)}
                className="w-fit text-[0.85rem] text-ink-2 underline decoration-line-strong underline-offset-[5px] transition-colors hover:text-brand hover:decoration-brand"
              >
                Re-center graph here
              </button>
            )}

            <section>
              <h3 className="mb-2 text-[0.68rem] font-medium uppercase tracking-[0.14em] text-ink-3">
                Connections · {selectedEdges.length}
              </h3>
              <ul className="flex flex-col gap-1.5">
                {selectedEdges.slice(0, 10).map((e, i) => {
                  const other = e.source === selected ? e.target : e.source;
                  const fam = EDGE_FAMILIES.find((f) =>
                    (f.types as readonly string[]).includes(e.rel_type),
                  );
                  return (
                    <li key={i} className="flex items-center gap-2 text-[0.82rem] text-ink-2">
                      <span className="h-[2px] w-3.5 shrink-0 rounded-full" style={{ background: fam?.color }} />
                      <button
                        onClick={() => setSelected(other)}
                        className="truncate font-medium text-ink transition-colors hover:text-brand"
                      >
                        {other}
                      </button>
                      <span className="ml-auto shrink-0 text-[0.68rem] text-ink-3">
                        {e.rel_type.replaceAll("_", " ").toLowerCase()}
                      </span>
                    </li>
                  );
                })}
                {selectedEdges.length > 10 && (
                  <li className="text-[0.75rem] text-ink-3">+ {selectedEdges.length - 10} more</li>
                )}
              </ul>
            </section>

            <section>
              <h3 className="mb-2 text-[0.68rem] font-medium uppercase tracking-[0.14em] text-ink-3">
                Recent signal · {selectedArticles.length}
              </h3>
              {selectedArticles.length === 0 ? (
                <p className="text-[0.82rem] text-ink-3">No scored articles for this company yet.</p>
              ) : (
                <ul className="flex flex-col gap-3">
                  {selectedArticles.map((a, i) => (
                    <li key={i} className="border-t border-line pt-3">
                      <div className="mb-1.5 flex items-center gap-2">
                        <span className="font-mono text-[0.62rem] uppercase tracking-[0.12em] text-ink-3">
                          {a.doc_type}
                        </span>
                        {a.score !== null && (
                          <span
                            className="h-1.5 w-1.5 rounded-full"
                            style={{ background: sentimentColor(a.score) }}
                            title={sentimentLabel(a.score)}
                          />
                        )}
                      </div>
                      <p className="text-[0.8rem] leading-relaxed text-ink-2">
                        {a.summary ?? "Filed document, no sentiment summary."}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        )}
      </aside>

      {/* footer stats strip */}
      {graph && (
        <div className="absolute bottom-5 left-1/2 z-20 hidden -translate-x-1/2 font-mono text-[0.68rem] uppercase tracking-[0.14em] text-ink-3 md:block">
          {graph.center} · {graph.nodes.length} companies · {graph.edges.length} relationships · {hops} hop{hops > 1 ? "s" : ""}
        </div>
      )}
    </div>
  );
}
