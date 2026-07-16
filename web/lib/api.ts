/* Typed client for the Cascade FastAPI backend (see src/api/README.md). */

export interface GraphNode {
  id: string;
  sentiment: number | null;
  article_count: number;
  is_center: boolean;
}

export type EdgeType =
  | "SUPPLIES_TO"
  | "SUPPLIED_BY"
  | "COMPETES_WITH"
  | "CO_HOLDS_ETF"
  | "SECTOR_PEER";

export interface GraphEdge {
  source: string;
  target: string;
  rel_type: EdgeType;
  confidence: number | null;
}

export interface GraphData {
  center: string | null;
  direction: "up" | "down" | "most_active" | null;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface Article {
  score: number | null;
  summary: string | null;
  source_doc: string;
  doc_type: string;
}

export interface GraphResponse extends GraphData {
  articles: Record<string, Article[]>;
}

export type ChatEvent =
  | { type: "status"; message: string }
  | { type: "graph"; data: GraphData }
  | { type: "token"; text: string }
  | { type: "done"; answer: string }
  | { type: "error"; message: string };

export interface HistoryTurn {
  role: "user" | "assistant";
  content: string;
}

/* ── Eval / comparison scoreboard ── */

export interface JudgeScore {
  entity_coverage: number;
  correctness: number;
  reasoning_depth: number;
}

export interface EvalSideResult {
  answer: string;
  recall: { recall: number; found: string[]; missed: string[] };
  coverage: { coverage: number; found: string[] };
  judge: JudgeScore;
}

export interface EvalQuestion {
  id: string;
  trigger: string;
  question: string;
  expected: string[];
  why: string;
  graph: EvalSideResult;
  flat: EvalSideResult;
  winner: "graph" | "flat" | "tie";
  rationale: string;
}

export interface EvalReport {
  generated_at: string;
  models: { reason: string; flat: string; judge: string };
  summary: {
    n: number;
    entity_recall: { graph: number; flat: number };
    retrieval_coverage: { graph: number; flat: number };
    judge_scores: { graph: JudgeScore; flat: JudgeScore };
    wins: { graph: number; flat: number; tie: number };
    judge_win_rate_graph: number;
  };
  questions: EvalQuestion[];
}

export async function fetchEval(): Promise<EvalReport | null> {
  const res = await fetch("/api/eval");
  if (!res.ok) return null;
  return res.json();
}

export async function fetchExamples(): Promise<string[]> {
  const res = await fetch("/api/examples");
  if (!res.ok) return [];
  const body = await res.json();
  return body.examples ?? [];
}

export async function fetchEntities(q: string): Promise<string[]> {
  const res = await fetch(`/api/entities?q=${encodeURIComponent(q)}`);
  if (!res.ok) return [];
  const body = await res.json();
  return body.matches ?? [];
}

export async function fetchGraph(ticker: string, hops: number): Promise<GraphResponse> {
  const res = await fetch(`/api/graph?ticker=${encodeURIComponent(ticker)}&hops=${hops}`);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Graph fetch failed (${res.status})`);
  }
  return res.json();
}

/**
 * POST /api/chat and dispatch each SSE frame to `onEvent`.
 * SSE over POST means EventSource is out, we read the body stream and split
 * frames on the blank-line delimiter ourselves.
 */
export async function streamChat(
  question: string,
  history: HistoryTurn[],
  onEvent: (ev: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, history }),
    signal,
  });
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Chat request failed (${res.status})`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const line = frame.trim();
      if (!line.startsWith("data:")) continue;
      try {
        onEvent(JSON.parse(line.slice(5).trim()) as ChatEvent);
      } catch {
        // tolerate a malformed frame rather than killing the stream
      }
    }
  }
}
