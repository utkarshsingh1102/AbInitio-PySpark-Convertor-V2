# Ab Initio → PySpark Conversion Platform (Neo4j-Backed)
## Claude Code Execution Plan

---

## 🧠 Mental Model (Lock This First)

```
Ab Initio:   .mp (graph) → compiled → .ksh → executed by Co>Operating System
This System: .mp → parsed → Neo4j (Source of Truth) → IR → PySpark + .ksh → Spark Execution
```

You are building a **graph-native dataflow compiler**, not a simple converter.

- Ab Initio graphs are dataflow DAGs stored as structured metadata
- Neo4j is the **canonical representation** of every pipeline — not just storage
- IR is derived FROM Neo4j graph queries, not from the parser directly
- Get the Neo4j schema + IR builder right and everything else is mechanical

---

## 🏗️ System Architecture

```
Frontend (Next.js)
        ↓
Backend API (FastAPI)
        ↓
┌──────────────────────────────────────────────┐
│  Parser Layer (.mp / .dml / .xfr)            │
└──────────────────────┬───────────────────────┘
                       ↓
┌──────────────────────────────────────────────┐
│  Neo4j Graph DB  ← Pipeline DAG lives here   │
└──────────────────────┬───────────────────────┘
                       ↓
┌──────────────────────────────────────────────┐
│  IR Builder  (reads from Neo4j via Cypher)   │
└──────────────────────┬───────────────────────┘
                       ↓
┌──────────────────────────────────────────────┐
│  Code Generator  →  PySpark + .ksh           │
└──────────────────────┬───────────────────────┘
                       ↓
              Execution Engine (spark-submit)
```

---

## 📁 Project Structure

```
abinitio-spark/
├── backend/
│   ├── api/
│   │   ├── main.py
│   │   └── routes/
│   │       ├── upload.py
│   │       ├── parse.py
│   │       ├── graph.py          # Neo4j store + query endpoints
│   │       ├── convert.py
│   │       ├── download.py
│   │       └── execute.py
│   ├── parser/
│   │   ├── mp_parser.py          # .mp → components + edges dict
│   │   ├── dml_parser.py         # .dml → StructType schema
│   │   └── xfr_parser.py         # .xfr → transform AST (Lark)
│   ├── graph/
│   │   ├── client.py             # Neo4j driver setup
│   │   ├── ingestion.py          # Parsed output → Cypher INSERT
│   │   └── queries.py            # Cypher query library
│   ├── ir/
│   │   ├── builder.py            # Neo4j graph → IRNode list
│   │   └── models.py             # IRNode dataclasses
│   ├── codegen/
│   │   ├── pyspark_gen.py        # IR → PySpark code
│   │   └── ksh_gen.py            # IR → .ksh wrapper
│   ├── executor/
│   │   └── spark_runner.py       # Trigger .ksh, stream logs
│   └── tests/
│       ├── unit/
│       ├── graph/
│       └── integration/
├── frontend/
│   ├── pages/
│   │   ├── index.tsx             # Upload page
│   │   └── results/[job_id].tsx  # DAG + code view
│   └── components/
│       ├── FileUpload.tsx
│       ├── DAGViewer.tsx         # Driven by Neo4j graph data
│       └── CodePreview.tsx
├── examples/
│   └── simple_pipeline/          # Input → Reformat → Filter → Output
├── docker-compose.yml            # FastAPI + Neo4j + Next.js
└── README.md
```

---

## 🔢 Phase 1 — Parser Layer

### 1.1 `.mp` Graph Parser (`backend/parser/mp_parser.py`)

**Goal:** Parse Ab Initio `.mp` XML-like structure → Python dict of components and edges.

**Output shape:**
```python
{
    "pipeline": {"name": "customer_pipeline"},
    "nodes": [
        {"id": "node_1", "name": "Input",    "type": "InputFile",  "params": {...}},
        {"id": "node_2", "name": "Reformat", "type": "Reformat",   "params": {...}},
        {"id": "node_3", "name": "Filter",   "type": "Filter",     "params": {...}},
        {"id": "node_4", "name": "Output",   "type": "OutputFile", "params": {...}},
    ],
    "edges": [
        {"from": "node_1", "to": "node_2"},
        {"from": "node_2", "to": "node_3"},
        {"from": "node_3", "to": "node_4"},
    ]
}
```

**Tasks:**
- [ ] Parse node types: `InputFile`, `OutputFile`, `Reformat`, `Filter`, `Join`, `Aggregate`
- [ ] Extract component parameters and port connections
- [ ] Extract embedded transform expressions per node
- [ ] Return validated dict (Pydantic model)

---

### 1.2 `.dml` Schema Parser (`backend/parser/dml_parser.py`)

**Goal:** Convert Ab Initio DML schema → PySpark `StructType`.

**Type mapping:**

| DML Type      | PySpark Type      |
|---------------|-------------------|
| string(N)     | StringType()      |
| integer       | IntegerType()     |
| decimal(p,s)  | DecimalType(p,s)  |
| date          | DateType()        |
| datetime      | TimestampType()   |

**Tasks:**
- [ ] Support nullable fields
- [ ] Support decimal precision/scale
- [ ] Support nested records and arrays
- [ ] Output `StructType` object

---

### 1.3 `.xfr` Transform Parser (`backend/parser/xfr_parser.py`)

**Goal:** Parse Ab Initio transform expressions → PySpark column expressions using Lark.

**Conversion example:**
```
Ab Initio:  out.age = in.age + 1;
PySpark:    col("age") + lit(1)
```

**Tasks:**
- [ ] Define Lark grammar for `.xfr` expression syntax
- [ ] Handle arithmetic: `+`, `-`, `*`, `/`
- [ ] Handle comparisons: `>`, `<`, `==`, `!=`
- [ ] Handle string functions: `string_length`, `trim`, `upper`, `lower`
- [ ] Handle conditionals: `if/else`, `is_null`
- [ ] Return expression strings usable inside `.withColumn()` / `.filter()`

---

## 🔢 Phase 2 — Neo4j Graph Layer (Source of Truth)

### 2.1 Neo4j Data Model

**Node Labels:**
```cypher
(:Pipeline  { id: STRING, name: STRING })

(:Component {
    id:         STRING,
    name:       STRING,
    type:       STRING,   // InputFile | Reformat | Filter | Join | Aggregate | OutputFile
    properties: STRING    // JSON blob of component params
})

(:Schema {
    id:     STRING,
    fields: STRING        // JSON blob of StructType definition
})

(:Parameter {
    name:  STRING,
    value: STRING
})
```

**Relationship Types:**
```cypher
(:Pipeline)-[:HAS_COMPONENT]->(:Component)
(:Component)-[:FLOWS_TO]->(:Component)
(:Component)-[:USES_SCHEMA]->(:Schema)
(:Component)-[:USES_PARAM]->(:Parameter)
```

**Required Indexes:**
```cypher
CREATE INDEX component_id FOR (c:Component) ON (c.id);
CREATE INDEX pipeline_id  FOR (p:Pipeline)  ON (p.id);
```

---

### 2.2 Neo4j Ingestion (`backend/graph/ingestion.py`)

**Goal:** Take parsed output from Phase 1 and write it into Neo4j using MERGE (idempotent).

**Tasks:**
- [ ] `ingest_pipeline(pipeline_dict)` — creates Pipeline node
- [ ] `ingest_components(nodes)` — MERGE each Component node
- [ ] `ingest_edges(edges)` — create FLOWS_TO relationships
- [ ] `ingest_schema(node_id, struct_type)` — attach Schema node
- [ ] All writes use MERGE, not CREATE (safe for re-runs)

**Example Cypher:**
```cypher
MERGE (c:Component {id: $id})
SET c.name = $name, c.type = $type, c.properties = $properties

MERGE (a:Component {id: $from_id})
MERGE (b:Component {id: $to_id})
MERGE (a)-[:FLOWS_TO]->(b)
```

---

### 2.3 Cypher Query Library (`backend/graph/queries.py`)

**Goal:** All graph intelligence lives here as named query functions.

**Required queries:**
```python
# 1. Full pipeline DAG
def get_pipeline_dag(pipeline_id: str) -> list[dict]:
    # MATCH (p:Pipeline {id: $id})-[:HAS_COMPONENT]->(c)
    # OPTIONAL MATCH (c)-[:FLOWS_TO]->(next)
    # RETURN c, next

# 2. Execution order (topological from root)
def get_execution_order(pipeline_id: str) -> list[dict]:
    # MATCH path = (start)-[:FLOWS_TO*]->(end)
    # WHERE NOT ()-[:FLOWS_TO]->(start)
    # RETURN path

# 3. Root node detection (no incoming edges)
def get_root_nodes(pipeline_id: str) -> list[dict]:
    # MATCH (c:Component) WHERE NOT ()-[:FLOWS_TO]->(c) RETURN c

# 4. Leaf node detection (no outgoing edges)
def get_leaf_nodes(pipeline_id: str) -> list[dict]:
    # MATCH (c:Component) WHERE NOT (c)-[:FLOWS_TO]->() RETURN c

# 5. Downstream impact analysis
def get_downstream(component_name: str) -> list[dict]:
    # MATCH (c:Component {name: $name})-[:FLOWS_TO*]->(n) RETURN n

# 6. Cycle detection (must run before IR build)
def detect_cycles(pipeline_id: str) -> bool:
    # MATCH (c:Component)-[:FLOWS_TO*]->(c) RETURN count(c) > 0
```

---

## 🔢 Phase 3 — IR Layer (Derived from Neo4j)

### 3.1 IR Models (`backend/ir/models.py`)

```python
from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class IRNode:
    id:      str
    type:    str          # read | transform | filter | join | aggregate | write
    inputs:  List[str]    # upstream node IDs
    outputs: List[str]    # downstream node IDs
    schema:  Any          # StructType
    config:  Dict         # operation-specific params
```

**Type mappings:**

| IRNode Type  | Ab Initio Component |
|--------------|---------------------|
| `read`       | InputFile           |
| `transform`  | Reformat            |
| `filter`     | Filter              |
| `join`       | Join                |
| `aggregate`  | Rollup / Aggregate  |
| `write`      | OutputFile          |

---

### 3.2 IR Builder (`backend/ir/builder.py`)

**Goal:** Query Neo4j for execution-ordered nodes → produce `list[IRNode]`.

**Process:**
1. Call `detect_cycles()` — raise if cycles found
2. Call `get_execution_order(pipeline_id)` — topologically sorted nodes
3. For each node, resolve StructType schema via `USES_SCHEMA` relationship
4. Attach parsed transform config from `Component.properties`
5. Return ordered `list[IRNode]`

**Tasks:**
- [ ] `build_ir(pipeline_id) -> list[IRNode]`
- [ ] Schema resolution at every node boundary
- [ ] Raise `CyclicGraphError` if cycle detected
- [ ] Log unmapped component types as warnings (don't fail silently)

---

## 🔢 Phase 4 — Code Generation

### 4.1 PySpark Generator (`backend/codegen/pyspark_gen.py`)

**Goal:** Walk `list[IRNode]` in execution order → emit a single `pipeline.py`.

**Component mapping:**

| IRNode Type  | PySpark Output                               |
|--------------|----------------------------------------------|
| `read`       | `df = spark.read.parquet(input_path)`        |
| `transform`  | `df = df.withColumn("col", expr(...))`       |
| `filter`     | `df = df.filter(expr(condition))`            |
| `join`       | `df = df.join(df2, on=[...], how="inner")`   |
| `aggregate`  | `df = df.groupBy(...).agg(...)`              |
| `write`      | `df.write.mode("overwrite").parquet(out)`    |

**Tasks:**
- [ ] Emit SparkSession init boilerplate
- [ ] Enforce explicit schema on reads (no inference)
- [ ] Track DataFrame variable names per node ID (required for multi-input joins)
- [ ] Output as single `pipeline.py` string

---

### 4.2 KSH Generator (`backend/codegen/ksh_gen.py`)

**Goal:** Wrap generated PySpark script in a production `.ksh` execution wrapper.

**Output template:**
```bash
#!/bin/ksh
set -e

PIPELINE_NAME="${PIPELINE_NAME:-pipeline}"
INPUT_FILE="${INPUT_FILE:-data/input}"
OUTPUT_FILE="${OUTPUT_FILE:-data/output}"
LOG_FILE="logs/${PIPELINE_NAME}_$(date +%Y%m%d_%H%M%S).log"

echo "[$(date)] Starting: $PIPELINE_NAME" | tee -a "$LOG_FILE"

spark-submit \
  --master local[*] \
  pipeline.py \
    --input  "$INPUT_FILE" \
    --output "$OUTPUT_FILE" \
  2>&1 | tee -a "$LOG_FILE"

EXIT_CODE=$?
[ $EXIT_CODE -ne 0 ] && echo "[$(date)] FAILED: $EXIT_CODE" | tee -a "$LOG_FILE" && exit $EXIT_CODE
echo "[$(date)] Completed successfully" | tee -a "$LOG_FILE"
```

**Tasks:**
- [ ] Inject pipeline name + paths from Neo4j-stored parameters
- [ ] Add retry logic (configurable attempts)
- [ ] Support `spark-submit` flags for cluster mode (EMR / Databricks)

---

## 🔢 Phase 5 — FastAPI Backend

### API Endpoints

```
POST /upload              → Accept .mp, .dml, .xfr; store to /tmp/{job_id}/; return job_id
POST /parse               → Run parser on job_id files; return raw GraphAST
POST /store               → Ingest GraphAST into Neo4j; return pipeline_id
GET  /graph/{id}          → Return DAG nodes + edges from Neo4j (for frontend)
GET  /graph/{id}/order    → Return topologically sorted execution order
POST /generate-code       → IR build from Neo4j + codegen; return PySpark + KSH
GET  /download/{id}       → Download .py + .ksh as zip
POST /execute/{id}        → Run .ksh; stream logs via SSE
GET  /logs/{id}           → Return execution logs
```

**Tasks:**
- [ ] Pydantic v2 request/response models for all endpoints
- [ ] File validation (only `.mp`, `.dml`, `.xfr`)
- [ ] Neo4j client injected as FastAPI dependency (`Depends`)
- [ ] `/execute` uses Server-Sent Events (SSE) to stream log lines in real time

---

## 🔢 Phase 6 — Next.js Frontend

### Pages & Components

**`/` — Upload Page**
- [ ] Drag-and-drop upload for `.mp`, `.dml`, `.xfr`
- [ ] Sequential calls: `/upload` → `/parse` → `/store`
- [ ] Redirect to `/results/[job_id]` on success

**`/results/[job_id]` — Results Page**
- [ ] `DAGViewer` — render graph from `GET /graph/{id}` using `react-flow`; nodes colored by component type
- [ ] Execution order panel (from `GET /graph/{id}/order`)
- [ ] `CodePreview` — syntax-highlighted PySpark (`prism-react-renderer`)
- [ ] Download buttons for `.py` and `.ksh`
- [ ] "Run Pipeline" → POST `/execute/{id}` → stream logs to terminal panel

**Tasks:**
- [ ] Next.js 14 app router + Tailwind CSS
- [ ] `lib/api.ts` — typed API client for all FastAPI calls
- [ ] Error boundaries and loading skeletons on all async operations

---

## 🔢 Phase 7 — Testing

### Unit Tests (`backend/tests/unit/`)
- [ ] `test_mp_parser.py` — parse sample `.mp` → assert correct nodes/edges
- [ ] `test_dml_parser.py` — parse sample `.dml` → assert correct StructType
- [ ] `test_xfr_parser.py` — parse transform expressions → assert PySpark expressions

### Graph Tests (`backend/tests/graph/`)
- [ ] `test_ingestion.py` — ingest parsed dict → assert correct nodes/edges in Neo4j
- [ ] `test_queries.py` — execution order query returns correct topological sort
- [ ] `test_cycle_detection.py` — cyclic graph raises `CyclicGraphError`

### Integration Tests (`backend/tests/integration/`)
- [ ] Golden test: `Input → Reformat → Filter → Output`
  - Uploads `.mp` + `.dml` + `.xfr`
  - Verifies Neo4j has correct 4-node DAG
  - Verifies generated PySpark runs without error
  - Verifies `.ksh` script has correct parameters

### Test Data (`examples/simple_pipeline/`)
- [ ] Minimal `.mp` for `Input → Reformat → Filter → Output`
- [ ] Matching `.dml` with 4–5 fields
- [ ] Matching `.xfr` with one field transform + one filter condition

---

## 🔢 Phase 8 — Infrastructure

### `docker-compose.yml`

```yaml
services:
  neo4j:
    image: neo4j:5
    ports: ["7474:7474", "7687:7687"]
    environment:
      NEO4J_AUTH: neo4j/password

  backend:
    build: ./backend
    ports: ["8000:8000"]
    depends_on: [neo4j]
    environment:
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_USER: neo4j
      NEO4J_PASSWORD: password

  frontend:
    build: ./frontend
    ports: ["3000:3000"]
    depends_on: [backend]
    environment:
      NEXT_PUBLIC_API_URL: http://backend:8000
```

**Tasks:**
- [ ] Dockerfile for FastAPI backend
- [ ] Dockerfile for Next.js frontend
- [ ] Neo4j startup script to create indexes on first run

---

## ⚠️ Known Engineering Challenges

| Risk                           | Mitigation                                               |
|-------------------------------|----------------------------------------------------------|
| Complex `.xfr` transforms      | Lark grammar; log unmapped expressions as warnings       |
| Schema mismatch between nodes  | Strict StructType validation at each IR node boundary    |
| Cyclic graphs in `.mp`         | `detect_cycles` Cypher query before IR build             |
| Spark vs Ab Initio ordering    | Flag order-sensitive nodes in IR; emit `.orderBy()`      |
| Ab Initio explicit parallelism | Map `dop` param to `repartition()` hint in codegen       |

---

## 🧱 Tech Stack

| Layer      | Technology                          |
|------------|-------------------------------------|
| Backend    | Python 3.11, FastAPI, Pydantic v2   |
| Graph DB   | Neo4j 5 (driver: `neo4j` Python pkg)|
| Parser     | Lark (transform grammar)            |
| Spark      | PySpark 3.5                         |
| Frontend   | Next.js 14, Tailwind CSS            |
| DAG UI     | react-flow                          |
| Infra      | Docker, docker-compose              |

---

## 🚀 Build Order (Recommended)

```
Phase 1 (Parsers)
    ↓
Phase 2 (Neo4j Schema + Ingestion)
    ↓
Phase 3 (IR Builder from Neo4j)
    ↓
Phase 4 (Code Generation)
    ↓
Phase 7 (Tests alongside each phase)
    ↓
Phase 5 (FastAPI)
    ↓
Phase 6 (Frontend)
    ↓
Phase 8 (Docker infra)
```

Drive every phase around making the golden test case work first:
**`Input → Reformat → Filter → Output`** — end-to-end, before expanding component coverage.

---

## ✅ MVP Definition

MVP is complete when:
1. `.mp` / `.dml` / `.xfr` files upload and parse correctly
2. Pipeline DAG is stored in Neo4j with correct nodes, edges, and schemas
3. IR is built from Neo4j graph queries (not from parser directly)
4. Valid, runnable PySpark code is generated
5. A production `.ksh` wrapper is generated with correct parameters
6. Spark job runs locally and produces correct output
7. All of the above accessible through the web UI with DAG visualization driven from Neo4j
