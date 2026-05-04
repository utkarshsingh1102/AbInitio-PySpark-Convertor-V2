# PySpark Code Generation — Production Optimization Framework
## Claude Code Execution Plan (Optimizer Layer — Pipeline-Agnostic)

---

## 🎯 Objective

Build a rule-based optimizer that sits between the IR Builder and the PySpark
Code Generator. It must improve **any** generated pipeline regardless of what
Ab Initio components are present. Every rule must apply universally — not to a
specific pipeline shape.

The optimizer operates at two levels:

```
IR Optimizer     → works on list[IRNode] before codegen
                   (structural: reorder, merge, tag, annotate)

Expression Rewriter → works on individual expression strings inside IRNode.config
                      (syntactic: fix, replace, type-annotate expressions)
```

---

## 🏗️ Optimizer Architecture

```
list[IRNode]  (raw, from IR Builder)
      ↓
┌─────────────────────────────────────────────────────┐
│  STAGE 1 — Structural IR Optimizations              │
│                                                     │
│  S1: EarlyFilterPushdown                            │
│  S2: ProjectionPruning                              │
│  S3: FanOutCacheAnnotation                          │
│  S4: JoinStrategyAnnotation                         │
│  S5: CollapseConsecutiveTransforms                  │
│  S6: EliminatePassthroughNodes                      │
└────────────────────────┬────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────┐
│  STAGE 2 — Expression-Level Rewrites                │
│                                                     │
│  E1: StripIdentityAssignments                       │
│  E2: FixDateTimeExpressions                         │
│  E3: TypeNullLiterals                               │
│  E4: RewriteUDFsToNativeFunctions                   │
│  E5: NullSafeComparisonRewrite                      │
│  E6: DeduplicateCommonSubexpressions                │
└────────────────────────┬────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────┐
│  STAGE 3 — Write & Runtime Annotations              │
│                                                     │
│  W1: CoalesceBeforeWrite                            │
│  W2: PartitionByAnnotation                          │
│  W3: StorageLevelSelection                          │
│  W4: RepartitionBeforeShuffleJoin                   │
└────────────────────────┬────────────────────────────┘
                         ↓
   list[IRNode]  (fully optimized + annotated)
                         ↓
            PySpark Code Generator
```

---

## 📁 Project Structure

```
backend/
├── codegen/
│   ├── optimizer.py                  # Stage runner — executes all rules in order
│   ├── pyspark_gen.py                # Updated to consume annotated IR
│   ├── spark_config.py               # SparkSession builder with production configs
│   └── rules/
│       ├── __init__.py
│       ├── base.py                   # OptimizerRule ABC
│       │
│       ├── structural/
│       │   ├── early_filter_pushdown.py
│       │   ├── projection_pruning.py
│       │   ├── fanout_cache_annotation.py
│       │   ├── join_strategy_annotation.py
│       │   ├── collapse_consecutive_transforms.py
│       │   └── eliminate_passthrough_nodes.py
│       │
│       ├── expression/
│       │   ├── strip_identity_assignments.py
│       │   ├── fix_datetime_expressions.py
│       │   ├── type_null_literals.py
│       │   ├── rewrite_udfs_to_native.py
│       │   ├── null_safe_comparison_rewrite.py
│       │   └── deduplicate_common_subexpressions.py
│       │
│       └── write/
│           ├── coalesce_before_write.py
│           ├── partition_by_annotation.py
│           ├── storage_level_selection.py
│           └── repartition_before_shuffle_join.py
└── tests/
    └── unit/
        └── optimizer/
            ├── test_structural_rules.py
            ├── test_expression_rules.py
            └── test_write_rules.py
```

---

## 🔧 Base Rule Interface (`rules/base.py`)

Every rule is a stateless, pure function wrapped in a class for testability
and introspection.

```python
from abc import ABC, abstractmethod
from typing import List
from ir.models import IRNode

class OptimizerRule(ABC):
    """
    All optimizer rules implement this interface.
    Rules are pure: they never mutate input nodes, always return new list.
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    def enabled(self) -> bool:
        return True   # can be toggled per pipeline via config

    @abstractmethod
    def apply(self, nodes: List[IRNode]) -> List[IRNode]: ...

    def __call__(self, nodes: List[IRNode]) -> List[IRNode]:
        if not self.enabled:
            return nodes
        result = self.apply(nodes)
        # Optimizer contract: rule must never change node count arbitrarily
        # (only EliminatePassthroughNodes may reduce count, CollapseTransforms may reduce)
        return result
```

---

## ═══════════════════════════════════════════
## STAGE 1 — Structural IR Optimizations
## ═══════════════════════════════════════════

---

### S1 — `EarlyFilterPushdown`

**What it does:** Moves Filter nodes as far upstream as possible — ideally
immediately after a Read node. This reduces data volume before joins, aggregations,
and expensive transforms run.

**When it applies:** Any pipeline containing a Filter node that is NOT immediately
downstream of a Read node, with only Reformat (projection-only) nodes in between.

**Safe to push when:**
- The filter condition only references columns present at the push target
- No column referenced in the condition is computed by an intermediate Reformat

**Not safe to push when:**
- Filter condition references a derived column (e.g., `total_with_tax`) computed upstream
- The node between Filter and Read is a Join (filter may require both sides)
- The intermediate node is an Aggregate (filter on aggregated columns cannot move past it)

```
BEFORE:  Read → Reformat(rename cols) → Reformat(add derived) → Filter(status = 'ACTIVE')
AFTER:   Read → Filter(status = 'ACTIVE') → Reformat(rename) → Reformat(add derived)
         ↑ only if 'status' exists in Read schema and is not renamed
```

**Impact:** Reduces rows flowing into every subsequent stage. On a 100M row dataset
filtered to 5M, this eliminates 95M rows from every downstream shuffle.

---

### S2 — `ProjectionPruning`

**What it does:** Inserts `.select(required_columns_only)` after Read nodes to
drop columns that are never referenced anywhere downstream. Computes the full
required column set by walking forward through all downstream nodes.

**Algorithm:**
1. For every Write node, collect its input schema (all columns in that schema are required)
2. Walk backward through the IR DAG, accumulating the set of columns referenced
   in each node's transforms, join keys, filter conditions, group-by keys, and agg expressions
3. For each Read node, emit only the intersection of (available columns ∩ required columns)

**When it applies:** Any pipeline where Read schema has more columns than are
actually consumed downstream. Very common when converting Ab Initio graphs that
read wide flat files but only process a subset of columns.

**Impact:** Reduces memory footprint of every shuffle. Parquet/ORC readers apply
this at the scan layer via predicate pushdown — the optimizer makes it explicit
so it works for CSV reads too.

```python
# Emitted after Read if pruning applies:
df_node_01 = (
    spark.read.schema(FULL_SCHEMA).csv(path)
    .select("customer_id", "email", "signup_date")   # 3 of 20 columns needed
)
```

---

### S3 — `FanOutCacheAnnotation`

**What it does:** Detects any IRNode whose output is consumed by more than one
downstream node (out-degree > 1 in the DAG). Tags it with `cache=True` and
computes `unpersist_after = <last_consumer_node_id>`.

**Applies to all node types:** Read, Transform, Join, Aggregate, Filter.
Any of these can be fan-out nodes depending on the pipeline shape.

**Storage level selection** (feeds into W3):
- If the fan-out node's schema is narrow (few columns, simple types) → `MEMORY_ONLY`
- If the fan-out node's schema is wide or has nested types → `MEMORY_AND_DISK`
- If downstream consumers are writes only (no further transforms) → `DISK_ONLY`

**Codegen contract:**
```python
df_node_XX = (...).cache()      # tagged cache=True

# ... all consumers of df_node_XX ...

df_node_XX.unpersist()          # emitted after last consumer's action
```

---

### S4 — `JoinStrategyAnnotation`

**What it does:** Annotates every Join IRNode with the optimal join strategy
based on available metadata. Does NOT hardcode — uses a decision tree.

**Decision tree:**

```
Does the system have row count metadata for both inputs? (from Neo4j stats)
├── YES → use actual row counts
└── NO  → use heuristics (file type, path name, schema width)

Is either input small enough to broadcast? (threshold: configurable, default 10MB)
├── YES → strategy = BROADCAST, broadcast_side = left|right
└── NO  →
    Are both inputs already partitioned on the join key? (bucketed Hive/Delta tables)
    ├── YES → strategy = BUCKET_MERGE (no shuffle)
    └── NO  →
        Is there known data skew on the join key? (from profiling metadata in Neo4j)
        ├── YES → strategy = SKEW_JOIN (emit hint + salt key logic)
        └── NO  → strategy = SORT_MERGE (default)
```

**Codegen output per strategy:**

```python
# BROADCAST
df = large_df.join(F.broadcast(small_df), on="key", how="inner")

# SORT_MERGE (default, no hint needed — Spark default)
df = df_left.join(df_right, on="key", how="inner")

# SKEW_JOIN hint (Spark 3.0+)
df = df_left.hint("skew", "key").join(df_right, on="key", how="inner")

# BUCKET_MERGE (no shuffle if both tables bucketed on same key + count)
df = df_left.join(df_right, on="key", how="inner")
# + SparkSession config: spark.sql.sources.bucketing.enabled = true
```

---

### S5 — `CollapseConsecutiveTransforms`

**What it does:** Merges two or more consecutive Reformat/Transform nodes into
a single node when it is safe to do so (no intermediate fan-out, no schema-breaking
dependency between them).

**Safe to collapse when:**
- No node between them has out-degree > 1
- Transform B does not reference a column computed in Transform A that requires
  the intermediate `.select()` projection to have happened

**Why this matters:** Each Transform node in the IR generates a DataFrame
transformation stage. Fewer stages = fewer query plan nodes = faster Catalyst
optimization time on complex pipelines.

```
BEFORE:  Read → Transform(rename)  → Transform(cast types) → Transform(add flags) → Filter
AFTER:   Read → Transform(rename + cast + add flags) → Filter
```

**Merge algorithm:**
1. Walk IR in topological order
2. If current node is `transform` and previous node is `transform` and
   out-degree(previous) == 1:
   - Merge config.assignments from both
   - Resolve column name conflicts (later assignment wins)
   - Remove intermediate node from IR

---

### S6 — `EliminatePassthroughNodes`

**What it does:** After S1 and S5 run, any Transform node with zero real
assignments (all columns are identity passthrough) is replaced with a simple
alias in the codegen. The node is not removed from the IR (downstream IDs must
remain valid) but is tagged `passthrough=True`.

**Codegen output:**
```python
# node_XX is a passthrough — no transformation applied
df_node_XX = df_node_YY
```

This eliminates the `.withColumn()` + `.select()` block entirely.

---

## ═══════════════════════════════════════════
## STAGE 2 — Expression-Level Rewrites
## ═══════════════════════════════════════════

---

### E1 — `StripIdentityAssignments`

**What it does:** Within every Transform node's `config.assignments` dict,
removes any entry where the expression is a pure reference to the same column.

**Identity patterns to detect:**
```
col = col                    → identity
col = `col`                  → identity (backtick-quoted)
col = in.col                 → identity (Ab Initio input-qualified)
col = CAST(col AS same_type) → identity if type matches schema
col = col + 0                → NOT identity (even though value-equivalent)
col = col || ''              → NOT identity
```

**After stripping, the column still appears in the final `.select()`** —
it is not dropped from output. It simply doesn't need a `withColumn` call.

---

### E2 — `FixDateTimeExpressions`

**What it does:** Scans all expression strings for patterns that are
syntactically valid SQL but semantically incorrect or unreliable when
applied to Spark date/timestamp columns. Rewrites them to the correct
Spark SQL function.

**Rewrite table (exhaustive):**

| Broken Pattern | When Column Type Is | Correct Rewrite |
|---|---|---|
| `SUBSTRING(col, 1, 7)` | Timestamp / Date | `DATE_FORMAT(col, 'yyyy-MM')` |
| `SUBSTRING(col, 1, 4)` | Timestamp / Date | `YEAR(col)` |
| `SUBSTRING(col, 6, 2)` | Timestamp / Date | `MONTH(col)` |
| `SUBSTRING(col, 9, 2)` | Timestamp / Date | `DAY(col)` |
| `col - other_col` | both Date | `DATEDIFF(col, other_col)` |
| `CAST(col AS STRING)` | Timestamp | `DATE_FORMAT(col, 'yyyy-MM-dd HH:mm:ss')` |
| `col > 'YYYY-MM-DD'` | Timestamp / Date | `col > TO_DATE('YYYY-MM-DD')` |
| `UPPER(col)` | Date / Timestamp | WARN: meaningless, strip the UPPER |
| `TRIM(col)` | Date / Timestamp | WARN: meaningless, strip the TRIM |
| `LENGTH(col)` | Date / Timestamp | ERROR: cannot compute length of date |

**Implementation note:** The rule must consult the IRNode's upstream schema
to know the column type. It must NOT rewrite blindly on string patterns alone.

---

### E3 — `TypeNullLiterals`

**What it does:** Finds any assignment whose expression reduces to a NULL literal
(various forms) and replaces it with a typed null using the column's declared
type from the IRNode output schema.

**Patterns matched:**
```
NULL                        → F.lit(None).cast(target_type)
null                        → F.lit(None).cast(target_type)
F.expr("NULL")              → F.lit(None).cast(target_type)
CAST(NULL AS type)          → F.lit(None).cast(target_type)  [already typed — keep as-is]
IF(false, col, NULL)        → simplify → F.lit(None).cast(target_type)
COALESCE(NULL, NULL)        → F.lit(None).cast(target_type)
```

**Why this matters:** Spark's `NullType` cannot be written to Parquet or Delta.
Any untyped null that reaches a Write node will cause a runtime
`AnalysisException: Cannot write nullable values to non-null fields`.

---

### E4 — `RewriteUDFsToNativeFunctions`

**What it does:** The Ab Initio `.xfr` transform parser may emit custom function
calls (e.g. Ab Initio built-ins) that get translated naively to Python UDFs.
This rule detects cases where a native Spark SQL function exists and substitutes it.

**UDF → Native rewrite table:**

| Ab Initio / Custom UDF | Spark Native Equivalent |
|---|---|
| `string_length(col)` | `LENGTH(col)` |
| `trim_leading(col)` | `LTRIM(col)` |
| `trim_trailing(col)` | `RTRIM(col)` |
| `is_null(col)` | `col IS NULL` |
| `is_not_null(col)` | `col IS NOT NULL` |
| `to_upper(col)` | `UPPER(col)` |
| `to_lower(col)` | `LOWER(col)` |
| `coalesce_first(a, b)` | `COALESCE(a, b)` |
| `abs_value(col)` | `ABS(col)` |
| `round_to(col, n)` | `ROUND(col, n)` |
| `mod(a, b)` | `MOD(a, b)` or `a % b` |
| `date_add_days(col, n)` | `DATE_ADD(col, n)` |
| `date_diff(a, b, 'days')` | `DATEDIFF(a, b)` |
| `string_to_date(col, fmt)` | `TO_DATE(col, fmt)` |
| `string_to_datetime(col, fmt)` | `TO_TIMESTAMP(col, fmt)` |
| `decimal(expr, p, s)` | `CAST(expr AS DECIMAL(p, s))` |

**Why this matters:** Python UDFs break Catalyst optimization (they are black boxes),
serialize/deserialize data through Python's GIL, and disable Tungsten whole-stage
code generation. A single Python UDF on a 1B row dataset can cause 10× slowdown
vs an equivalent native Spark function.

**Rule behavior:** If a UDF cannot be mapped to a native function, it is left as-is
but flagged in the optimization report with a `WARN: unresolved_udf` annotation.

---

### E5 — `NullSafeComparisonRewrite`

**What it does:** Detects equality comparisons on nullable columns and ensures
they use null-safe semantics where appropriate.

**Patterns:**

```sql
-- UNSAFE: returns NULL (not FALSE) when col IS NULL
col = 'value'

-- SAFE rewrite when column is nullable and downstream logic treats NULL as non-match:
col <=> 'value'    (null-safe equals, Spark SQL: col IS NOT DISTINCT FROM 'value')

-- Or explicit null guard:
(col IS NOT NULL AND col = 'value')
```

**Rule logic:**
- Only rewrite when the column is declared `nullable=True` in the IRNode schema
- Only rewrite in Filter conditions (not in withColumn assignments)
- Never rewrite join keys — Spark join handles nulls correctly for equi-joins

---

### E6 — `DeduplicateCommonSubexpressions`

**What it does:** Detects when the same expensive expression appears in multiple
assignments within a single Transform node and extracts it into a shared
intermediate column.

**Example:**
```python
# Before — same expression computed twice
.withColumn('tax_amount',  F.expr("order_amount * 0.18"))
.withColumn('total',       F.expr("order_amount + order_amount * 0.18"))

# After — extracted to shared column, then dropped from output select if not needed
.withColumn('__tax__',    F.expr("order_amount * 0.18"))
.withColumn('tax_amount', F.col('__tax__'))
.withColumn('total',      F.expr("order_amount + `__tax__`"))
.drop('__tax__')
```

**Threshold:** Only extract subexpressions that appear 2+ times AND are
non-trivial (not a single column reference or literal).

**Note:** Spark's CSE (Common Subexpression Elimination) within Catalyst handles
some of this automatically for `F.col` references. This rule targets `F.expr()`
string expressions which are opaque to Catalyst until parse time.

---

## ═══════════════════════════════════════════
## STAGE 3 — Write & Runtime Annotations
## ═══════════════════════════════════════════

---

### W1 — `CoalesceBeforeWrite`

**What it does:** Emits a `.coalesce(n)` or `.repartition(n)` before every
Write node to control output file count.

**Decision logic:**

```
Is output file format Parquet/ORC/Delta?
├── YES →
│   What is the estimated output size?
│   ├── Small  (< 128MB total) → .coalesce(1)   # single file, easy downstream read
│   ├── Medium (128MB–10GB)    → .coalesce(dop)  # pipeline DOP parameter
│   └── Large  (> 10GB)        → .repartition(output_partitions)  # full shuffle for balance
└── NO (CSV/text) →
    Is downstream system expecting a specific file count?
    ├── YES → .coalesce(expected_count)
    └── NO  → .coalesce(dop)

Is write mode = 'append'?
├── YES → prefer .coalesce() over .repartition() to avoid full shuffle on appends
└── NO  → either is acceptable
```

**Why coalesce vs repartition:**
- `.coalesce(n)` — narrow transformation, no shuffle, may produce uneven files
  if upstream partitioning is skewed. Use for small/medium outputs.
- `.repartition(n)` — wide transformation, full shuffle, guarantees even file sizes.
  Use for large outputs where file size uniformity matters (e.g., Hive partitioned tables).

---

### W2 — `PartitionByAnnotation`

**What it does:** Detects when a Write node's output should use Hive-style
directory partitioning (`partitionBy`) based on the pipeline metadata.

**Triggers:**
- Output schema contains a date/month column AND downstream use is known to be
  time-range filtered (e.g., column named `date`, `year`, `month`, `order_date`)
- Output schema contains a known high-cardinality categorical column AND
  `partitionBy` is explicitly set in the Ab Initio graph properties

**Codegen output:**
```python
(
    df.write
    .mode("overwrite")
    .partitionBy("order_month")     # injected by W2
    .format("parquet")
    .save(output_path)
)
```

**Guard:** Never emit `partitionBy` on a column with cardinality > configurable
threshold (default: 10,000 distinct values). High-cardinality partition columns
produce millions of small files — worse than no partitioning.

---

### W3 — `StorageLevelSelection`

**What it does:** Works with S3's cache annotations to assign the correct
`StorageLevel` for each cached DataFrame rather than always defaulting to
`MEMORY_ONLY` (the default for `.cache()`).

**Decision table:**

| Scenario | Storage Level |
|---|---|
| Schema is narrow (< 5 cols), primitive types only | `MEMORY_ONLY` |
| Schema is wide (> 20 cols) or has nested types | `MEMORY_AND_DISK_SER` |
| DataFrame is only consumed by Write nodes (no further transforms) | `DISK_ONLY` |
| DataFrame is consumed 5+ times | `MEMORY_AND_DISK` |
| Cluster has known memory pressure (configurable flag) | `MEMORY_AND_DISK_SER` |

**Codegen output:**
```python
from pyspark import StorageLevel

df_node_06 = df_node_06.persist(StorageLevel.MEMORY_AND_DISK_SER)
# instead of the naive:
df_node_06 = df_node_06.cache()
```

---

### W4 — `RepartitionBeforeShuffleJoin`

**What it does:** For any join annotated by S4 as `strategy = SORT_MERGE`
(i.e., not broadcast, not bucketed), emits explicit repartition of both sides
on the join key before the join. This ensures Spark's shuffle is deterministic
and avoids double-shuffle when both sides are already partitioned differently.

**Applies when:**
- Both join inputs have > configurable threshold rows (default: 1M)
- Neither input is annotated for broadcast
- Join key is a single column (multi-key joins handled differently)

```python
# Emitted before Sort-Merge join
df_left  = df_left.repartition(spark_shuffle_partitions, F.col("join_key"))
df_right = df_right.repartition(spark_shuffle_partitions, F.col("join_key"))
df_joined = df_left.join(df_right, on="join_key", how="inner")
```

**Why:** Without this, Spark may shuffle both sides independently with different
partition counts, then need a secondary sort. Explicit co-partitioning on the
join key collapses this to a single deterministic shuffle.

---

## ⚡ SparkSession Builder (`codegen/spark_config.py`)

Generated for every pipeline — not hardcoded, derived from pipeline metadata.

```python
def build_spark_session(pipeline_name: str, dop: int) -> SparkSession:
    """
    Production SparkSession config — generated from pipeline metadata.
    All configs are explicit; never rely on cluster defaults.
    """
    return (
        SparkSession.builder
        .appName(pipeline_name)                         # from Neo4j pipeline.name

        # ── Adaptive Query Execution (Spark 3.0+) ──────────────────────────
        .config("spark.sql.adaptive.enabled",                        "true")
        .config("spark.sql.adaptive.coalescePartitions.enabled",     "true")
        .config("spark.sql.adaptive.coalescePartitions.minPartitionNum", str(dop))
        .config("spark.sql.adaptive.skewJoin.enabled",               "true")
        .config("spark.sql.adaptive.skewJoin.skewedPartitionThresholdInBytes", "256mb")

        # ── Join Thresholds ─────────────────────────────────────────────────
        .config("spark.sql.autoBroadcastJoinThreshold",              str(10 * 1024 * 1024))

        # ── Shuffle ─────────────────────────────────────────────────────────
        .config("spark.sql.shuffle.partitions",                      "200")

        # ── Serialization ───────────────────────────────────────────────────
        .config("spark.serializer",                                  "org.apache.spark.serializer.KryoSerializer")
        .config("spark.kryoserializer.buffer.max",                   "512m")

        # ── Memory ──────────────────────────────────────────────────────────
        .config("spark.sql.inMemoryColumnarStorage.compressed",      "true")
        .config("spark.sql.inMemoryColumnarStorage.batchSize",       "20000")

        # ── Parquet ─────────────────────────────────────────────────────────
        .config("spark.sql.parquet.compression.codec",               "snappy")
        .config("spark.sql.parquet.mergeSchema",                     "false")  # never infer
        .config("spark.sql.parquet.filterPushdown",                  "true")

        # ── Schema Safety ───────────────────────────────────────────────────
        .config("spark.sql.caseSensitive",                           "false")
        .config("spark.sql.storeAssignmentPolicy",                   "STRICT")  # fail on type mismatch

        # ── Tungsten ────────────────────────────────────────────────────────
        .config("spark.sql.codegen.wholeStage",                      "true")
        .config("spark.sql.codegen.fallback",                        "true")

        .getOrCreate()
    )
```

---

## 📊 Optimization Report

The optimizer must produce a machine-readable report alongside the generated code.
This report is stored in Neo4j against the pipeline node and surfaced in the UI.

```json
{
  "pipeline_id": "...",
  "rules_applied": [
    {
      "rule": "EarlyFilterPushdown",
      "nodes_affected": ["node_07", "node_08"],
      "description": "Pushed FilterHighValue upstream past NormalizeOrder (saved ~40% rows in join)"
    },
    {
      "rule": "FanOutCacheAnnotation",
      "nodes_affected": ["node_06"],
      "description": "node_06 has out-degree=3; cached at MEMORY_AND_DISK_SER"
    },
    {
      "rule": "JoinStrategyAnnotation",
      "nodes_affected": ["node_05"],
      "description": "Left input (customers) heuristically identified as dimension; broadcast applied"
    },
    {
      "rule": "RewriteUDFsToNativeFunctions",
      "nodes_affected": ["node_03"],
      "description": "Replaced string_length() → LENGTH(), is_null() → IS NULL"
    }
  ],
  "warnings": [
    {
      "rule": "RewriteUDFsToNativeFunctions",
      "node": "node_06",
      "message": "custom_hash_fn() could not be mapped to a native function; left as Python UDF"
    }
  ],
  "unresolved": []
}
```

---

## 🧪 Testing Strategy

### Unit Tests (per rule, `tests/unit/optimizer/`)

Each rule must have:
1. A test that verifies it fires on a matching IR input
2. A test that verifies it does NOT fire on a non-matching IR input
3. A test that verifies it does not corrupt nodes it should not touch
4. A golden-diff test: IR before vs IR after, asserted structurally

### Key tests to write:

```python
# S1 - EarlyFilterPushdown
test_filter_pushed_past_rename_only_reformat()
test_filter_NOT_pushed_past_reformat_that_computes_filtered_column()
test_filter_NOT_pushed_past_join()
test_filter_NOT_pushed_past_aggregate()

# S3 - FanOutCacheAnnotation
test_node_with_three_consumers_is_tagged_cache()
test_node_with_one_consumer_is_NOT_tagged()
test_unpersist_emitted_after_last_consumer()

# S4 - JoinStrategyAnnotation
test_small_input_gets_broadcast_annotation()
test_both_large_inputs_get_sort_merge()
test_skew_metadata_triggers_skew_hint()

# S5 - CollapseConsecutiveTransforms
test_two_consecutive_transforms_merged()
test_transform_with_fanout_between_NOT_merged()
test_merged_assignments_resolve_column_name_conflicts()

# E2 - FixDateTimeExpressions
test_substring_on_timestamp_rewritten_to_date_format()
test_substring_on_string_NOT_rewritten()
test_year_extraction_rewritten_to_year_function()

# E3 - TypeNullLiterals
test_untyped_null_gets_decimal_type_from_schema()
test_untyped_null_gets_string_type_from_schema()
test_already_typed_cast_null_left_unchanged()

# E4 - RewriteUDFsToNativeFunctions
test_string_length_udf_rewritten_to_length()
test_unknown_udf_left_unchanged_with_warning()
test_date_diff_udf_rewritten_to_datediff()

# W1 - CoalesceBeforeWrite
test_small_output_gets_coalesce_1()
test_large_output_gets_repartition()
test_append_write_gets_coalesce_not_repartition()
```

---

## 🔢 Build Order

```
1. base.py — OptimizerRule ABC
2. Structural rules (S1–S6) — test each before moving on
3. Expression rules (E1–E6) — test each before moving on
4. Write rules (W1–W4) — test each before moving on
5. optimizer.py — pipeline runner that chains all stages
6. spark_config.py — SparkSession builder
7. Update pyspark_gen.py to consume annotated IR
8. Add optimization report generation
9. Expose report via GET /optimize-report/{pipeline_id} endpoint
10. Surface warnings and applied rules in the frontend results page
```

---

## ✅ Production-Ready Code Checklist

A generated pipeline is production-quality when ALL of the following are true:

**Structural**
- [ ] No Filter node exists downstream of a Read when it could safely have been pushed up
- [ ] All Read nodes select only columns needed downstream (no `SELECT *` equivalent)
- [ ] All fan-out nodes (out-degree > 1) are persisted with an appropriate StorageLevel
- [ ] All persisted nodes have a matching `.unpersist()` after their last consumer
- [ ] All consecutive Transform nodes that can be safely merged are merged
- [ ] All passthrough Transform nodes emit only a DataFrame alias

**Joins**
- [ ] Every Join node has an explicit strategy annotation (broadcast / sort-merge / skew)
- [ ] Sort-merge joins on large tables have co-partitioned inputs
- [ ] No cartesian products (cross joins) are emitted unless explicitly in IR

**Expressions**
- [ ] Zero identity `withColumn` calls
- [ ] Zero untyped null literals (`F.expr("NULL")`)
- [ ] Zero `SUBSTRING` on Date/Timestamp columns
- [ ] All Ab Initio built-in functions replaced with native Spark equivalents
- [ ] Repeated subexpressions within a transform are extracted

**Writes**
- [ ] Every Write node is preceded by `.coalesce(n)` or `.repartition(n)`
- [ ] Date/time partitioned outputs use `.partitionBy()`
- [ ] Append-mode writes use `.coalesce()` not `.repartition()`

**Runtime**
- [ ] SparkSession has AQE, skew join, and shuffle config set explicitly
- [ ] `appName` is the pipeline name from Neo4j
- [ ] Kryo serializer is configured
- [ ] Parquet schema merging is disabled
- [ ] `STRICT` assignment policy is set (catches type mismatches at plan time)
