# Ab Initio → PySpark Conversion Platform

A graph-native dataflow compiler. Parses production Ab Initio
`.mp` / `.dml` / `.xfr` files, stores the pipeline DAG in Neo4j as the
source of truth, derives an intermediate representation from the graph,
and emits production PySpark + KSH wrappers.

```
.mp / .dml / .xfr
      │  (preprocess: --comments, escape <, interpolate ${VAR})
      ▼
   Parser ──► Neo4j (DAG, schemas, params, transform blocks)
                  │
                  ▼
            IR Builder ──► PySpark codegen (plugin registry)
                                          │
                                          ▼
                                   spark-submit
```

## Component coverage (Common-20)

The platform ships with 22 component plugins covering ~95% of real ETL:

| Category | Components |
|---|---|
| Datasets | InputFile, OutputFile, LookupFile, IntermediateFile, Trash |
| Transforms | Reformat, Filter, Sort, SortWithinGroups, DedupSorted |
| Aggregates | Rollup / Aggregate, Scan, Normalize, DenormalizeSorted |
| Joins | Join, Lookup, MatchSorted |
| Topology | Replicate (fan-out), Gather / Concatenate (fan-in) |
| Side effects | RunProgram |

Adding a new component is one file under [backend/components/](backend/components/) — implement the `ComponentPlugin` ABC and the plugin registers itself on import.

## Dialect support

The parsers handle production Ab Initio syntax:

- `.mp`: top-level `<component>`, `<connections><edge/>`, `<property name=.. value=..>`, `<port type=.. source=..>`, `<parameters>` block + `${VAR}` interpolation, named ports (`in_left`/`in_right`), unescaped `<`/`<=` inside attribute values.
- `.dml`: `--` line comments, `DEFINE name BEGIN … END`, multiple definitions per file, `NOT NULL` / `NULL` two-token modifiers.
- `.xfr`: `--` comments, `TRANSFORM name BEGIN … END` and `FILTER name BEGIN CONDITION: expr; END` blocks, single-`=` equality, string `+` lowered to `CONCAT`, `decimal()`/`string_to_date()`/`string_to_datetime()`/`date_diff()` mapped to Spark equivalents, format-string translation (`YYYY-MM-DD` → `yyyy-MM-dd`), `else if` chains, `out.X` self-references (emitted as a `withColumn` chain).

## Quick start (Docker)

```bash
docker compose up --build
```

- Frontend → http://localhost:3000
- API      → http://localhost:8000/docs
- Neo4j    → http://localhost:7474  (`neo4j` / `password`)

## Local dev

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn backend.api.main:app --reload --app-dir ..
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Tests

```bash
python -m pytest backend/tests/unit          # always runs (~75 tests)
python -m pytest backend/tests/integration   # runs PySpark jobs locally
python -m pytest backend/tests/graph         # requires Neo4j
```

The integration suite includes a real PySpark execution of the
`examples/complex_pipeline/` (13 components, fan-out, joins, aggregations,
self-references) and verifies the resulting parquet output.

## Pipeline lifecycle

1. **POST /upload** — drop `.mp` / `.dml` / `.xfr`; receive `job_id`.
2. **POST /parse** — emit structured AST (interpolated, schemas resolved).
3. **POST /store** — ingest the AST into Neo4j (idempotent MERGE).
4. **GET  /graph/{id}** — full DAG (drives the frontend visualization).
5. **GET  /graph/{id}/order** — topologically sorted execution order.
6. **POST /generate-code** — IR build + emit `pipeline.py` + `pipeline.ksh`.
7. **GET  /download/{id}** — bundle as zip.
8. **POST /execute/{id}** — run the `.ksh`, stream logs over SSE.

## Examples

- `examples/simple_pipeline/` — `Input → Reformat → Filter → Output`
- `examples/complex_pipeline/` — 13-component pipeline with two CSV inputs,
  normalization, inner join, fan-out to high-value/standard/audit branches,
  loyalty-tier discount logic, and aggregation. Used as the integration
  test golden case.

## Adding a new component

1. Create `backend/components/<your_component>.py`.
2. Subclass `ComponentPlugin`, set `component_type` and `ir_type`, implement `emit_pyspark`.
3. Decorate the class with `@register`.
4. Add a fixture and test under `backend/tests/unit/test_components.py`.

That's it — the registry auto-discovers it on import.
