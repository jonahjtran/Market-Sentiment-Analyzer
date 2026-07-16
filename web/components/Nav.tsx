"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Wordmark } from "./Wordmark";

const LINKS = [
  { href: "/chat", label: "Analyst" },
  { href: "/graph", label: "Graph" },
  { href: "/eval", label: "Benchmark" },
];

/* Borderless editorial bar, wordmark left, plain text links right,
   a soft scrim for readability instead of a container. */
export function Nav() {
  const pathname = usePathname();
  return (
    <header className="fixed top-0 inset-x-0 z-50 bg-gradient-to-b from-surface-0/85 to-transparent pb-6 backdrop-blur-[2px]">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 pt-5">
        <Link href="/" aria-label="Cascade home" className="transition-opacity hover:opacity-75">
          <Wordmark size={19} />
        </Link>
        <nav className="flex items-center gap-7 text-[0.85rem]">
          {LINKS.map(({ href, label }) => {
            const active = pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`underline-offset-[6px] transition-colors hover:text-ink hover:underline ${
                  active ? "text-ink underline" : "text-ink-2"
                }`}
              >
                {label}
              </Link>
            );
          })}
          <Link
            href="/chat"
            className="hidden items-center gap-1.5 text-ink transition-opacity hover:opacity-75 sm:inline-flex"
          >
            Ask the analyst
            <span className="text-brand transition-transform group-hover:translate-x-0.5">→</span>
          </Link>
        </nav>
      </div>
    </header>
  );
}
