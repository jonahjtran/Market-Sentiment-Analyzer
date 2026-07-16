"""LLM-as-judge for the graph-vs-flat comparison (PRD Section 4.5).

Entity recall counts *whether* the right names appear; it can't tell whether
the reasoning about them is any good. The judge covers that: given the question
and a reference list of the genuinely-related companies, it scores each answer
on entity coverage, correctness, and reasoning depth, and picks a winner.

Two guards against the well-known biases of LLM judges:
  - **Blinding**: the two answers are shown as "System A" / "System B" with no
    hint of which is graph vs flat.
  - **Position randomization**: which system takes slot A is flipped per question
    (by index parity, deterministic, so runs are reproducible), so a judge that
    mildly favors whichever answer comes first can't systematically favor one
    system.

The caller un-blinds the result (map A/B back to graph/flat) when aggregating.
"""

from __future__ import annotations

import json
import os
import re

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-5"
MAX_TOKENS = 1500

_JUDGE_PROMPT = """\
You are a neutral evaluator comparing two AI analysts' answers to the same \
investor question about how one company's news ripples out to related companies.

Question: {question}

For reference, the genuinely related companies a strong answer should surface \
here (competitors, suppliers, customers) are: {reference}. An answer need not \
name all of them, but a good answer should identify the important ones and \
reason correctly about the direction of impact (for example: a competitor's \
strong quarter is often BAD for a rival via share loss, not shared upside; a \
key supplier benefits when its customer's demand rises).

Score each answer from 1 to 5 on:
- "entity_coverage": did it surface the relevant related companies (vs missing \
them or staying vague)?
- "correctness": are its factual claims about the relationships accurate and \
free of invented connections?
- "reasoning_depth": does it reason about direction and magnitude of impact, \
not just assert that everything moves together?

Then choose "winner": "A", "B", or "tie".

System A:
---
{answer_a}
---

System B:
---
{answer_b}
---

Return ONLY a JSON object with exactly these keys:
{{"a": {{"entity_coverage": int, "correctness": int, "reasoning_depth": int}},
 "b": {{"entity_coverage": int, "correctness": int, "reasoning_depth": int}},
 "winner": "A" | "B" | "tie",
 "rationale": "one sentence"}}
"""

_client: Anthropic | None = None


def _anthropic() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ["ANTHROPIC_KEY"])
    return _client


def _parse_json_object(raw: str) -> dict:
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object in judge reply: {raw[:200]!r}")
    return json.loads(match.group(0))


def judge(
    question: str,
    reference: list[str],
    graph_answer: str,
    flat_answer: str,
    graph_first: bool,
) -> dict:
    """Score graph vs flat. `graph_first` decides which slot (A/B) graph takes.

    Returns un-blinded scores keyed by system ("graph"/"flat") plus which system
    the judge preferred and its one-line rationale.
    """
    answer_a, answer_b = (graph_answer, flat_answer) if graph_first else (flat_answer, graph_answer)

    resp = _anthropic().messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[
            {
                "role": "user",
                "content": _JUDGE_PROMPT.format(
                    question=question,
                    reference=", ".join(reference),
                    answer_a=answer_a,
                    answer_b=answer_b,
                ),
            }
        ],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    result = _parse_json_object(text)

    # un-blind: map slot A/B back to graph/flat
    graph_slot, flat_slot = ("a", "b") if graph_first else ("b", "a")
    winner_raw = str(result.get("winner", "tie")).strip().lower()
    if winner_raw in ("a", "b"):
        winner = "graph" if winner_raw == graph_slot else "flat"
    else:
        winner = "tie"

    return {
        "graph": result[graph_slot],
        "flat": result[flat_slot],
        "winner": winner,
        "rationale": result.get("rationale", ""),
        "graph_first": graph_first,
    }
