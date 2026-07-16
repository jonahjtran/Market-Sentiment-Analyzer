"use client";

import { useEffect, useRef } from "react";

/* Ambient hero constellation: real tickers linked by curved relationship
   edges, sentiment pulses sliding along them. Nodes render as bright cores
   inside soft bloom; edges are shallow arcs, not chords. Weighted toward the
   right of the canvas so the editorial headline owns the left. */

type N = { id: string; r: number; a: number; size: number; hue: string };

const CENTER = "NVDA";
const RING1: N[] = [
  { id: "TSM", r: 0.17, a: -0.62, size: 4.6, hue: "#34d399" },
  { id: "AMD", r: 0.18, a: 0.65, size: 4.6, hue: "#8b95a8" },
  { id: "MSFT", r: 0.19, a: 2.15, size: 4.6, hue: "#8b95a8" },
  { id: "AVGO", r: 0.18, a: 3.35, size: 4.2, hue: "#34d399" },
  { id: "SK Hynix", r: 0.19, a: 4.25, size: 3.8, hue: "#8b95a8" },
  { id: "Micron", r: 0.18, a: 5.2, size: 3.8, hue: "#8b95a8" },
];
const RING2: N[] = [
  { id: "ASML", r: 0.33, a: -0.95, size: 3.2, hue: "#8b95a8" },
  { id: "Samsung", r: 0.32, a: -0.18, size: 3.2, hue: "#8b95a8" },
  { id: "Intel", r: 0.34, a: 0.95, size: 3.2, hue: "#f87171" },
  { id: "Qualcomm", r: 0.32, a: 1.62, size: 2.8, hue: "#8b95a8" },
  { id: "GOOGL", r: 0.33, a: 2.48, size: 3.2, hue: "#8b95a8" },
  { id: "AMZN", r: 0.32, a: 3.08, size: 3.2, hue: "#8b95a8" },
  { id: "DLR", r: 0.34, a: 3.78, size: 2.8, hue: "#34d399" },
  { id: "EQIX", r: 0.33, a: 4.5, size: 2.8, hue: "#8b95a8" },
  { id: "Foxconn", r: 0.32, a: 4.14, size: 2.8, hue: "#8b95a8" },
  { id: "Marvell", r: 0.34, a: 5.92, size: 2.8, hue: "#8b95a8" },
];

const EDGES: [string, string, string][] = [
  ["NVDA", "TSM", "#3987e5"],
  ["NVDA", "AMD", "#d95926"],
  ["NVDA", "MSFT", "#3987e5"],
  ["NVDA", "AVGO", "#d95926"],
  ["NVDA", "SK Hynix", "#3987e5"],
  ["NVDA", "Micron", "#3987e5"],
  ["TSM", "ASML", "#3987e5"],
  ["TSM", "Samsung", "#d95926"],
  ["AMD", "Intel", "#d95926"],
  ["AMD", "Qualcomm", "#d95926"],
  ["MSFT", "GOOGL", "#d95926"],
  ["MSFT", "AMZN", "#d95926"],
  ["AVGO", "Marvell", "#d95926"],
  ["AVGO", "Foxconn", "#3987e5"],
  ["MSFT", "DLR", "#9085e9"],
  ["AMZN", "EQIX", "#9085e9"],
  ["SK Hynix", "Samsung", "#d95926"],
  ["Micron", "SK Hynix", "#d95926"],
];

const PULSE_PATHS: [string, string][] = [
  ["NVDA", "TSM"],
  ["TSM", "ASML"],
  ["NVDA", "AMD"],
  ["AMD", "Intel"],
  ["NVDA", "MSFT"],
  ["MSFT", "DLR"],
  ["NVDA", "Micron"],
];

/** Control point for a shallow arc between two points (perpendicular bow). */
function arcCtrl(x1: number, y1: number, x2: number, y2: number, bow: number): [number, number] {
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len = Math.hypot(dx, dy) || 1;
  return [mx - (dy / len) * bow, my + (dx / len) * bow];
}

/** Point along a quadratic bezier at t. */
function qPoint(t: number, x1: number, y1: number, cx: number, cy: number, x2: number, y2: number): [number, number] {
  const u = 1 - t;
  return [u * u * x1 + 2 * u * t * cx + t * t * x2, u * u * y1 + 2 * u * t * cy + t * t * y2];
}

export function HeroGraph({ className = "" }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let raf = 0;
    let w = 0;
    let h = 0;

    const nodes = [{ id: CENTER, r: 0, a: 0, size: 6.5, hue: "#22d3ee" }, ...RING1, ...RING2];
    const byId = new Map(nodes.map((n) => [n.id, n]));

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const rect = canvas.getBoundingClientRect();
      w = rect.width;
      h = rect.height;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    const pos = (n: N, t: number): [number, number] => {
      // right-weighted on wide screens, centered on narrow ones
      const wide = w > 820;
      const cx = w * (wide ? 0.66 : 0.5);
      const cy = h * (wide ? 0.48 : 0.56);
      const R = Math.min(w, h) * (wide ? 1.18 : 1.0);
      const drift = reduced ? 0 : Math.sin(t * 0.00022 + n.a * 7) * 0.014;
      const x = cx + Math.cos(n.a + drift) * n.r * R;
      const y = cy + Math.sin(n.a + drift) * n.r * R * 0.78;
      return [x, y];
    };

    const bowFor = (a: string, b: string) => 14 + ((a.length * 7 + b.length * 3) % 18);

    const draw = (t: number) => {
      ctx.clearRect(0, 0, w, h);

      // edges, shallow arcs, whisper-thin
      for (const [a, b, color] of EDGES) {
        const [x1, y1] = pos(byId.get(a)!, t);
        const [x2, y2] = pos(byId.get(b)!, t);
        const [cx, cy] = arcCtrl(x1, y1, x2, y2, bowFor(a, b));
        ctx.strokeStyle = color + "2e";
        ctx.lineWidth = 0.8;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.quadraticCurveTo(cx, cy, x2, y2);
        ctx.stroke();
      }

      // pulses gliding along the arcs
      if (!reduced) {
        PULSE_PATHS.forEach(([a, b], i) => {
          const [x1, y1] = pos(byId.get(a)!, t);
          const [x2, y2] = pos(byId.get(b)!, t);
          const [cx, cy] = arcCtrl(x1, y1, x2, y2, bowFor(a, b));
          const cycle = 5600;
          const phase = ((t + i * 800) % cycle) / cycle;
          if (phase > 0.6) return;
          const k = phase / 0.6;
          const [x, y] = qPoint(k, x1, y1, cx, cy, x2, y2);
          const fade = k < 0.15 ? k / 0.15 : k > 0.8 ? (1 - k) / 0.2 : 1;
          // comet: short trail behind the head
          for (let s = 0; s < 4; s++) {
            const kt = Math.max(0, k - s * 0.025);
            const [tx, ty] = qPoint(kt, x1, y1, cx, cy, x2, y2);
            ctx.fillStyle = `rgba(52, 211, 153, ${0.5 * fade * (1 - s / 4)})`;
            ctx.beginPath();
            ctx.arc(tx, ty, 1.6 - s * 0.3, 0, Math.PI * 2);
            ctx.fill();
          }
          const glow = ctx.createRadialGradient(x, y, 0, x, y, 6);
          glow.addColorStop(0, `rgba(52, 211, 153, ${0.7 * fade})`);
          glow.addColorStop(1, "rgba(52, 211, 153, 0)");
          ctx.fillStyle = glow;
          ctx.beginPath();
          ctx.arc(x, y, 6, 0, Math.PI * 2);
          ctx.fill();
        });
      }

      // nodes, bloom halo, then gradient core with a bright center
      for (const n of nodes) {
        const [x, y] = pos(n, t);
        const breathe = reduced ? 1 : 1 + Math.sin(t * 0.0012 + n.a * 3) * 0.06;

        const halo = ctx.createRadialGradient(x, y, 0, x, y, n.size * 5.5 * breathe);
        halo.addColorStop(0, n.hue + "3c");
        halo.addColorStop(0.55, n.hue + "14");
        halo.addColorStop(1, n.hue + "00");
        ctx.fillStyle = halo;
        ctx.beginPath();
        ctx.arc(x, y, n.size * 5.5 * breathe, 0, Math.PI * 2);
        ctx.fill();

        const core = ctx.createRadialGradient(x - n.size * 0.3, y - n.size * 0.3, 0, x, y, n.size);
        core.addColorStop(0, "#f8fafc");
        core.addColorStop(0.35, n.hue);
        core.addColorStop(1, n.hue + "c8");
        ctx.fillStyle = core;
        ctx.beginPath();
        ctx.arc(x, y, n.size, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = n.id === CENTER ? "rgba(242,244,248,0.92)" : "rgba(154,163,181,0.62)";
        ctx.font = `${n.id === CENTER ? 500 : 400} ${n.id === CENTER ? 11.5 : 10}px ui-monospace, SFMono-Regular, monospace`;
        ctx.textAlign = "center";
        ctx.fillText(n.id, x, y - n.size - 8);
      }
    };

    if (reduced) {
      draw(0);
    } else {
      const loop = (t: number) => {
        draw(t);
        raf = requestAnimationFrame(loop);
      };
      raf = requestAnimationFrame(loop);
    }

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, []);

  return <canvas ref={ref} className={className} aria-hidden />;
}
