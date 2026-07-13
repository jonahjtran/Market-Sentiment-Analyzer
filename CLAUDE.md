# Project Context: Market Sentiment Propagation Graph

This document is the single reference file for Claude CLI when working on this project. It contains the full PRD (architecture, decisions, rationale) followed by the ordered action steps for development. Read this file in full before starting or resuming work.

---

# PART 1: PRD (Full Context, Architecture & Decisions)

# PRD: Market Sentiment Propagation Graph

**Status:** Draft v1
**Owner:** Jonah + coworker
**Last updated:** 2026-07-06

---

## 1. Problem Statement

Traditional sentiment analysis for equities treats each stock in isolation: NVIDIA earnings sentiment gets scored, and that score is applied only to NVDA. But real markets don't work that way — sentiment cascades through supply chains, competitor relationships, ETF co-membership, and sector linkages (NVIDIA earnings move AMD, TSMC, and data center REITs, often within hours). Flat/semantic models can't represent or traverse these multi-hop relationships. The result is that a large share of the tradeable signal in earnings/news events is left on the table because it shows up in *related* names, not the primary one.

**Core hypothesis:** A graph RAG system, where an LLM reasons over entity relationships and traverses the graph at query time, will surface cascading sentiment impacts (e.g., "how does NVDA earnings affect AMD, TSMC, and data center REITs?") that a flat/semantic RAG system — limited to similarity search over documents — cannot represent or reason about.

---

## 2. Goals for Learning

1. **Graph RAG mechanics in practice** — hands-on experience building a retrieval layer that traverses relationships instead of doing vector similarity search alone.
2. **New-team stack fluency** — S3 → Spark/Hadoop → Neo4j → LangChain/LlamaIndex.
3. **Graph schema design** — modeling financial entities and relationship types so propagation queries are expressive and performant.
4. **LLM-driven graph reasoning** — prompting and orchestration patterns for having the LLM traverse a graph and reason about relationship strength/direction at query time, rather than relying on precomputed weights.
5. **The "regular RAG fails, graph RAG succeeds" demo** — a concrete, side-by-side illustration of why graph structure matters, showing the LLM correctly reasoning through multi-hop relationships (e.g., competitor beat = possible share loss, not shared upside) that flat retrieval would miss.

---

## 3. Non-Goals (v1)

- Social/alt-data sentiment sources (deferred to v2)
- Analyst report ingestion (deferred to v2)
- Real-time/streaming pipeline (batch is fine for MVP)
- Options / derivatives signals
- Full portfolio construction or execution
- **A backtestable, reproducible trading signal with a target Sharpe ratio.** Deferred to v2 (see Section 6.5) — v1 uses LLM-inferred reasoning at query time, which is not deterministic run-to-run and is not intended to produce a stable numeric signal. Rigorous backtesting requires Approach B (precomputed, calibrated edge weights), planned as the v2 phase.

---

## 4. System Architecture

### 4.1 Data Layer
| Source | Purpose | Notes |
|---|---|---|
| SEC EDGAR (10-Ks) | Mined for disclosed customer/supplier relationships | Legally required disclosures — underused, high-signal, free |
| SEC EDGAR (earnings transcripts) | Sentiment scoring on trigger events | |
| Polygon.io | Intraday price/volume around earnings windows | Primary stock + graph neighbors |
| ETF holdings files | Peer/co-membership edges | Accessible baseline for `CO_HOLDS_ETF` edges |

Deferred to v2: news APIs, analyst reports, social/alt-data.

### 4.2 Graph Layer (Neo4j)

**Nodes:** `Entity` (ticker, sector, name, market cap, etc.)

**Edge types** (each with a `weight` and `confidence` property):
- `SUPPLIES_TO` / `SUPPLIED_BY`
- `COMPETES_WITH`
- `CO_HOLDS_ETF`
- `SECTOR_PEER`

**Ingestion:** Spark job(s) reading raw filings/ETF data from S3, parsing relationships, writing into Neo4j.

### 4.3 Sentiment Scoring Layer

- Sentiment scoring on the trigger event (earnings call / 10-K) via LLM or existing NLP sentiment model. This score, plus the surrounding text, is what gets handed to the LLM at query time as context — there is no separate propagation/decay computation.

### 4.4 RAG Layer (LLM-Inferred Traversal — Approach A)

- LangChain/LlamaIndex query interface for questions like: *"What is the likely near-term sentiment impact on AMD given NVIDIA's latest earnings?"*
- At query time, the system retrieves the relevant subgraph around the trigger entity (neighbors up to N hops, via Neo4j) along with supporting text (filings, transcripts), and passes both to the LLM.
- **The LLM — not a precomputed formula — is responsible for:**
  - Deciding which relationships are meaningfully relevant to the question
  - Reasoning about impact direction and magnitude (e.g., recognizing that a competitor's earnings beat may signal share loss rather than shared upside)
  - Synthesizing a natural-language answer, optionally with a qualitative confidence/strength characterization (e.g., "strong direct effect," "weak/indirect effect")
- Graph structure still matters here — it constrains what the LLM sees and reasons over (the actual relationships that exist), preventing hallucinated connections and keeping reasoning multi-hop rather than single-document.
- Baseline comparator: ChromaDB or Pinecone doing plain vector search over the same documents, used for the side-by-side demo — this baseline has no graph structure, so it can't answer multi-hop questions coherently, which is the core "regular RAG fails" illustration.

### 4.5 Evaluation Layer (replaces Backtest Layer)

Since output is qualitative/LLM-reasoned rather than a deterministic numeric signal, evaluation shifts from backtesting to reasoning quality:
- **Comparative eval:** graph RAG vs. flat RAG answers on a fixed set of multi-hop test questions, scored (manually or LLM-as-judge) on correctness, relevance, and whether the right entities were surfaced at all.
- **Spot-check against realized moves:** informal, retrospective check of whether the LLM's directional call (up/down/neutral) on a neighbor entity matched what actually happened — useful as a sanity signal, but explicitly *not* a rigorous backtest and not a basis for a Sharpe ratio claim.

---

## 5. Tech Stack

| Layer | Tool | Purpose |
|---|---|---|
| Cloud storage | AWS S3 | Raw data storage (filings, transcripts, ETF holdings) |
| Data processing | Apache Spark | In-memory batch processing / ingestion pipeline |
| Data processing | Apache Hadoop / HDFS | Disk-based storage for large batch jobs |
| Graph database | Neo4j (Cypher) | Entity/relationship storage and traversal queries |
| Graph hosting | Neo4j AuraDB (Free tier) | Managed Neo4j instance — no self-hosted infra (EC2/Docker) needed for v1 |
| RAG orchestration | LangChain / LlamaIndex | Query interface, retrieval-augmented reasoning |
| Flat RAG baseline | ChromaDB or Pinecone | Vector similarity search, used as the comparison baseline |
| Price data | Polygon.io | Intraday price/volume around earnings windows |
| Filing data | SEC EDGAR | 10-K filings, earnings transcripts |
| Reference data | ETF holdings files | Peer/co-membership edges |
| Other available datasets (noted, not committed) | OpenCorporates, ICIJ (Panama Papers / Offshore Leaks) | Potential future entity/ownership data sources |

## 6. Impact Reasoning Approach (Architecture Decision)

### 6.1 Two Candidate Architectures

There are two distinct ways to handle "how strongly does sentiment propagate":

- **Approach A — LLM-inferred connections and impact (selected):** No precomputed edge weights or decay formula. At query time, the LLM is given the retrieved subgraph and supporting text, and reasons directly about which relationships matter, and the likely direction/magnitude of impact.
- **Approach B — Explicit weighted propagation (not selected for this phase):** Precomputed, calibrated edge weights and a deterministic hop-decay/time-decay formula (see project history below) drive a reproducible propagation score. This is what a backtestable trading signal would require.

### 6.2 Decision & Rationale

**Selected for v1: Approach A.** A backtestable trading signal with a target Sharpe ratio is not a v1 priority — the priority is learning the graph RAG stack and producing a compelling demo of graph-aware reasoning over flat retrieval. Approach A gets there with substantially less upfront engineering (no weight calibration pipeline, no time-decay tuning, no regression work) and lets the LLM handle the genuinely hard part — judging relationship relevance and direction — which is difficult to encode well in a static formula anyway (e.g., `COMPETES_WITH` sign ambiguity, which was an open question under Approach B).

**Trade-off, explicitly acknowledged:** output is not deterministic or reproducible run-to-run, and there is no numeric signal to compute a Sharpe ratio against under v1. This is intentional — see Section 6.5 for the v2 plan.

### 6.3 What the Graph Still Provides Under Approach A

Even without a scoring formula, the graph is not decorative — it constrains and structures what the LLM reasons over:
- Retrieval is graph-traversal-based (N-hop neighborhood of the trigger entity in Neo4j), not pure semantic similarity — this is what regular RAG can't do.
- The LLM only reasons over relationships that actually exist in the graph (real 10-K-disclosed supply relationships, real ETF co-holdings), which reduces hallucinated connections compared to letting the LLM free-associate from text alone.
- Edge *type* (e.g., `SUPPLIES_TO` vs. `CO_HOLDS_ETF`) is still passed to the LLM as context, so it can reason about relationship strength qualitatively even without a numeric weight.

### 6.4 MVP Sequencing (v1)

1. Ship graph traversal + retrieval (N-hop subgraph extraction from Neo4j around a trigger entity).
2. Build the LLM reasoning/synthesis step: prompt design for taking the subgraph + supporting text and producing a reasoned answer.
3. Build the flat-RAG baseline (ChromaDB/Pinecone) for comparison.
4. Run the comparative eval (Section 4.5) on a fixed test set of multi-hop questions.

### 6.5 v2 Plan: Explicit Weighted Propagation (Approach B)

Once v1 is working and validated via the comparative eval, v2 introduces a precomputed, calibrated propagation model to produce a deterministic, backtestable signal — enabling the Sharpe ratio success criterion. Full design, preserved from the original PRD draft:

**Hop-based decay with edge-type weighting:**
```
impact(node_n) = impact(trigger) × ∏(edge_weight_i)   for each edge i in the path from trigger to node_n
```

Initial prior weights (to be recalibrated empirically):

| Edge type | Prior weight | Rationale |
|---|---|---|
| `SUPPLIES_TO` / `SUPPLIED_BY` | 0.6–0.7 | Direct revenue exposure, tight coupling |
| `COMPETES_WITH` | 0.4–0.5 | Directionally ambiguous — competitor beats can signal share loss, not shared upside; sign needs its own logic, not just magnitude |
| `CO_HOLDS_ETF` | 0.2–0.3 | Weak, mechanical — driven by fund flows rather than fundamentals |
| `SECTOR_PEER` | 0.3–0.4 | Moderate, fundamentals-adjacent but indirect |

**Multi-path aggregation:**
- Start with **max** (strongest single path) for simplicity.
- Move to diminishing-returns sum once calibration data exists: `impact(node_n) = 1 - ∏(1 - path_impact_i)` across all paths — compounds multiple paths but saturates.

**Time decay (independent of hop decay):**
```
impact(node_n, t) = impact(node_n, t=0) × e^(-t/τ)
```
`τ` likely varies by hop distance — direct-hop impact may resolve within hours; 2-hop impact may take a day or two.

**Empirical calibration:**
1. Collect historical trigger events and observed price moves across 1-hop, 2-hop, 3-hop neighbors.
2. Regress observed move magnitude against hop distance + edge type to estimate real decay weights.
3. Recalibrate weights and `τ` from the regression rather than relying on priors.

**v2 sequencing:**
1. Ship hop-based decay + edge-type weights with priors, using max aggregation.
2. Add time decay once price-window backtesting is running.
3. Run empirical calibration against historical events; update weights.
4. Revisit aggregation method (probabilistic sum vs. max) based on calibration results.

**v2 entry criteria:** v1's comparative eval shows graph RAG meaningfully outperforming flat RAG on the multi-hop test set, and there's appetite to invest in the calibration pipeline (data collection, regression, backtest infrastructure) beyond the learning-focused v1 scope.

---

## 7. User Flow

1. **Ingest** — Spark pulls new 10-K/earnings data from S3, updates the Neo4j graph with new entities/edges.
2. **Trigger event** — An earnings call or filing lands for Entity X.
3. **Score** — Sentiment score computed for X's event.
4. **Retrieve subgraph** — Neo4j traversal from X pulls the N-hop neighborhood (AMD, TSMC, REITs, etc.) along with edge types and supporting filing/transcript text.
5. **Query/Reason** — A user asks a question like "What's affected by today's NVDA earnings?" — the LLM reasons over the retrieved subgraph and text to produce an answer, judging relevance and likely direction/magnitude itself.
6. **Answer output** — Natural-language response identifying affected entities, the relationship driving each effect, and a qualitative read on direction/strength.
7. **Spot-check (optional)** — Informal, retrospective comparison of the LLM's directional calls against realized price moves, as a sanity check rather than a rigorous backtest.

---

## 8. Success Metrics

- **Primary:** A working side-by-side demo showing flat/regular RAG failing a multi-hop query (e.g., "what's affected by NVDA earnings?") vs. graph RAG correctly surfacing and reasoning about cascading relationships.
- **Secondary:** Comparative eval results (Section 4.5) — graph RAG answers judged more correct/complete than flat RAG on a fixed multi-hop test set.
- **Deferred to v2:** Sharpe ratio improvement / backtestable trading signal — see Section 6.5.

---

## 9. Key Learnings to Take Away

- Where graph RAG actually earns its keep vs. where flat vector search is sufficient.
- Schema design tradeoffs — edge type granularity vs. query performance vs. signal quality.
- Free/public data (10-K disclosures, ETF holdings) is legally mandated, structured, and underused for relationship graphs.
- Backtesting rigor — proving a Sharpe improvement (not just a plausible story) is a transferable discipline.
- Full-stack fluency across S3/Spark/Neo4j/LangChain, directly applicable to the new team's stack.

---

## 10. Open Questions

- How much relationship-type context (edge metadata, sample disclosure text) the LLM needs in-prompt to reason well about `COMPETES_WITH` sign ambiguity, vs. relying on general model judgment.
- Whether ETF co-membership edges should be time-varying (holdings change quarterly) and how to version them in the graph.
- How to design the comparative eval test set (Section 4.5) so it's genuinely hard for flat RAG rather than trivially graph-favoring.
- **v2 planning:** Approach B (precomputed edge weights, hop decay, time decay, empirical calibration) is fully specified in Section 6.5 for when the project moves to that phase.
---

# PART 2: Action Steps (Build Order for Claude CLI)

# Dev Steps: Market Sentiment Propagation Graph (v1 / Approach A)

Reference doc for Claude CLI. Execute in order. Each phase should be a working, testable slice before moving to the next — don't scale up (Spark, full ingestion, full test set) until the thin slice works end-to-end.

---

## Phase 0 — Environment Setup

- [ ] Create S3 bucket(s) with prefixes: `/filings/`, `/transcripts/`, `/etf-holdings/`
- [ ] Provision Neo4j AuraDB instance (Free tier — console.neo4j.io; managed, no EC2/self-hosting needed for v1; do NOT set up Hadoop/HDFS yet)
- [ ] Save AuraDB connection URI, username, password to `.env` (shown only once at creation — download the credentials file)
- [ ] Init Python project
- [ ] Install deps: `neo4j`, `langchain` (or `llama-index`), `chromadb` (or `pinecone-client`), `boto3`
- [ ] Set up `.env` for API keys (Anthropic/OpenAI, Neo4j URI/creds, S3 creds)

**Exit criteria:** Can connect to S3, Neo4j, and call the LLM API from a script.

---

## Phase 1 — Thin-Slice Data Ingestion (manual, not Spark yet)

- [ ] Pull one trigger entity's most recent 10-K from SEC EDGAR (start with NVDA)
- [ ] Pull 10-Ks for 2-3 related entities (AMD, TSMC)
- [ ] Pull one ETF holdings file (e.g., SOXX) for `CO_HOLDS_ETF` edges
- [ ] Write a small parser (regex or LLM-assisted extraction) to pull customer/supplier mentions from 10-K text
- [ ] Validate extraction manually on this handful of filings before writing any Spark code

**Exit criteria:** You have structured (entity, relationship, entity) triples extracted from real filings for NVDA/AMD/TSMC + ETF co-membership.

---

## Phase 2 — Graph Construction

- [ ] Write Cypher `CREATE` statements (or small Python script via `neo4j` driver) to load the entities and edges from Phase 1
- [ ] Create edge types: `SUPPLIES_TO`, `SUPPLIED_BY`, `COMPETES_WITH`, `CO_HOLDS_ETF`, `SECTOR_PEER`
- [ ] Run test Cypher queries: N-hop traversal from NVDA (confirm AMD, TSMC, ETF co-holders are reachable)

**Exit criteria:** A Cypher query from NVDA returns the correct N-hop neighborhood with edge types.

---

## Phase 3 — Sentiment Scoring

- [ ] Pull NVDA's latest earnings transcript
- [ ] Run it through an LLM prompt to produce a sentiment score + short summary
- [ ] Store the score/summary alongside the trigger node/event (in Neo4j as a property, or in a linked doc store)

**Exit criteria:** NVDA trigger event has an attached sentiment score + summary retrievable by entity.

---

## Phase 4 — Graph RAG Query Layer (Approach A core)

- [ ] Build retrieval function: given a trigger entity, query Neo4j for N-hop subgraph (nodes + edge types)
- [ ] Pull associated supporting text (transcript/filing excerpts) for those nodes
- [ ] Build prompt template: hand the LLM the subgraph (nodes, edge types) + supporting text; ask it to reason about impact direction/magnitude, not just retrieve
- [ ] Wire this into LangChain/LlamaIndex as a custom retriever + chain

**Exit criteria:** Querying "How does NVDA's earnings affect AMD, TSMC, and data center REITs?" returns a reasoned, multi-hop answer that cites the graph relationships used.

---

## Phase 5 — Flat RAG Baseline

- [ ] Chunk the same documents (10-Ks, transcripts) into ChromaDB or Pinecone with standard embeddings
- [ ] Run the same multi-hop question against this baseline

**Exit criteria:** You have a flat-RAG answer to compare against the Phase 4 graph-RAG answer on the same question.

---

## Phase 6 — Side-by-Side Demo

- [ ] Select 2-3 multi-hop test questions (e.g., NVDA → AMD/TSMC/REITs)
- [ ] Run both systems (Phase 4 vs Phase 5) on each question
- [ ] Capture outputs side-by-side — this is the core deliverable (PRD Section 8, primary success metric)

**Exit criteria:** A clear, presentable case where flat RAG fails/misses relationships and graph RAG correctly traverses and reasons about them.

---

## Phase 7 — Comparative Eval (Section 4.5)

- [ ] Expand the test question set beyond the initial 2-3
- [ ] Score each system's answers (manual or LLM-as-judge) on correctness, relevance, and whether the right entities were surfaced
- [ ] (Optional) Spot-check LLM directional calls against realized price moves via Polygon.io — informal sanity check only, not a backtest

**Exit criteria:** Comparative eval results documented (PRD Section 4.5, secondary success metric).

---

## Phase 8 — Scale Up (only after Phases 1-7 work on the thin slice)

- [ ] Build the Spark ingestion job(s) to replace manual pulls — parse filings/ETF data from S3 into graph entities/edges at scale
- [ ] Only introduce Hadoop/HDFS if Spark batch jobs exceed in-memory capacity
- [ ] Expand entity coverage beyond NVDA/AMD/TSMC to full sector(s)

---

## Explicit Non-Goals for This Pass (do not build)

- Precomputed edge weights / hop-decay / time-decay formulas (Approach B — deferred to v2, see PRD Section 6.5)
- Backtestable Sharpe ratio signal (v2)
- Social/alt-data sentiment sources (v2)
- Real-time/streaming pipeline (batch only for v1)
- Analyst report ingestion (v2)

**v2 entry criteria:** Only revisit Approach B once Phase 7's comparative eval shows graph RAG meaningfully outperforming flat RAG, and there's appetite to invest in calibration infrastructure.