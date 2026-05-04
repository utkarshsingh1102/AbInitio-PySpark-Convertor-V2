You are creating a professional PowerPoint presentation for the Ab Initio → PySpark Convertor project. Save it to /Users/utkarshsingh/Desktop/AbInitio-PySpark-Presentation.pptx

Use pptxgenjs (Node.js) to create from scratch. The skill base directory is: /Users/utkarshsingh/Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin/e5e635dd-c05f-468a-8add-f4c140c322ec/23679e57-09f7-47ca-8df0-285ea9db11ba/skills/pptx

First read the pptxgenjs.md file in that directory to understand how to use the tool.

DESIGN THEME: Dark tech / premium midnight executive
- Primary background: #0D1117 (near-black)
- Card/panel color: #161B22 (dark navy)
- Accent: #F97316 (orange — IBM/tech feel)
- Secondary accent: #3B82F6 (blue)
- Success green: #22C55E
- Warning: #EAB308 (yellow)
- Text primary: #F0F6FC (near-white)
- Text muted: #8B949E
- Font: Calibri (headers bold 36-44pt, body 14-16pt)

15 SLIDES:

---
SLIDE 1 — TITLE (dark, full bleed)
Title: "Ab Initio → PySpark Convertor"
Subtitle: "IBM Network | Automated Legacy ETL Migration"
Bottom right: "May 2026"
Bottom left: "Team Presentation — Internal"
Orange accent rectangle on left edge (full height, 0.15" wide)

---
SLIDE 2 — THE PROBLEM
Title: "The Problem"
3 large stat callouts in a row:
- "Weeks" label "Manual Migration Time Per Graph"
- "High" label "Error Rate in Manual Re-coding"  
- "$$$" label "Engineering Cost per Migration"

Below: two-column layout
Left column header: "Ab Initio Reality"
Bullets:
• Proprietary .mp graph format — not human-readable
• DML schemas define complex binary/text layouts
• Transform expressions in Ab Initio's own language
• Hundreds of graphs to migrate

Right column header: "Current Approach"
Bullets:
• Engineers manually read each graph
• Hand-write PySpark equivalents
• No consistency, high rework rate
• No validation until runtime

---
SLIDE 3 — SOLUTION OVERVIEW
Title: "Our Solution: Automated Conversion Pipeline"
Large centered subtitle: "Input .mp graph → Runnable PySpark .py file"

4 numbered cards in a row (orange numbers):
1. "Parse" — Read Ab Initio graph structure from Neo4j
2. "Schema" — Convert DML record formats to PySpark StructType
3. "Map" — Translate Ab Initio components to PySpark ops
4. "Generate" — Synthesize production-ready .py file

Bottom banner (orange background): "90/99 test cases passing · 6 components covered · 25 DML features supported"

---
SLIDE 4 — ARCHITECTURE
Title: "Architecture: Two Networks"

Two large side-by-side panels separated by an arrow:

LEFT PANEL (muted/grey border — "out of scope"):
Header: "Client Network" (grey text)
Label: "OUT OF SCOPE"
Contents:
• Ab Initio .mp Graph Files
• Parser (separate workstream)
• Outputs to Neo4j Graph DB
Note: "Runs on client premises"

CENTER: Large right arrow with "Neo4j Handoff" label

RIGHT PANEL (orange border — "this project"):
Header: "IBM Network" (orange text)
Label: "THIS PROJECT"
4 sub-boxes stacked:
① IR Loader — Neo4j → Pydantic IR
② DML Convertor — DML → StructType
③ Mapping Engine — AbInitio ops → PySpark ops
④ Code Generator — Jinja2 + LLM → .py

Bottom of right panel: "→ Runnable PySpark .py"

---
SLIDE 5 — END TO END FLOW
Title: "How It Works — End to End"

Horizontal flow diagram (7 steps with arrows):
[.mp File] → [Neo4j DB] → [IR Loader] → [Mapping Engine] → [DML Convertor] → [Code Generator] → [output.py]

Below each box, small italic description:
- ".mp File": Ab Initio graph
- "Neo4j DB": Parser output (graph nodes + edges)
- "IR Loader": Pydantic models (Graph, Component, Edge)
- "Mapping Engine": Rule-based + LLM fallback
- "DML Convertor": Lark Earley parser → StructType
- "Code Generator": Jinja2 template + Ollama polish
- "output.py": Runnable PySpark pipeline

Below the flow: Two-column example
Left: "Ab Initio REFORMAT transform body" — show `out.customer_id :: customer_id; out.name :: string_upcase(name);`
Right arrow → "Generated PySpark" — show `df.select(col("customer_id"), upper(col("name")).alias("name"))`

---
SLIDE 6 — DML CONVERTOR DEEP DIVE
Title: "DML Convertor: Feature Coverage"
Subtitle: "Lark Earley parser handles the full Ab Initio DML grammar"

Two-column feature table:
Left column — Feature, Right column — Status

Row 1: Scalar types (decimal, integer, real, string, date, datetime, void) | ✅ Supported
Row 2: Delimited fields + per-field null sentinels | ✅ Supported
Row 3: Fixed-width (no-delimiter) records | ✅ Supported
Row 4: Nested sub-records (record...end name) | ✅ Supported
Row 5: Fixed-length vectors field[N] | ✅ Supported
Row 6: Variable-length vectors record[disc]...end | ✅ Supported
Row 7: Union fields | ✅ MANUAL_REVIEW flagged
Row 8: Conditional fields (if/else if/else chains) | ✅ Supported
Row 9: Packed / zoned decimal | ✅ MANUAL_REVIEW flagged
Row 10: Mixed-delimiter records | ✅ Supported
Row 11: Comments and whitespace | ✅ Supported
Row 12: Include resolver (%include) | 🔄 In Progress
Row 13: Type aliases (typedef) | 🔄 In Progress
Row 14: EBCDIC charset | 🔄 In Progress

Use alternating row background colors. ✅ rows in green text, 🔄 rows in yellow text.

---
SLIDE 7 — MAPPING ENGINE
Title: "Mapping Engine: 6 Components Covered"
Subtitle: "Rule-based deterministic mapping. LLM fallback only for unknowns."

2x3 grid of component cards:
Each card: component name (orange, bold), arrow, PySpark equivalent (blue), then small code snippet

Card 1: REFORMAT → df.select(*cols) | `df.select(col("id"), upper(col("name")))`
Card 2: FILTER_BY_EXPRESSION → df.filter(...) | `df.filter(F.expr("amount > 100"))`
Card 3: JOIN → left.join(right, on=keys) | `left.join(right, on=["id"], how="inner")`
Card 4: SORT → df.orderBy(*keys) | `df.orderBy("date", "id")`
Card 5: ROLLUP → df.groupBy().agg() | `df.groupBy("region").agg(sum("sales"))`
Card 6: DEDUP_SORTED → df.dropDuplicates() | `df.dropDuplicates(["customer_id"])`

Bottom bar: "Strategy: Deterministic rules handle ~90% of cases. Local LLM (Ollama) invoked only for unknown components or unparseable transform expressions."

---
SLIDE 8 — CODE GENERATOR
Title: "Code Generator: From IR to Production Python"
Subtitle: "Deterministic synthesis with optional LLM polish — all on-premise"

Two columns:
Left: "How it works"
Steps (numbered):
1. Walk IR graph in topological order
2. Pull mapped op for each component
3. Render via Jinja2 pipeline template
4. LLM polish pass (optional, local only)
5. Output clean, importable .py file

Right: "Why Local LLM?" 
Orange callout box:
"Client DML schemas and transform expressions contain proprietary business logic. Data CANNOT leave the client network."
Below:
• Model: qwen2.5-coder:14b via Ollama
• Alternative: vLLM on IBM-side infra
• LLM is optional — pipeline works without it
• Used only for fallback + final polish

---
SLIDE 9 — WEB UI
Title: "Bonus: Local Web UI for Schema Exploration"
Subtitle: "FastAPI + static HTML/JS — runs at localhost:8000"

4 feature cards in a 2x2 grid:

Card 1 (blue icon): "DML Schema Tab"
Paste DML record → Get PySpark StructType + full spark.read chain

Card 2 (orange icon): "Transform Body Tab"  
Paste Ab Initio out.x :: expr block → Get df.select() arguments

Card 3 (green icon): "Single Expression Tab"
One Ab Initio expression → PySpark Column expression

Card 4 (purple icon): "Full Pipeline Tab"
POST graph JSON → Complete runnable .py file

Bottom: `pip install -e ".[web]" && uvicorn ibm_network.web.server:app --reload --port 8000`

---
SLIDE 10 — TEST PROGRESS
Title: "Test Progress: 90 / 99 Passing"
Subtitle: "DML Suite — TC-001 through TC-025 + CLI + E2E tests"

Large centered stat: "90" (huge, orange) "/" "99" (muted) with "tests passing" below

Below: TC grid — 5x5 grid of test case boxes (TC-001 to TC-025):
- TC-001 to TC-018: green background (PASS)
- TC-019: green (PASS)
- TC-020: yellow background (PARTIAL — MANUAL_REVIEW stub)
- TC-021: red background (FAIL — include resolver)
- TC-022: red background (FAIL — type aliases)
- TC-023: green (PASS)
- TC-024: red background (FAIL — EBCDIC)
- TC-025: red background (FAIL — boss fight, depends on 021/022/024)

Legend: Green = PASS, Yellow = Partial/Manual Review, Red = Failing

Bottom: "9 failing tests across 5 scenarios. All failures are tracked with clear remediation paths."

---
SLIDE 11 — WHAT'S COVERED VS NOT COVERED
Title: "Scope: V1 Coverage"

Two large panels side by side:

LEFT PANEL (green left border): "✅ In Scope — V1"
Ab Initio Components:
• REFORMAT, FILTER_BY_EXPRESSION, JOIN, SORT, ROLLUP, DEDUP_SORTED

DML Features:
• All scalar types, null sentinels, date/time, vectors, nested records, conditionals, unions, packed decimal (stub)

Infrastructure:
• Neo4j → IR pipeline, CLI tool, Web UI, E2E tests, Docker Compose dev setup

RIGHT PANEL (red left border): "❌ Out of Scope — V1"
Ab Initio Components:
• SCAN, NORMALIZE, DENORMALIZE, LOOKUP, MULTI_REFORMAT, PARTITION_BY_KEY, GATHER, MERGE

DML Features:
• Include resolver (%include), Type aliases (typedef), EBCDIC charset full support

Infrastructure:
• The Parser (Client Network — separate workstream), Cloud deployment, CI/CD pipeline, Production hardening

---
SLIDE 12 — REMAINING WORK
Title: "Remaining Work: 5 Items"

5 work-item cards, each with: ID badge (orange), title, what's needed, estimated effort

Card 1: TC-021 | Include Resolver
What: grammar.lark + parser pre-processing for %include "other.dml"
Effort: ~1 day

Card 2: TC-022 | Type Aliases  
What: grammar extension + symbol table for typedef declarations
Effort: ~1 day

Card 3: TC-024 | EBCDIC Charset
What: grammar fix + MANUAL_REVIEW warning generation
Effort: ~0.5 day

Card 4: TC-025 | Boss Fight Integration
What: Full integration test — depends on TC-021/022/024 first
Effort: ~0.5 day after blockers resolved

Card 5: TC-020 | Packed/Zoned Binary
What: UDF stub + byte-level decode logic (intentionally hard)
Effort: ~2 days (+ domain expertise on sign nibble conventions)

Bottom note: "Plus: fix CLI read_strategy routing for no-delimiter decimal fields (test_cli.py)"

---
SLIDE 13 — BLOCKERS
Title: "Blockers — Action Required"

4 blocker cards, each with: number badge, title, description, owner/action needed

Blocker 1 (red badge): "Neo4j Schema Contract"
Parser team has not confirmed node labels, relationship types, or property names. IR loader is built on assumed schema — could break when real Parser output arrives.
Action: Parser team to share Cypher schema definition

Blocker 2 (red badge): "No Real Client Graphs"
All testing uses hand-crafted synthetic fixtures. No sanitized real Ab Initio graphs from client yet. Coverage gaps may be hidden.
Action: Client Network team to provide 5-10 sanitized graph examples

Blocker 3 (yellow badge): "LLM Model Uncertainty"
Which model is available on IBM-side infra not confirmed (qwen2.5-coder vs codellama vs deepseek-coder). Prompts and fallback logic may need tuning per model.
Action: IBM infra team to confirm available model + endpoint

Blocker 4 (yellow badge): "V1 Coverage Target Not Signed Off"
Proposed target: ≥90% deterministic, <10% LLM fallback. Not formally agreed with stakeholders. Without this, "done" has no definition.
Action: Stakeholder sign-off needed

---
SLIDE 14 — PHASE STATUS
Title: "Development Phases: Where We Are"

Vertical timeline / phase list (8 phases):

Phase 0 ✅ DONE — Scaffolding
pyproject.toml, docker-compose, Makefile, README

Phase 1 ✅ DONE — IR + Neo4j Loader
Pydantic IR models, Cypher queries, fixture seeding

Phase 2 ✅ DONE — DML Convertor
Lark grammar, Earley parser, AST, StructType emitter

Phase 3 ✅ DONE — Mapping Engine
6 component rules, transform expression parser (Lark)

Phase 4 ✅ DONE — Code Generator
Jinja2 templates, Ollama LLM client, synthesizer

Phase 5 ✅ DONE — CLI + E2E Glue
ibm-net convert command, E2E test, spark-submit verification

Phase 6 🔄 IN PROGRESS — Validation & Iteration
DML fixture corpus, coverage matrix, 90/99 passing — 5 items remaining

Phase 7 ⏳ NOT STARTED — Documentation & Handoff
Per-component mapping reference, runbook, troubleshooting guide

Progress bar: 75% complete (6/8 phases done, 1 in progress)

---
SLIDE 15 — NEXT STEPS
Title: "Next Steps"
Subtitle: "To reach 99/99 and hand off to production"

3-column layout:

Column 1: "This Sprint"
• Implement include resolver (TC-021)
• Implement type aliases (TC-022)  
• Fix EBCDIC grammar (TC-024)
• Run boss fight integration (TC-025)

Column 2: "Needs External Input"
• Parser team: Neo4j schema contract
• Client team: real sanitized graph samples
• IBM infra: confirm LLM model + endpoint
• Stakeholders: sign off V1 coverage target

Column 3: "After Blockers Resolved"
• Validate against real client graphs
• Tune LLM prompts for confirmed model
• Write Phase 7 documentation
• Plan V2 component scope (SCAN, NORMALIZE, etc.)

Bottom: Large orange call-to-action box:
"The core pipeline is production-capable. Unblocking the 4 open items will take us to 99/99 and Phase 7 handoff."
