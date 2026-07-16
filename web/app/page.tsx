import Link from "next/link";
import { Nav } from "@/components/Nav";
import { HeroGraph } from "@/components/HeroGraph";
import { CascadeMark } from "@/components/Wordmark";
import { ExamplePrompts } from "@/components/ExamplePrompts";
import { EDGE_FAMILIES } from "@/lib/palette";

const STEPS = [
  {
    n: "01",
    title: "Relationships, on the record",
    body: "Supplier, customer, and competitor ties mined from SEC 10-K filings and fund holdings, the relationships companies are legally required to admit.",
  },
  {
    n: "02",
    title: "Sentiment scored at the source",
    body: "Every earnings release and headline is read and scored the moment it lands, then pinned to the company it's about.",
  },
  {
    n: "03",
    title: "An analyst that follows the chain",
    body: "Ask a question and the model walks the actual graph, supplier to customer, rival to rival, and reasons about who's exposed, in which direction, and how hard.",
  },
];

export default function Landing() {
  return (
    <main className="flex-1">
      <Nav />

      {/* ── Hero, asymmetric editorial: type owns the left, graph the right ── */}
      <section className="relative flex min-h-svh items-center overflow-hidden">
        <div className="aurora absolute inset-0" aria-hidden />
        <HeroGraph className="absolute inset-0 h-full w-full" />
        {/* left scrim so the type sits on quiet ground */}
        <div
          className="absolute inset-0 bg-[linear-gradient(100deg,rgba(7,9,13,0.92)_0%,rgba(7,9,13,0.72)_34%,rgba(7,9,13,0.18)_60%,transparent_78%)]"
          aria-hidden
        />

        <div className="relative z-10 mx-auto w-full max-w-6xl px-6">
          <div className="max-w-[38rem]">
            {/* live-wire readout, not a marketing chip */}
            <p className="anim-fade-up mb-7 font-mono text-[0.72rem] tracking-[0.06em] text-ink-3">
              <span className="text-pos-text">NVDA ▲</span>&nbsp; earnings&nbsp;&nbsp;⟶&nbsp;&nbsp;TSM · AMD ·
              SOXX&nbsp;&nbsp;⟶&nbsp;&nbsp;<span className="text-ink-2">2nd-order: ASML, DLR…</span>
            </p>

            <h1 className="anim-fade-up delay-1 font-display text-[clamp(3.2rem,8vw,6rem)] leading-[0.98] tracking-tight">
              Sentiment
              <br />
              moves <em className="text-brand">in chains.</em>
            </h1>

            {/* accent rule, the one non-text ornament */}
            <div className="anim-fade-up delay-2 mt-8 h-px w-24 bg-gradient-to-r from-brand to-transparent" aria-hidden />

            <p className="anim-fade-up delay-2 mt-7 max-w-[26rem] text-pretty text-[1.02rem] leading-relaxed text-ink-2">
              One company's news reprices its foundries, its rivals, and the funds
              that hold them all. Cascade maps those chains from real disclosures, 
              and reasons through them, hop by hop.
            </p>

            <div className="anim-fade-up delay-3 mt-10 flex flex-wrap items-center gap-7">
              <Link
                href="/chat"
                className="rounded-lg bg-ink px-6 py-3 text-[0.95rem] font-semibold text-surface-1 transition-transform hover:scale-[1.02] active:scale-100"
              >
                Ask the analyst
              </Link>
              <Link
                href="/graph"
                className="group text-[0.95rem] text-ink-2 underline decoration-line-strong underline-offset-[6px] transition-colors hover:text-ink hover:decoration-brand"
              >
                Explore the graph
                <span className="ml-1.5 inline-block text-brand transition-transform group-hover:translate-x-1">→</span>
              </Link>
            </div>

            {/* edge taxonomy as a quiet marginal caption, not a band */}
            <div className="anim-fade-up delay-4 mt-16 flex flex-wrap items-center gap-x-6 gap-y-2 font-mono text-[0.68rem] uppercase tracking-[0.12em] text-ink-3">
              {EDGE_FAMILIES.map((f) => (
                <span key={f.key} className="inline-flex items-center gap-2">
                  <span className="h-px w-5" style={{ background: f.color }} />
                  {f.label}
                </span>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── How it works, numbered hairline columns, no cards ── */}
      <section className="mx-auto max-w-6xl px-6 py-28">
        <div className="grid gap-14 md:grid-cols-[minmax(0,20rem)_1fr] md:gap-20">
          <div>
            <p className="font-mono text-[0.7rem] uppercase tracking-[0.16em] text-ink-3">
              How it works
            </p>
            <h2 className="mt-4 font-display text-[clamp(2rem,4vw,2.8rem)] leading-[1.05] tracking-tight">
              From filings
              <br />
              to <em className="text-brand">foresight.</em>
            </h2>
            <p className="mt-5 max-w-[20rem] text-[0.92rem] leading-relaxed text-ink-2">
              No black box: every answer is grounded in relationships companies
              disclosed and news that actually printed.
            </p>
          </div>

          <div className="grid gap-12 sm:grid-cols-3 sm:gap-8">
            {STEPS.map((s) => (
              <div key={s.n} className="group">
                <div className="flex items-baseline justify-between border-t border-line pt-4 transition-colors group-hover:border-brand/60">
                  <span className="font-mono text-[0.7rem] tracking-[0.16em] text-ink-3">{s.n}</span>
                </div>
                <h3 className="mt-5 text-[1rem] font-semibold leading-snug">{s.title}</h3>
                <p className="mt-3 text-[0.88rem] leading-relaxed text-ink-2">{s.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Example prompts, an index, not buttons ── */}
      <section className="mx-auto max-w-6xl px-6 pb-32">
        <div className="grid gap-10 md:grid-cols-[minmax(0,20rem)_1fr] md:gap-20">
          <div>
            <p className="font-mono text-[0.7rem] uppercase tracking-[0.16em] text-ink-3">
              Try asking
            </p>
            <h2 className="mt-4 font-display text-[clamp(2rem,4vw,2.8rem)] leading-[1.05] tracking-tight">
              Questions that
              <br />
              <em className="text-brand-2">cross companies.</em>
            </h2>
            <p className="mt-5 max-w-[20rem] text-[0.92rem] leading-relaxed text-ink-2">
              Where keyword search stops at one ticker, the graph keeps going.
            </p>
          </div>
          <ExamplePrompts />
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-8 text-[0.78rem] text-ink-3">
          <span className="inline-flex items-center gap-2">
            <CascadeMark size={15} />
            Cascade, market sentiment propagation graph
          </span>
          <span className="font-mono text-[0.68rem] uppercase tracking-[0.1em]">
            SEC EDGAR · ETF holdings · market news, research, not advice
          </span>
        </div>
      </footer>
    </main>
  );
}
