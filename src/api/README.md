# Streaming API, frontend contract

FastAPI backend for the Next.js UI. Replaces the old Flask demo
(`src/demo/`). Runs the agentic graph-RAG chatbot and streams both the graph it
retrieves and the answer it writes, over Server-Sent Events.

## Run

```bash
# from repo root, with the project venv (Python 3.10+; built on 3.14)
.venv/bin/uvicorn src.api.server:app --reload --port 8000
```

Requires the same `.env` as the rest of the project (`ANTHROPIC_KEY`,
`NEO4J_URI` / `NEO4J_USERNAME` / `NEO4J_PASSWORD`). CORS is open to
`http://localhost:3000` (the Next.js dev origin).

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | `{"status":"ok"}` liveness check |
| `GET` | `/api/examples` | `{"examples": [string, ...]}`, preset prompts for the hero |
| `POST` | `/api/chat` | SSE stream (see below) |

### `POST /api/chat`

Request body:

```json
{
  "question": "How does NVDA affect AMD and TSMC?",
  "history": [
    { "role": "user", "content": "prior question text" },
    { "role": "assistant", "content": "prior answer text" }
  ]
}
```

`history` is optional and is plain text turns only (no tool/tool-result blocks), 
the frontend owns the transcript; the agent re-runs its lookups each turn.

Response: `text/event-stream`. Each frame is `data: <json>\n\n`. Consume with
`fetch` + a `ReadableStream` reader (not `EventSource`, which is GET-only).

### SSE event types (the `type` field on each frame's JSON)

| `type` | Payload | Meaning / UI use |
|---|---|---|
| `status` | `{ "message": string }` | Human-readable progress cue ("Mapping NVDA's connections…"). Show as a transient status line. |
| `graph` | `{ "data": {...} }` | The subgraph the agent pulled, render it. Shape below. May arrive more than once if the agent looks up multiple entities. |
| `token` | `{ "text": string }` | Append to the streaming answer. |
| `done` | `{ "answer": string }` | Final full answer text; stream ends. |
| `error` | `{ "message": string }` | Something failed; stream ends. |

### `graph` data shape

```json
{
  "center": "NVDA",          // trigger entity, or null for a "what's trending" query
  "direction": null,          // "up" | "down" | "most_active" for trending queries, else null
  "nodes": [
    { "id": "NVDA", "sentiment": 0.0,  "article_count": 2, "is_center": true  },
    { "id": "TSM",  "sentiment": 0.75, "article_count": 2, "is_center": false },
    { "id": "Intel","sentiment": null, "article_count": 0, "is_center": false }
  ],
  "edges": [
    { "source": "TSM", "rel_type": "SUPPLIES_TO",   "target": "NVDA", "confidence": 0.95 },
    { "source": "NVDA","rel_type": "COMPETES_WITH", "target": "AMD",  "confidence": 0.95 }
  ]
}
```

- `sentiment` is the mean of that entity's article scores in `[-1, 1]`, or `null`
  if it has no scored articles (color nodes accordingly; treat `null` as neutral/unknown).
- `rel_type` is one of `SUPPLIES_TO`, `SUPPLIED_BY`, `COMPETES_WITH`,
  `CO_HOLDS_ETF`, `SECTOR_PEER`, color/legend edges by type.
- A dense neighborhood (~40+ nodes) is normal; `CO_HOLDS_ETF` edges are
  combinatorial, so a per-edge-type toggle is worth it (see cytoscape notes).

## Notes for the frontend build

- Render the `graph` event immediately (it arrives before the answer tokens), 
  fast structural render, then stream the prose beneath it.
- Suggested lib: **cytoscape.js** (force layout, zoom, drag, edge coloring).
