"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Nav } from "./Nav";
import { CompareBar } from "./CompareBar";
import { fetchEval, type EvalReport, type EvalQuestion } from "@/lib/api";

export function Scoreboard() {
  const [report, setReport] = useState<EvalReport | null | undefined>(undefined);

  useEffect(() => {
    fetchEval().then(setReport).catch(() => setReport(null));
  }, []);

  if (report === undefined) {
    return (
      <Shell>
        <p className="font-mono text-[0.8rem] uppercase tracking-[0.14em] text-ink-3">
          Loading benchmark…
        </p>
      </Shell>
    );
  }
  if (report === null) {
    return (
      <Shell>
        <p className="max-w-md text-[0.95rem] leading-relaxed text-ink-2">
          No benchmark results yet. Run{" "}
          <code className="rounded bg-surface-3 px-1.5 py-0.5 font-mono text-[0.8rem]">
            python -m src.eval.run_eval
          </code>{" "}
          to generate them.
        </p>
      </Shell>
    );
  }

  const s = report.summary;
  const winPct = Math.round(s.judge_win_rate_graph * 100);

  // Composite benchmark score: the mean of the five measured signals (entity
  // recall, retrieval coverage, and the three judge dimensions normalized to
  // 0..1). The headline multiplier is graph's composite over flat's, so it is a
  // transparent roll-up of exactly the metrics shown below, not a cherry-pick.
  const composite = (side: "graph" | "flat") => {
    const j = s.judge_scores[side];
    return (
      (s.entity_recall[side] +
        s.retrieval_coverage[side] +
        j.entity_coverage / 5 +
        j.correctness / 5 +
        j.reasoning_depth / 5) /
      5
    );
  };
  const multiplier =
    composite("flat") > 0 ? composite("graph") / composite("flat") : null;
  const multLabel = multiplier ? `${multiplier.toFixed(1)}×` : "n/a";

  return (
    <Shell>
      {/* ── headline ── */}
      <header className="max-w-3xl">
        <p className="font-mono text-[0.7rem] uppercase tracking-[0.16em] text-ink-3">
          Benchmark · graph RAG vs flat RAG · {s.n} multi-hop questions
        </p>
        <h1 className="mt-5 font-display text-[clamp(2.4rem,5.5vw,4rem)] leading-[1.02] tracking-tight">
          The graph model performs{" "}
          <em className="text-brand">{multLabel} better</em>
          <br className="hidden sm:block" /> across the benchmark.
        </h1>
        <p className="mt-6 max-w-xl text-[1.02rem] leading-relaxed text-ink-2">
          Same questions, same reasoning model, only the retrieval layer differs.
          Across five measures of how well each system surfaces and reasons about
          the right related companies, the graph model scores{" "}
          <span className="text-pos-text">{multLabel} the flat baseline</span>,
          because it traverses relationships instead of matching keywords.
        </p>
      </header>

      {/* ── three headline stats ── */}
      <section className="mt-16 grid gap-px overflow-hidden border-y border-line sm:grid-cols-3">
        <Stat
          label="Overall benchmark score"
          value={multLabel}
          sub="graph vs flat, five measures combined"
          accent
        />
        <Stat
          label="Entity recall, graph"
          value={`${Math.round(s.entity_recall.graph * 100)}%`}
          sub={`flat baseline ${Math.round(s.entity_recall.flat * 100)}%`}
        />
        <Stat
          label="Judge win rate"
          value={`${winPct}%`}
          sub={`${s.wins.graph} wins, ${s.wins.flat} losses, ${s.wins.tie} ties`}
        />
      </section>

      {/* ── charts ── */}
      <section className="mt-16 grid gap-14 md:grid-cols-2 md:gap-20">
        <div>
          <h2 className="font-display text-[1.5rem] tracking-tight">
            Did it surface the right companies?
          </h2>
          <p className="mt-2 max-w-sm text-[0.88rem] leading-relaxed text-ink-2">
            Answer-level entity recall, plus the retrieval coverage underneath it
            that explains the gap. Flat search only reaches names textually near
            the query.
          </p>
          <div className="mt-6 divide-y divide-line border-t border-line">
            <CompareBar
              label="Entity recall (in the answer)"
              graph={s.entity_recall.graph}
              flat={s.entity_recall.flat}
              max={1}
            />
            <CompareBar
              label="Retrieval coverage (reached at all)"
              graph={s.retrieval_coverage.graph}
              flat={s.retrieval_coverage.flat}
              max={1}
            />
          </div>
        </div>

        <div>
          <h2 className="font-display text-[1.5rem] tracking-tight">
            Was the reasoning any better?
          </h2>
          <p className="mt-2 max-w-sm text-[0.88rem] leading-relaxed text-ink-2">
            A blinded LLM judge scored each answer 1 to 5. Positions were randomized
            per question so order can&apos;t bias the verdict.
          </p>
          <div className="mt-6 divide-y divide-line border-t border-line">
            <CompareBar
              label="Entity coverage"
              graph={s.judge_scores.graph.entity_coverage}
              flat={s.judge_scores.flat.entity_coverage}
              max={5}
              format={(v) => v.toFixed(1)}
            />
            <CompareBar
              label="Correctness"
              graph={s.judge_scores.graph.correctness}
              flat={s.judge_scores.flat.correctness}
              max={5}
              format={(v) => v.toFixed(1)}
            />
            <CompareBar
              label="Reasoning depth"
              graph={s.judge_scores.graph.reasoning_depth}
              flat={s.judge_scores.flat.reasoning_depth}
              max={5}
              format={(v) => v.toFixed(1)}
            />
          </div>
        </div>
      </section>

      {/* ── legend ── */}
      <div className="mt-10 flex items-center gap-6 font-mono text-[0.68rem] uppercase tracking-[0.12em] text-ink-3">
        <span className="inline-flex items-center gap-2">
          <span className="h-[3px] w-5 rounded-full bg-edge-supply" />
          Graph RAG (ours)
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="h-[3px] w-5 rounded-full bg-edge-compete" />
          Flat RAG (baseline)
        </span>
      </div>

      {/* ── per-question breakdown ── */}
      <section className="mt-20">
        <h2 className="font-display text-[1.6rem] tracking-tight">Every question</h2>
        <p className="mt-2 max-w-lg text-[0.88rem] leading-relaxed text-ink-2">
          Each question names only the trigger company; the expected neighbors are
          never mentioned in the prompt. Recall is over those expected neighbors.
        </p>
        <div className="mt-8 flex flex-col">
          {report.questions.map((q) => (
            <QuestionRow key={q.id} q={q} />
          ))}
        </div>
      </section>

      {/* ── methodology ── */}
      <section className="mt-20 border-t border-line pt-8">
        <p className="font-mono text-[0.7rem] uppercase tracking-[0.16em] text-ink-3">
          How this is scored
        </p>
        <div className="mt-5 grid gap-8 text-[0.88rem] leading-relaxed text-ink-2 md:grid-cols-3">
          <p>
            <strong className="text-ink">Entity recall.</strong> Objective and
            market-data-free: of the genuinely-related companies each question
            targets, how many does the answer name? Same alias-matching for both
            systems.
          </p>
          <p>
            <strong className="text-ink">Blinded LLM judge.</strong> A neutral
            model scores both answers 1 to 5 on coverage, correctness, and reasoning
            depth, with the two answers anonymized and their order randomized.
          </p>
          <p>
            <strong className="text-ink">Fair targets.</strong> Expected
            neighbors are real-world-correct relationships that also exist in the
            graph, so the test measures retrieval, not data gaps. Both systems
            share the identical reasoning model.
          </p>
        </div>
        <p className="mt-8 font-mono text-[0.66rem] uppercase tracking-[0.1em] text-ink-3">
          Generated {report.generated_at.slice(0, 16).replace("T", " ")} UTC · reasoning{" "}
          {report.models.reason} · judge {report.models.judge} · not investment advice
        </p>
      </section>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex-1">
      <Nav />
      <div className="mx-auto max-w-5xl px-6 pb-28 pt-32">{children}</div>
    </main>
  );
}

function Stat({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub: string;
  accent?: boolean;
}) {
  return (
    <div className="bg-surface-1 px-6 py-8">
      <div className="font-mono text-[0.66rem] uppercase tracking-[0.14em] text-ink-3">
        {label}
      </div>
      <div
        className={`mt-3 font-display text-[3rem] leading-none tracking-tight tabular-nums ${
          accent ? "text-brand" : "text-ink"
        }`}
      >
        {value}
      </div>
      <div className="mt-2 text-[0.8rem] text-ink-2">{sub}</div>
    </div>
  );
}

function QuestionRow({ q }: { q: EvalQuestion }) {
  const badge =
    q.winner === "graph"
      ? { text: "graph", cls: "text-edge-supply border-edge-supply/40 bg-edge-supply/10" }
      : q.winner === "flat"
        ? { text: "flat", cls: "text-edge-compete border-edge-compete/40 bg-edge-compete/10" }
        : { text: "tie", cls: "text-ink-3 border-line-strong bg-surface-2" };
  return (
    <details className="group border-t border-line last:border-b">
      <summary className="flex cursor-pointer list-none items-center gap-4 py-4 transition-colors hover:bg-surface-2/40">
        <span className="w-12 shrink-0 font-mono text-[0.66rem] uppercase tracking-[0.1em] text-ink-3">
          {q.trigger}
        </span>
        <span className="flex-1 text-[0.92rem] leading-snug text-ink group-open:text-brand">
          {q.question}
        </span>
        <span className="hidden shrink-0 items-center gap-3 font-mono text-[0.72rem] tabular-nums text-ink-2 sm:flex">
          <span title="graph entity recall" className="text-edge-supply">
            {Math.round(q.graph.recall.recall * 100)}%
          </span>
          <span className="text-ink-3">/</span>
          <span title="flat entity recall" className="text-edge-compete">
            {Math.round(q.flat.recall.recall * 100)}%
          </span>
        </span>
        <span
          className={`w-14 shrink-0 rounded-full border px-2 py-0.5 text-center font-mono text-[0.62rem] uppercase tracking-[0.08em] ${badge.cls}`}
        >
          {badge.text}
        </span>
      </summary>
      <div className="grid gap-5 pb-6 pl-16 pr-4 pt-1 text-[0.85rem] leading-relaxed md:grid-cols-2">
        <div>
          <p className="mb-2 font-mono text-[0.64rem] uppercase tracking-[0.12em] text-edge-supply">
            Graph, recall {Math.round(q.graph.recall.recall * 100)}%
          </p>
          <p className="text-ink-2">
            found{" "}
            <span className="text-pos-text">{q.graph.recall.found.join(", ") || ", "}</span>
            {q.graph.recall.missed.length > 0 && (
              <>
                {" · missed "}
                <span className="text-neg-text">{q.graph.recall.missed.join(", ")}</span>
              </>
            )}
          </p>
        </div>
        <div>
          <p className="mb-2 font-mono text-[0.64rem] uppercase tracking-[0.12em] text-edge-compete">
            Flat, recall {Math.round(q.flat.recall.recall * 100)}%
          </p>
          <p className="text-ink-2">
            found{" "}
            <span className="text-pos-text">{q.flat.recall.found.join(", ") || ", "}</span>
            {q.flat.recall.missed.length > 0 && (
              <>
                {" · missed "}
                <span className="text-neg-text">{q.flat.recall.missed.join(", ")}</span>
              </>
            )}
          </p>
        </div>
        <p className="text-ink-3 md:col-span-2">
          <span className="font-mono text-[0.64rem] uppercase tracking-[0.12em]">Judge:</span>{" "}
          {q.rationale}
        </p>
      </div>
    </details>
  );
}
