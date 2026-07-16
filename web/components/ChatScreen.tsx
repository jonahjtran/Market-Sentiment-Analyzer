"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import ReactMarkdown from "react-markdown";
import { Wordmark } from "./Wordmark";
import { GraphCard } from "./GraphCard";
import {
  streamChat,
  fetchExamples,
  type GraphData,
  type HistoryTurn,
} from "@/lib/api";

interface AssistantMsg {
  role: "assistant";
  status: string | null;
  graphs: GraphData[];
  text: string;
  streaming: boolean;
  error?: string;
}
interface UserMsg {
  role: "user";
  text: string;
}
type Msg = UserMsg | AssistantMsg;

const FALLBACK_PROMPTS = [
  "How does NVDA's earnings affect AMD, TSMC, and data center REITs?",
  "AMD just reported strong data center growth. What does that mean for NVDA and Intel?",
  "What's trending down in semiconductors right now?",
];

export function ChatScreen() {
  const params = useSearchParams();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>(FALLBACK_PROMPTS);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const autoSent = useRef(false);

  useEffect(() => {
    fetchExamples().then((ex) => ex.length && setSuggestions(ex)).catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const send = useCallback(
    async (question: string) => {
      const q = question.trim();
      if (!q || busy) return;
      setBusy(true);
      setInput("");

      // history = completed turns only, as plain text (per API contract)
      const history: HistoryTurn[] = [];
      for (const m of messages) {
        if (m.role === "user") history.push({ role: "user", content: m.text });
        else if (m.text && !m.error) history.push({ role: "assistant", content: m.text });
      }

      setMessages((prev) => [
        ...prev,
        { role: "user", text: q },
        { role: "assistant", status: "Thinking…", graphs: [], text: "", streaming: true },
      ]);

      const patchLast = (fn: (m: AssistantMsg) => AssistantMsg) =>
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last?.role === "assistant") next[next.length - 1] = fn(last);
          return next;
        });

      try {
        await streamChat(q, history, (ev) => {
          if (ev.type === "status") {
            patchLast((m) => ({ ...m, status: ev.message }));
          } else if (ev.type === "graph") {
            patchLast((m) => ({ ...m, status: null, graphs: [...m.graphs, ev.data] }));
          } else if (ev.type === "token") {
            patchLast((m) => ({ ...m, status: null, text: m.text + ev.text }));
          } else if (ev.type === "done") {
            patchLast((m) => ({ ...m, status: null, text: ev.answer, streaming: false }));
          } else if (ev.type === "error") {
            patchLast((m) => ({ ...m, status: null, streaming: false, error: ev.message }));
          }
        });
        // stream closed without a done frame, settle whatever we have
        patchLast((m) => (m.streaming ? { ...m, streaming: false } : m));
      } catch (err) {
        patchLast((m) => ({
          ...m,
          status: null,
          streaming: false,
          error: err instanceof Error ? err.message : "The analyst service is unreachable.",
        }));
      } finally {
        setBusy(false);
        textareaRef.current?.focus();
      }
    },
    [busy, messages],
  );

  // auto-send ?q= from the landing page
  useEffect(() => {
    const q = params.get("q");
    if (q && !autoSent.current) {
      autoSent.current = true;
      send(q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  const empty = messages.length === 0;

  return (
    <div className="flex h-svh flex-col">
      {/* slim header */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-line px-5">
        <Link href="/" className="transition-opacity hover:opacity-80">
          <Wordmark size={18} />
        </Link>
        <div className="flex items-center gap-1 text-sm">
          <button
            onClick={() => setMessages([])}
            className="rounded-lg px-3 py-1.5 text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink"
          >
            New thread
          </button>
          <Link
            href="/graph"
            className="rounded-lg px-3 py-1.5 text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink"
          >
            Graph →
          </Link>
        </div>
      </header>

      {/* conversation */}
      <div className="slim-scroll flex-1 overflow-y-auto">
        <div className="mx-auto max-w-2xl px-5 pb-40 pt-8">
          {empty ? (
            <div className="flex min-h-[60svh] flex-col justify-center">
              <p className="anim-fade-up font-mono text-[0.7rem] uppercase tracking-[0.16em] text-ink-3">
                The analyst
              </p>
              <h1 className="anim-fade-up delay-1 mt-4 font-display text-[clamp(2.2rem,5vw,3.1rem)] leading-[1.04] tracking-tight">
                What's the <em className="text-brand">ripple effect?</em>
              </h1>
              <p className="anim-fade-up delay-1 mt-4 max-w-md text-[0.95rem] leading-relaxed text-ink-2">
                Ask how one company's news travels through its suppliers, rivals,
                and the funds that hold them.
              </p>
              <ul className="anim-fade-up delay-2 mt-10 flex flex-col">
                {suggestions.map((s, i) => (
                  <li key={s} className="border-t border-line last:border-b">
                    <button
                      onClick={() => send(s)}
                      className="group flex w-full items-baseline gap-4 py-4 text-left transition-colors hover:bg-surface-2/40"
                    >
                      <span className="w-6 shrink-0 font-mono text-[0.68rem] tracking-[0.16em] text-ink-3 transition-colors group-hover:text-brand">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <span className="flex-1 text-[0.92rem] leading-snug text-ink-2 transition-colors group-hover:text-ink">
                        {s}
                      </span>
                      <span className="shrink-0 text-brand opacity-0 transition-all group-hover:translate-x-1 group-hover:opacity-100">
                        →
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <div className="flex flex-col gap-7">
              {messages.map((m, i) =>
                m.role === "user" ? (
                  <div key={i} className="flex justify-end">
                    <div className="max-w-[85%] border-r-2 border-brand/70 bg-surface-2/70 px-4 py-2.5 text-[0.9375rem] leading-relaxed rounded-l-lg">
                      {m.text}
                    </div>
                  </div>
                ) : (
                  <div key={i} className="flex flex-col gap-3">
                    {m.status && (
                      <div className="shimmer-text text-[0.85rem]" role="status">
                        {m.status}
                      </div>
                    )}
                    {m.graphs.map((g, gi) => (
                      <GraphCard key={gi} data={g} />
                    ))}
                    {m.text && (
                      <div className={`prose-chat ${m.streaming ? "stream-caret" : ""}`}>
                        <ReactMarkdown>{m.text}</ReactMarkdown>
                      </div>
                    )}
                    {m.error && (
                      <div className="rounded-xl border border-neg/40 bg-neg/10 px-4 py-3 text-[0.875rem] text-neg-text">
                        {m.error}
                      </div>
                    )}
                  </div>
                ),
              )}
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* composer */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-surface-1 via-surface-1/90 to-transparent pb-5 pt-10">
        <div className="pointer-events-auto mx-auto max-w-2xl px-5">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
            className="flex items-end gap-2 border-t border-line-strong bg-surface-1/95 px-1 pt-3 pb-1 transition-colors focus-within:border-brand/60"
          >
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                e.target.style.height = "auto";
                e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send(input);
                }
              }}
              rows={1}
              placeholder="Ask about a company, a sector, or what's moving…"
              className="slim-scroll max-h-40 flex-1 resize-none bg-transparent px-3 py-2 text-[0.9375rem] leading-relaxed placeholder:text-ink-3 focus:outline-none"
              disabled={busy}
              autoFocus
            />
            <button
              type="submit"
              disabled={busy || !input.trim()}
              aria-label="Send"
              className="mb-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-ink text-surface-1 transition-all enabled:hover:scale-105 disabled:opacity-30"
            >
              {busy ? (
                <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-surface-1/30 border-t-surface-1" />
              ) : (
                <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
                  <path d="M8 13V3m0 0L3.5 7.5M8 3l4.5 4.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              )}
            </button>
          </form>
          <p className="mt-2.5 font-mono text-[0.62rem] uppercase tracking-[0.12em] text-ink-3">
            Grounded in disclosed relationships + scored news · research, not advice
          </p>
        </div>
      </div>
    </div>
  );
}
