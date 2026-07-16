/* Cascade mark: three nodes stepping down a smooth cascade curve.
   Drawn on a 24px grid with its visual mass centered for optical alignment
   against the serif wordmark's x-height. */
export function CascadeMark({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M4 7 C 10 7, 9 12, 12 12 S 17 17, 20 17"
        stroke="#22d3ee"
        strokeWidth="1.5"
        strokeLinecap="round"
        opacity="0.9"
      />
      <circle cx="4" cy="7" r="2.6" fill="#22d3ee" />
      <circle cx="12" cy="12" r="2" fill="#7dd3fc" />
      <circle cx="20" cy="17" r="1.5" fill="#a78bfa" />
    </svg>
  );
}

export function Wordmark({ size = 20 }: { size?: number }) {
  return (
    <span className="inline-flex items-center gap-[7px] select-none">
      {/* serif x-height sits low; nudge the mark down to meet it optically */}
      <CascadeMark size={size} />
      <span className="font-display text-[1.3rem] leading-none tracking-tight translate-y-[-1px]">
        Cascade
      </span>
    </span>
  );
}
