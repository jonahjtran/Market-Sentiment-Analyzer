"""Agentic chatbot: LLM decides how to use the graph (PRD extension, MCP-based).

Unlike src/retrieval/reason.py (which requires a ticker up front and always
does a single N-hop traversal around it), this hands the model the raw
question plus a set of graph tools (src/mcp_server/graph_tools.py) and lets
it decide what to look up — resolve a fuzzy company reference, traverse a
specific entity's neighborhood, or pull aggregate trending sentiment when no
company is named — chaining multiple tool calls if needed. The graph still
constrains what the model can claim (PRD 6.3): it only reasons over data
those tool calls actually returned, never free-associated relationships.

Run: python -m src.retrieval.chat "question" ["prior turn" "prior turn" ...]
"""

import asyncio
import os
import sys

from anthropic import Anthropic
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

MODEL = "claude-sonnet-5"
MAX_TOKENS = 2000
MAX_TOOL_ROUNDS = 6

_SYSTEM_PROMPT = """\
You are a markets analyst chatbot for a self-directed investor. You have \
tools that let you look up real, tracked business relationships (competitors, \
suppliers, customers, ETF co-holders, sector peers) and recent \
sentiment/summaries from company disclosures and earnings commentary. Use \
them whenever a question is about specific companies, sectors, or market \
moves — even if the user doesn't name an exact ticker, try search_entities \
first rather than guessing or answering from general knowledge. If the \
question has no specific company in it (e.g. "what's trending" or "what \
should I look into"), use get_trending instead of guessing a company.

Never mention "graph," "database," "relationships graph," "nodes," "edges," \
"confidence scores," "subgraph," "tool," "tool call," or similar backend/ \
technical terms — describe things the way a human analyst would: "X is a \
direct competitor of Y," "Z supplies key components to X," "the recent \
earnings call had an upbeat tone because...". Never print a raw sentiment \
or confidence number; translate it into plain language like "upbeat," \
"mixed," or "no notable news."

For each company you discuss, explain in plain terms whether the news is \
likely good, bad, or roughly neutral for them, how strong that effect seems, \
and why — including cases where a competitor's good news is actually bad \
news for someone else (share loss, not shared upside), rather than assuming \
everything moves together. If your tools don't surface enough to say \
something meaningful, say so plainly instead of guessing. If the question \
has nothing to do with markets/companies, just answer normally.
"""

_client: Anthropic | None = None


def _anthropic() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ["ANTHROPIC_KEY"])
    return _client


def _mcp_tools_to_anthropic(mcp_tools) -> list[dict]:
    return [
        {"name": t.name, "description": t.description or "", "input_schema": t.inputSchema}
        for t in mcp_tools
    ]


async def answer_chat(question: str, history: list[dict] | None = None) -> dict:
    """Answer `question` using the graph tool server, given prior turns in `history`.

    `history` is a list of Anthropic-format messages ({"role", "content"})
    from previous turns in this conversation; the returned "history" includes
    this turn's exchange appended, so the caller can pass it straight back in
    for the next turn.
    """
    messages = list(history or [])
    messages.append({"role": "user", "content": question})

    server_params = StdioServerParameters(command=sys.executable, args=["-m", "src.mcp_server.graph_tools"])

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = _mcp_tools_to_anthropic((await session.list_tools()).tools)

            for _ in range(MAX_TOOL_ROUNDS):
                resp = _anthropic().messages.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    system=_SYSTEM_PROMPT,
                    messages=messages,
                    tools=tools,
                )
                messages.append({"role": "assistant", "content": resp.content})

                if resp.stop_reason != "tool_use":
                    text = "".join(b.text for b in resp.content if b.type == "text")
                    return {"question": question, "answer": text, "history": messages}

                tool_results = []
                for block in resp.content:
                    if block.type != "tool_use":
                        continue
                    result = await session.call_tool(block.name, block.input)
                    content = "\n".join(
                        c.text for c in result.content if getattr(c, "type", None) == "text"
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": content,
                            "is_error": result.isError,
                        }
                    )
                messages.append({"role": "user", "content": tool_results})

    # Model kept requesting tools past MAX_TOOL_ROUNDS without settling.
    return {
        "question": question,
        "answer": "I wasn't able to pull together a confident answer to that one — could you rephrase or narrow it down?",
        "history": messages,
    }


def run() -> None:
    if len(sys.argv) < 2:
        print('Usage: python -m src.retrieval.chat "question" ["prior turn" ...]')
        sys.exit(1)

    question = sys.argv[1]
    history = None
    for prior in sys.argv[2:]:
        result = asyncio.run(answer_chat(prior, history))
        history = result["history"]
        print(f"Q: {prior}\n{result['answer']}\n")

    result = asyncio.run(answer_chat(question, history))
    print(f"Q: {result['question']}\n\n{result['answer']}")


if __name__ == "__main__":
    run()
