"""MCP server exposing graph retrieval as tools for an agentic chatbot.

Wraps the existing retrieval functions (src/retrieval/subgraph.py) as MCP
tools rather than pre-classifying a question and picking a retrieval path
for it. The LLM decides which tool(s) to call, with what arguments, and can
chain calls (e.g. search_entities to resolve a fuzzy company reference, then
get_subgraph on the result) — the graph still constrains what it can see,
but the *decision* of what to look up lives in the model's tool-use loop,
not in a pre-step here.

Run: python -m src.mcp_server.graph_tools
"""

import os

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from neo4j import GraphDatabase

from src.ingestion.edgar_client import TICKERS
from src.retrieval.subgraph import DEFAULT_HOPS, get_subgraph, get_trending_subgraph

load_dotenv()

mcp = FastMCP("market-sentiment-graph")

_driver = None


def _get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            os.environ["NEO4J_URI"],
            auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
        )
    return _driver


_DISTINCT_ENTITY_NAMES_QUERY = "MATCH (e:Entity) RETURN DISTINCT e.name AS name"


def _known_entity_names() -> list[str]:
    """Entity.name values as they actually exist in the graph.

    Not assumed to be tickers — filing-derived entities are stored under
    suffix-stripped company names (see canonical_name() in load_graph.py),
    so a fuzzy search has to match against real graph state, not just the
    static ticker list.
    """
    with _get_driver().session() as session:
        names = {row["name"] for row in session.run(_DISTINCT_ENTITY_NAMES_QUERY)}
    return sorted(names | set(TICKERS))


@mcp.tool()
def search_entities(query: str) -> list[str]:
    """Find companies in the graph matching a free-text query.

    Use this first whenever the user's question doesn't give you an exact
    ticker or exact company name — e.g. "the company that makes GPUs",
    partial names, misspellings, or informal references. Returns the actual
    Entity names as stored in the graph (tickers like "NVDA" or company
    names like "Intel" depending on how that entity was ingested) — always
    use one of these returned names, not a guess, when calling get_subgraph.

    Returns an empty list if nothing matches; try a broader or different
    query term rather than assuming the company isn't tracked.
    """
    query_lower = query.strip().lower()
    if not query_lower:
        return []
    return [name for name in _known_entity_names() if query_lower in name.lower()]


@mcp.tool(name="get_subgraph")
def get_subgraph_tool(ticker: str, hops: int = DEFAULT_HOPS) -> dict:
    """Get a company's business-relationship neighborhood and recent news.

    Given an exact Entity name (from search_entities, or a well-known ticker
    like "NVDA"), returns the companies connected to it within `hops` steps
    (competitors, suppliers, customers, ETF co-holders, sector peers) along
    with recent article summaries and sentiment for every company reached.
    Use this to answer "how does X affect Y" or "what's the latest on X and
    who does it impact" style questions.
    """
    return get_subgraph(_get_driver(), ticker, hops)


@mcp.tool()
def get_trending(direction: str = "up", limit: int = 5) -> dict:
    """Get the companies with the most notable aggregate recent sentiment.

    Use this when the question names no specific company — "what's
    trending", "what's trending down", "what should I look into", "what's
    getting a lot of attention". `direction` must be one of:
      - "up": highest average sentiment (most positive)
      - "down": lowest average sentiment (most negative)
      - "most_active": most articles regardless of sentiment direction

    Each returned entity includes its average sentiment score and article
    count, so you can tell a single loud article apart from a sustained
    trend before characterizing it to the user.
    """
    return get_trending_subgraph(_get_driver(), direction, limit)


if __name__ == "__main__":
    mcp.run()
