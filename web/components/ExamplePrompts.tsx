"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchExamples } from "@/lib/api";

const FALLBACK = [
  "How does NVDA's earnings affect AMD, TSMC, and data center REITs?",
  "AMD just reported strong data center growth. What does that mean for NVDA and Intel?",
  "What's trending down in semiconductors right now?",
];

/* Editorial index of live prompts, hairline rows, mono numerals, no pills. */
export function ExamplePrompts() {
  const [prompts, setPrompts] = useState<string[]>(FALLBACK);
  const router = useRouter();

  useEffect(() => {
    fetchExamples().then((ex) => ex.length && setPrompts(ex)).catch(() => {});
  }, []);

  return (
    <ul className="flex flex-col">
      {prompts.map((p, i) => (
        <li key={p} className="border-t border-line last:border-b">
          <button
            onClick={() => router.push(`/chat?q=${encodeURIComponent(p)}`)}
            className="group flex w-full items-baseline gap-5 py-5 text-left transition-colors hover:bg-surface-2/40"
          >
            <span className="w-7 shrink-0 font-mono text-[0.7rem] tracking-[0.16em] text-ink-3 transition-colors group-hover:text-brand">
              {String(i + 1).padStart(2, "0")}
            </span>
            <span className="flex-1 text-[1rem] leading-snug text-ink-2 transition-colors group-hover:text-ink">
              {p}
            </span>
            <span className="shrink-0 translate-x-0 text-brand opacity-0 transition-all group-hover:translate-x-1 group-hover:opacity-100">
              →
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
