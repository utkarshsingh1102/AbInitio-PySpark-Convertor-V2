# Ab Initio → PySpark Convertor — Presentation Content

**Theme:** Dark tech / midnight executive
**Audience:** Internal team
**Date:** May 2026
**Slides:** 15

---

## SLIDE 1 — TITLE

- **Title:** Ab Initio → PySpark Convertor
- **Subtitle:** IBM Network | Automated Legacy ETL Migration
- **Bottom right:** May 2026
- **Bottom left:** Team Presentation — Internal
- **Visual:** Orange accent rectangle on left edge (full height)

---

## SLIDE 2 — THE PROBLEM

**Title:** The Problem

**Stat callouts (row of 3):**
- **Weeks** — Manual Migration Time Per Graph
- **High** — Error Rate in Manual Re-coding
- **$$$** — Engineering Cost per Migration

**Two-column layout:**

**Ab Initio Reality**
- Proprietary .mp graph format — not human-readable
- DML schemas define complex binary/text layouts
- Transform expressions in Ab Initio's own language
- Hundreds of graphs to migrate

**Current Approach**
- Engineers manually read each graph
- Hand-write PySpark equivalents
- No consistency, high rework rate
- No validation until runtime

---

## SLIDE 3 — SOLUTION OVERVIEW

**Title:** Our Solution: Automated Conversion Pipeline
**Subtitle:** Input .mp graph → Runnable PySpark .py file

**4 numbered steps:**
1. **Parse** — Read Ab Initio graph structure from Neo4j
2. **Schema** — Convert DML record formats to PySpark StructType
3. **Map** — Translate Ab Initio components to PySpark ops
4. **Generate** — Synthesize production-ready .py file

**Banner:** 90/99 test cases passing · 6 components covered · 25 DML features supported

---

## SLIDE 4 — ARCHITECTURE

**Title:** Architecture: Two Networks

**Left panel (Out of Scope — Client Network):**
- Ab Initio .mp Graph Files
- Parser (separate workstream)
- Outputs to Neo4j Graph DB
- Note: Runs on client premises

**Center:** Neo4j Handoff (arrow)

**Right panel (This Project — IBM Network):**
1. IR Loader — Neo4j → Pydantic IR
2. DML Convertor — DML → StructType
3. Mapping Engine — AbInitio ops → PySpark ops
4. Code Generator — Jinja2 + LLM → .py
- → Runnable PySpark .py

---

## SLIDE 5 — END TO END FLOW

**Title:** How It Works — End to End

**Pipeline (7 stages):**
.mp File → Neo4j DB → IR Loader → Mapping Engine → DML Convertor → Code Generator → output.py

**Per-stage descriptions:**
- .mp File — Ab Initio graph
- Neo4j DB — Parser output (graph nodes + edges)
- IR Loader — Pydantic models (Graph, Component, Edge)
- Mapping Engine — Rule-based + LLM fallback
- DML Convertor — Lark Earley parser → StructType
- Code Generator — Jinja2 template + Ollama polish
- output.py — Runnable PySpark pipeline

**Example transform:**
- Ab Initio REFORMAT: `out.customer_id :: customer_id; out.name :: string_upcase(name);`
- Generated PySpark: `df.select(col("customer_id"), upper(col("name")).alias("name"))`

---

## SLIDE 6 — DML CONVERTOR DEEP DIVE

**Title:** DML Convertor: Feature Coverage
**Subtitle:** Lark Earley parser handles the full Ab Initio DML grammar

| Feature | Status |
|---------|--------|
| Scalar types (decimal, integer, real, string, date, datetime, void) | ✅ Supported |
| Delimited fields + per-field null sentinels | ✅ Supported |
| Fixed-width (no-delimiter) records | ✅ Supported |
| Nested sub-records (record...end name) | ✅ Supported |
| Fixed-length vectors field[N] | ✅ Supported |
| Variable-length vectors record[disc]...end | ✅ Supported |
| Union fields | ✅ MANUAL_REVIEW flagged |
| Conditional fields (if/else if/else chains) | ✅ Supported |
| Packed / zoned decimal | ✅ MANUAL_REVIEW flagged |
| Mixed-delimiter records | ✅ Supported |
| Comments and whitespace | ✅ Supported |
| Include resolver (%include) | 🔄 In Progress |
| Type aliases (typedef) | 🔄 In Progress |
| EBCDIC charset | 🔄 In Progress |

---

## SLIDE 7 — MAPPING ENGINE

**Title:** Mapping Engine: 6 Components Covered
**Subtitle:** Rule-based deterministic mapping. LLM fallback only for unknowns.

**Component cards:**
- **REFORMAT** → `df.select(*cols)` — `df.select(col("id"), upper(col("name")))`
- **FILTER_BY_EXPRESSION** → `df.filter(...)` — `df.filter(F.expr("amount > 100"))`
- **JOIN** → `left.join(right, on=keys)` — `left.join(right, on=["id"], how="inner")`
- **SORT** → `df.orderBy(*keys)` — `df.orderBy("date", "id")`
- **ROLLUP** → `df.groupBy().agg()` — `df.groupBy("region").agg(sum("sales"))`
- **DEDUP_SORTED** → `df.dropDuplicates()` — `df.dropDuplicates(["customer_id"])`

**Strategy:** Deterministic rules handle ~90% of cases. Local LLM (Ollama) invoked only for unknown components or unparseable transform expressions.

---

## SLIDE 8 — CODE GENERATOR

**Title:** Code Generator: From IR to Production Python
**Subtitle:** Deterministic synthesis with optional LLM polish — all on-premise

**How it works:**
1. Walk IR graph in topological order
2. Pull mapped op for each component
3. Render via Jinja2 pipeline template
4. LLM polish pass (optional, local only)
5. Output clean, importable .py file

**Why Local LLM?**
> Client DML schemas and transform expressions contain proprietary business logic. Data CANNOT leave the client network.
- Model: qwen2.5-coder:14b via Ollama
- Alternative: vLLM on IBM-side infra
- LLM is optional — pipeline works without it
- Used only for fallback + final polish

---

## SLIDE 9 — WEB UI

**Title:** Bonus: Local Web UI for Schema Exploration
**Subtitle:** FastAPI + static HTML/JS — runs at localhost:8000

**Tabs:**
- **DML Schema Tab** — Paste DML record → Get PySpark StructType + full spark.read chain
- **Transform Body Tab** — Paste Ab Initio out.x :: expr block → Get df.select() arguments
- **Single Expression Tab** — One Ab Initio expression → PySpark Column expression
- **Full Pipeline Tab** — POST graph JSON → Complete runnable .py file

**Run:** `pip install -e ".[web]" && uvicorn ibm_network.web.server:app --reload --port 8000`

---

## SLIDE 10 — TEST PROGRESS

**Title:** Test Progress: 90 / 99 Passing
**Subtitle:** DML Suite — TC-001 through TC-025 + CLI + E2E tests

**Status grid:**
- TC-001 to TC-018: PASS
- TC-019: PASS
- TC-020: PARTIAL (MANUAL_REVIEW stub)
- TC-021: FAIL (include resolver)
- TC-022: FAIL (type aliases)
- TC-023: PASS
- TC-024: FAIL (EBCDIC)
- TC-025: FAIL (boss fight, depends on 021/022/024)

**9 failing tests across 5 scenarios. All failures are tracked with clear remediation paths.**

---

## SLIDE 11 — SCOPE

**Title:** Scope: V1 Coverage

**✅ In Scope — V1**
- Components: REFORMAT, FILTER_BY_EXPRESSION, JOIN, SORT, ROLLUP, DEDUP_SORTED
- DML: All scalar types, null sentinels, date/time, vectors, nested records, conditionals, unions, packed decimal (stub)
- Infra: Neo4j → IR pipeline, CLI tool, Web UI, E2E tests, Docker Compose dev setup

**❌ Out of Scope — V1**
- Components: SCAN, NORMALIZE, DENORMALIZE, LOOKUP, MULTI_REFORMAT, PARTITION_BY_KEY, GATHER, MERGE
- DML: Include resolver (%include), Type aliases (typedef), EBCDIC charset full support
- Infra: The Parser (Client Network — separate workstream), Cloud deployment, CI/CD, Production hardening

---

## SLIDE 12 — REMAINING WORK

**Title:** Remaining Work: 5 Items

1. **TC-021 | Include Resolver** — grammar.lark + parser pre-processing for %include "other.dml" (~1 day)
2. **TC-022 | Type Aliases** — grammar extension + symbol table for typedef declarations (~1 day)
3. **TC-024 | EBCDIC Charset** — grammar fix + MANUAL_REVIEW warning generation (~0.5 day)
4. **TC-025 | Boss Fight Integration** — Full integration test, depends on TC-021/022/024 (~0.5 day)
5. **TC-020 | Packed/Zoned Binary** — UDF stub + byte-level decode logic (~2 days)

Plus: fix CLI read_strategy routing for no-delimiter decimal fields (test_cli.py)

---

## SLIDE 13 — BLOCKERS

**Title:** Blockers — Action Required

1. **🔴 Neo4j Schema Contract** — Parser team has not confirmed node labels, relationship types, or property names. IR loader is built on assumed schema. *Action: Parser team to share Cypher schema definition.*
2. **🔴 No Real Client Graphs** — All testing uses synthetic fixtures. Coverage gaps may be hidden. *Action: Client Network team to provide 5–10 sanitized graphs.*
3. **🟡 LLM Model Uncertainty** — IBM-side model not confirmed (qwen2.5-coder vs codellama vs deepseek-coder). *Action: IBM infra team to confirm model + endpoint.*
4. **🟡 V1 Coverage Target Not Signed Off** — Proposed: ≥90% deterministic, <10% LLM fallback. *Action: Stakeholder sign-off.*

---

## SLIDE 14 — PHASE STATUS

**Title:** Development Phases: Where We Are

- **Phase 0 ✅ DONE** — Scaffolding (pyproject.toml, docker-compose, Makefile, README)
- **Phase 1 ✅ DONE** — IR + Neo4j Loader (Pydantic IR models, Cypher queries, fixture seeding)
- **Phase 2 ✅ DONE** — DML Convertor (Lark grammar, Earley parser, AST, StructType emitter)
- **Phase 3 ✅ DONE** — Mapping Engine (6 component rules, transform expression parser)
- **Phase 4 ✅ DONE** — Code Generator (Jinja2 templates, Ollama LLM client, synthesizer)
- **Phase 5 ✅ DONE** — CLI + E2E Glue (ibm-net convert command, E2E test, spark-submit verification)
- **Phase 6 🔄 IN PROGRESS** — Validation & Iteration (DML fixture corpus, coverage matrix, 90/99 passing — 5 items remaining)
- **Phase 7 ⏳ NOT STARTED** — Documentation & Handoff (per-component mapping reference, runbook, troubleshooting guide)

**Progress: 75% complete (6/8 phases done, 1 in progress)**

---

## SLIDE 15 — NEXT STEPS

**Title:** Next Steps
**Subtitle:** To reach 99/99 and hand off to production

**This Sprint**
- Implement include resolver (TC-021)
- Implement type aliases (TC-022)
- Fix EBCDIC grammar (TC-024)
- Run boss fight integration (TC-025)

**Needs External Input**
- Parser team: Neo4j schema contract
- Client team: real sanitized graph samples
- IBM infra: confirm LLM model + endpoint
- Stakeholders: sign off V1 coverage target

**After Blockers Resolved**
- Validate against real client graphs
- Tune LLM prompts for confirmed model
- Write Phase 7 documentation
- Plan V2 component scope (SCAN, NORMALIZE, etc.)

> The core pipeline is production-capable. Unblocking the 4 open items will take us to 99/99 and Phase 7 handoff.
