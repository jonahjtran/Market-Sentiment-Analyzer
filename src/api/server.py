"""FastAPI streaming backend for the web UI (replaces the Flask demo).

Exposes the agentic graph-RAG chatbot as a Server-Sent-Events (SSE) stream so a
Next.js frontend can, in one request:
  - render the relationship graph the model pulls (`graph` events), and
  - stream the analyst answer token-by-token (`token` events),
  - with lightweight progress cues in between (`status` events).

It reuses the same retrieval primitives the MCP server (src/mcp_server/
graph_tools.py) wraps, get_subgraph / get_trending_subgraph / entity search, 
but calls them in-process instead of over an MCP stdio subprocess, which is the
right trade-off for a long-lived web server (no per-request subprocess). The
system prompt is shared with src/retrieval/chat.py so the web agent and the CLI
agent reason identically.

Conversation history is exchanged as plain {role, content-text} turns (not raw
tool-use blocks), keeping it JSON-clean for the browser; the tool loop re-runs
fresh each turn, re-deriving any lookups it needs.

Run: uvicorn src.api.server:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, SessionExpired
from pydantic import BaseModel

from src.ingestion.edgar_client import TICKERS
from src.retrieval.chat import _SYSTEM_PROMPT
from src.retrieval.subgraph import DEFAULT_HOPS, get_subgraph, get_trending_subgraph

load_dotenv()

MODEL = "claude-sonnet-5"
MAX_TOKENS = 2000
MAX_TOOL_ROUNDS = 6

# Preset prompts surfaced by the UI hero (mirrors the old demo's question set,
# generalized for the free-text agent).
EXAMPLE_PROMPTS = [
    "How does NVDA's earnings affect AMD, TSMC, and data center REITs?",
    "AMD just reported strong data center growth. What does that mean for NVDA and Intel?",
    "What's trending down in semiconductors right now?",
]

app = FastAPI(title="Market Sentiment Graph API")

# The Next.js dev server is a different origin; let the browser call us.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_client: AsyncAnthropic | None = None
_driver = None


def _anthropic() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_KEY"])
    return _client


def _get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            os.environ["NEO4J_URI"],
            auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
            # AuraDB closes idle sockets server-side; recycle pooled connections
            # well before that so a long-idle web server never hands a request
            # a defunct connection.
            max_connection_lifetime=300,
            keep_alive=True,
        )
    return _driver


def _reset_driver() -> None:
    """Drop the pooled driver after a stale-connection failure; next call rebuilds."""
    global _driver
    if _driver is not None:
        try:
            _driver.close()
        except Exception:
            pass
        _driver = None


# --- graph tools (same implementations the MCP server wraps) -----------------

_DISTINCT_ENTITY_NAMES_QUERY = "MATCH (e:Entity) RETURN DISTINCT e.name AS name"


def _known_entity_names() -> list[str]:
    with _get_driver().session() as session:
        names = {row["name"] for row in session.run(_DISTINCT_ENTITY_NAMES_QUERY)}
    return sorted(names | set(TICKERS))


def _search_entities(query: str) -> list[str]:
    q = query.strip().lower()
    if not q:
        return []
    return [n for n in _known_entity_names() if q in n.lower()]


TOOLS = [
    {
        "name": "search_entities",
        "description": (
            "Find companies in the graph matching a free-text query. Use this "
            "first whenever the question doesn't give an exact ticker or company "
            "name (partial names, misspellings, informal references). Returns "
            "actual entity names as stored; always pass one of these to "
            "get_subgraph rather than guessing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free-text company reference."}
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_subgraph",
        "description": (
            "Get a company's business-relationship neighborhood (competitors, "
            "suppliers, customers, ETF co-holders, sector peers) plus recent "
            "article sentiment for every company reached. Pass an exact entity "
            "name from search_entities or a well-known ticker like NVDA. Use for "
            "'how does X affect Y' or 'what's the latest on X' questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Exact entity name / ticker."},
                "hops": {
                    "type": "integer",
                    "description": f"Neighborhood depth (default {DEFAULT_HOPS}).",
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_trending",
        "description": (
            "Companies with the most notable aggregate recent sentiment, when the "
            "question names no specific company ('what's trending', 'what should I "
            "look into'). direction is 'up' (most positive), 'down' (most "
            "negative), or 'most_active' (most articles regardless of direction)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["up", "down", "most_active"],
                    "description": "Which trend to surface.",
                },
                "limit": {"type": "integer", "description": "How many to return (default 5)."},
            },
        },
    },
]


def _status_for(name: str, args: dict) -> str:
    if name == "search_entities":
        return f"Searching for “{args.get('query', '')}”…"
    if name == "get_subgraph":
        return f"Mapping {args.get('ticker', '')}'s connections…"
    if name == "get_trending":
        return "Scanning for names moving on sentiment…"
    return "Working…"


def _subgraph_to_render(result: dict) -> dict:
    """Shape a subgraph result into nodes+edges the frontend can draw.

    Node sentiment is the average of that entity's article scores (None if it
    has no scored articles), so the UI can color nodes by mood; article_count
    lets it distinguish a single spike from a sustained trend.
    """
    articles = result.get("articles", {})
    edges = result.get("edges", []) or []
    center = result.get("center")

    node_ids: set[str] = set()
    for e in edges:
        node_ids.add(e["source"])
        node_ids.add(e["target"])
    if center:
        node_ids.add(center)
    for t in result.get("trending", []) or []:
        node_ids.add(t["entity"])

    nodes = []
    for name in sorted(node_ids):
        arts = articles.get(name, []) or []
        scores = [a["score"] for a in arts if a.get("score") is not None]
        nodes.append(
            {
                "id": name,
                "sentiment": (sum(scores) / len(scores)) if scores else None,
                "article_count": len(arts),
                "is_center": name == center,
            }
        )

    return {
        "center": center,
        "direction": result.get("direction"),
        "nodes": nodes,
        "edges": edges,
    }


async def _run_graph_call(fn, *args):
    """Run a blocking Neo4j call in a worker thread, retrying once through a
    fresh driver if the pooled connection turned out to be stale/defunct.

    The sync driver runs off the event loop so the async server stays
    responsive under concurrent requests.
    """
    try:
        return await asyncio.to_thread(fn, *args)
    except (ServiceUnavailable, SessionExpired, OSError):
        _reset_driver()
        return await asyncio.to_thread(fn, *args)


async def _run_tool(name: str, args: dict) -> tuple[dict, dict | None]:
    """Execute a tool; return (result_for_model, render_or_None)."""
    if name == "search_entities":
        names = await _run_graph_call(_search_entities, args.get("query", ""))
        return {"matches": names}, None
    if name == "get_subgraph":
        result = await _run_graph_call(
            lambda t, h: get_subgraph(_get_driver(), t, h),
            args["ticker"],
            int(args.get("hops") or DEFAULT_HOPS),
        )
        return result, _subgraph_to_render(result)
    if name == "get_trending":
        result = await _run_graph_call(
            lambda d, l: get_trending_subgraph(_get_driver(), d, l),
            args.get("direction", "up"),
            int(args.get("limit") or 5),
        )
        return result, _subgraph_to_render(result)
    return {"error": f"unknown tool {name}"}, None


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def _chat_stream(question: str, history: list[dict]):
    """Async generator yielding SSE frames for one agentic turn."""
    messages: list[dict] = []
    for turn in history:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})

    client = _anthropic()
    try:
        for _ in range(MAX_TOOL_ROUNDS):
            async with client.messages.stream(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=_SYSTEM_PROMPT,
                messages=messages,
                tools=TOOLS,
            ) as stream:
                async for text in stream.text_stream:
                    yield _sse({"type": "token", "text": text})
                final = await stream.get_final_message()

            messages.append({"role": "assistant", "content": final.content})

            if final.stop_reason != "tool_use":
                answer = "".join(b.text for b in final.content if b.type == "text")
                yield _sse({"type": "done", "answer": answer})
                return

            tool_results = []
            for block in final.content:
                if block.type != "tool_use":
                    continue
                yield _sse({"type": "status", "message": _status_for(block.name, block.input)})
                result, render = await _run_tool(block.name, block.input)
                if render is not None:
                    yield _sse({"type": "graph", "data": render})
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    }
                )
            messages.append({"role": "user", "content": tool_results})

        # Model kept asking for tools past the round cap without settling.
        yield _sse(
            {
                "type": "done",
                "answer": "I couldn't settle on a confident answer to that, try narrowing the question.",
            }
        )
    except Exception as exc:  # surface the failure instead of a silently dead stream
        yield _sse({"type": "error", "message": str(exc)})


class ChatRequest(BaseModel):
    question: str
    history: list[dict] | None = None


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/examples")
async def examples():
    return {"examples": EXAMPLE_PROMPTS}


@app.get("/api/eval")
async def eval_results():
    """Serve the latest graph-vs-flat comparison report (src/eval/results.json).

    Produced offline by `python -m src.eval.run_eval`; 404 until it's been run.
    """
    path = Path(__file__).resolve().parent.parent / "eval" / "results.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="No eval results yet, run src.eval.run_eval")
    return json.loads(path.read_text())


@app.get("/api/entities")
async def entities(q: str = ""):
    """Entity-name autocomplete for the graph explorer's search box."""
    matches = await _run_graph_call(_search_entities, q)
    return {"matches": matches[:12]}


@app.get("/api/graph")
async def graph(ticker: str, hops: int = DEFAULT_HOPS):
    """Direct subgraph fetch for the graph explorer, no LLM round-trip.

    Returns the same render shape the chat stream's `graph` events use, plus
    per-entity article details for the node detail panel.
    """
    hops = max(1, min(int(hops), 3))  # bound traversal cost
    try:
        result = await _run_graph_call(
            lambda t, h: get_subgraph(_get_driver(), t, h), ticker.strip(), hops
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    render = _subgraph_to_render(result)
    if not render["edges"] and len(render["nodes"]) <= 1:
        raise HTTPException(status_code=404, detail=f"No graph neighborhood found for {ticker!r}")
    return {**render, "articles": result.get("articles", {})}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    return StreamingResponse(
        _chat_stream(question, req.history or []),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy buffering so tokens flush live
        },
    )
