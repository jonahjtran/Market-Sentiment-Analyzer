"""Fixed multi-hop evaluation set (PRD Phase 7 / Section 4.5).

Each question names ONLY the trigger company and asks, open-endedly, which
related companies are affected, it never names the expected neighbors. That is
the whole point of the comparison: a graph system can *traverse* to the trigger's
suppliers/competitors, while a flat vector-search system can only surface names
that happen to be textually near the query.

`expected` entities are chosen to be **both** (a) genuinely correct real-world
relationships and (b) actually present in the graph's neighborhood of the
trigger (verified against live edges). Point (b) matters for fairness: targeting
an entity the graph cannot reach would test data coverage, not the retrieval
claim, and would penalize both systems equally. Data-center REITs (DLR/EQIX),
for example, are deliberately excluded from NVDA questions because no such edge
exists in the graph, the system itself says so, and scoring against a missing
edge would be dishonest.

Fairness note: expected entities are real-world-correct, not graph artifacts.
Flat RAG *could* surface them if the filings named them; it usually can't,
because a foundry's 10-K rarely lists its customers and a chip 10-K rarely
enumerates every rival. That gap is exactly what the graph closes.
"""

from __future__ import annotations

# Canonical ticker -> the surface forms an LLM answer might use for it. Matching
# is alias-aware because the reasoning prompt is told to write company names
# ("TSMC", "NVIDIA"), not tickers.
ALIASES: dict[str, list[str]] = {
    "NVDA": ["NVDA", "NVIDIA", "Nvidia"],
    "AMD": ["AMD", "Advanced Micro Devices"],
    "TSM": ["TSM", "TSMC", "Taiwan Semiconductor"],
    "AVGO": ["AVGO", "Broadcom"],
    "ASML": ["ASML"],
    "MSFT": ["MSFT", "Microsoft"],
    "AMZN": ["AMZN", "Amazon"],
    "GOOGL": ["GOOGL", "GOOG", "Google", "Alphabet"],
    "ORCL": ["ORCL", "Oracle"],
    "DLR": ["DLR", "Digital Realty"],
    "EQIX": ["EQIX", "Equinix"],
    "INTC": ["INTC", "Intel"],
    "QCOM": ["QCOM", "Qualcomm"],
    "MU": ["MU", "Micron"],
}

# Each: trigger ticker fed to the graph retriever; the question (neighbors NOT
# named); expected neighbor tickers (graph-verified, domain-correct); a one-line
# rationale for the record.
TEST_SET: list[dict] = [
    {
        "id": "nvda-exposure",
        "trigger": "NVDA",
        "question": "NVIDIA just reported very strong AI GPU demand. Which competitors and suppliers are most exposed to this news, and in which direction?",
        "expected": ["AMD", "TSM", "AVGO", "INTC"],
        "why": "AMD/AVGO/Intel compete; TSMC is the foundry, none named in the prompt.",
    },
    {
        "id": "tsm-customers",
        "trigger": "TSM",
        "question": "TSMC raised its capital-expenditure guidance for advanced nodes. Which of its major fabless customers stand to benefit?",
        "expected": ["NVDA", "AMD", "AVGO"],
        "why": "TSMC fabs for NVDA/AMD/AVGO, but a foundry 10-K rarely names customers, hard for flat RAG.",
    },
    {
        "id": "amd-datacenter",
        "trigger": "AMD",
        "question": "AMD reported strong data-center accelerator growth. What does that imply for its main GPU rival and the foundry that manufactures its chips?",
        "expected": ["NVDA", "TSM"],
        "why": "NVDA is the rival; TSMC is the shared foundry.",
    },
    {
        "id": "avgo-relations",
        "trigger": "AVGO",
        "question": "Broadcom is benefiting from AI networking demand. Who are its main competitors in AI silicon, and who manufactures its chips?",
        "expected": ["NVDA", "AMD", "TSM"],
        "why": "AVGO competes with NVDA/AMD and is fabbed by TSMC.",
    },
    {
        "id": "nvda-lift-pressure",
        "trigger": "NVDA",
        "question": "Beyond NVIDIA itself, which chipmakers would a blowout NVIDIA quarter most likely lift, and which would it pressure?",
        "expected": ["AMD", "TSM", "AVGO"],
        "why": "Supplier TSMC lifts with demand; rivals AMD/AVGO face share pressure.",
    },
    {
        "id": "msft-stack",
        "trigger": "MSFT",
        "question": "How is Microsoft connected to the leading AI GPU and accelerator makers in its hardware supply chain?",
        "expected": ["NVDA", "AMD"],
        "why": "MSFT relates to NVDA and AMD in the AI hardware stack.",
    },
    {
        "id": "tsm-dependence",
        "trigger": "TSM",
        "question": "Whose businesses are most dependent on TSMC's manufacturing output for their leading-edge products?",
        "expected": ["NVDA", "AMD", "AVGO"],
        "why": "The three fabless customers most tied to TSMC capacity.",
    },
    {
        "id": "amd-share-gain",
        "trigger": "AMD",
        "question": "If AMD keeps gaining share in AI accelerators, which competitor is most at risk and which manufacturing partner benefits either way?",
        "expected": ["NVDA", "TSM"],
        "why": "NVDA is the at-risk rival; TSMC benefits regardless of who wins.",
    },
]
