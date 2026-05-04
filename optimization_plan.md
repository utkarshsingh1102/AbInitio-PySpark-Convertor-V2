# PySpark Code Generation — Optimization Layer
## Claude Code Execution Plan (Addendum to main plan.md)

---

## 🔍 What's Wrong With the Current Output

Before building the optimizer, understand exactly what problems exist in the generated code.

### Problem 1 — Identity `withColumn` Chains (Worst Offender)

Current output for `ApplyLoyaltyDiscount` (node_09):
```python
df_node_09 = df_node_09.withColumn('order_id',       F.expr("`order_id`"))
df_node_09 = df_node_09.withColumn('customer_id',    F.expr("`customer_id`"))
df_node_09 = df_node_09.withColumn('full_name',      F.expr("`full_name`"))
# ... 15 more identity columns ...
df_node_09 = df_node_09.withColumn('discount_pct',   F.expr("(CASE WHEN ...)"))
df_node_09 = df_node_09.withColumn('final_amount',   F.expr("CAST(...)"))
```

Each `.withColumn()` creates a new query plan node in Spark's Catalyst. 18 chained
identity withColumns = 18 unnecessary plan nodes before Catalyst can even begin
optimizing. Catalyst DOES partially fold these, but it consumes planning time and
makes the lineage unreadable.

**Fix:** Strip all identity assignments. Only emit `withColumn` for columns that
actually change. Passthrough columns are handled by the final `.select()`.

---

### Problem 2 — Fan-Out Node Not Cached

`df_node_06` (EnrichRecord) feeds THREE downstream nodes:
- `node_07` (FilterHighValue)
- `node_08` (FilterStandard)
- `node_13` (AuditOutput)

Current output has zero caching. Spark will recompute the entire lineage from
`CustomerInput → NormalizeCustomer → Join → EnrichRecord` **three separate times**
during the action phase.

**Fix:** Detect fan-out nodes (out-degree > 1) in the IR and wrap them with
`.cache()` + `.unpersist()` after all consumers have been written.

---

### Problem 3 — Untyped NULL Literal

```python
df_node_06 = df_node_06.withColumn('discount_pct', F.expr("NULL"))
df_node_06 = df_node_06.withColumn('final_amount',  F.expr("NULL"))
```

`F.expr("NULL")` produces `NullType` in Spark's type system. When this DataFrame
is written to Parquet, Spark cannot serialize `NullType` — it throws at runtime.
Must be typed: `F.lit(None).cast(DecimalType(5,2))`.

**Fix:** IR carries the schema for every node. Use schema types to emit typed null
literals: `F.lit(None).cast(...)`.

---

### Problem 4 — `order_month` Derived From Timestamp With SUBSTRING

```python
df_node_04 = df_node_04.withColumn('order_date',  F.expr("TO_TIMESTAMP(...)"))
df_node_04 = df_node_04.withColumn('order_month', F.expr("SUBSTRING(`order_date`, 1, 7)"))
```

`SUBSTRING` on a `TimestampType` column will NOT work in Spark SQL — it expects
a string. Spark implicitly casts `Timestamp → String` before applying SUBSTRING,
which means the output format depends on the JVM's timezone locale.

**Fix:** Codegen must use `DATE_FORMAT(order_date, 'yyyy-MM')` for any month
extraction from a datetime field.

---

### Problem 5 — No SparkSession Tuning

```python
spark = SparkSession.builder.appName('0d20fee8b5ce').getOrCreate()
```

- `appName` is a UUID (debugging is impossible)
- AQE is not enabled (Spark 3+ default is on, but explicit config is production hygiene)
- No skew join handling
- No broadcast threshold set

---

### Problem 6 — No Broadcast Hint on Join

```python
df_node_05 = df_node_03.join(df_node_04, on=['customer_id'], how='inner')
```

No consideration of table size. If `customers` is a dimension table (small), it
should be broadcast. The system has `DOP` and file path metadata in the IR — use it.

---

### Problem 7 — No Coalesce Before Write

All three writes output with the full partition count of the last stage. For
`AuditOutput` which uses `mode='append'`, this can produce thousands of tiny
Parquet files over time.

---

### Problem 8 — Redundant `.select()` on Passthrough Nodes

After stripping identity `withColumn`s, passthrough-only nodes (where nothing
actually changes) should emit NO code at all — just alias the upstream DataFrame.

---

## 🏗️ Optimizer Architecture

The optimizer is a **pipeline of rules** that transforms `list[IRNode]`
before codegen sees it. Each rule is a pure function: `list[IRNode] → list[IRNode]`.

```
list[IRNode]  (from IR Builder)
      ↓
┌─────────────────────────────────────┐
│  IR Optimizer Pipeline              │
│                                     │
│  Rule 1: StripIdentityTransforms    │
│  Rule 2: MarkFanOutNodes            │
│  Rule 3: InferBroadcastJoins        │
│  Rule 4: FixDateFormatExpressions   │
│  Rule 5: TypeNullLiterals           │
│  Rule 6: CollapsePassthroughNodes   │
└────────────────┬────────────────────┘
                 ↓
   list[IRNode]  (optimized)
                 ↓
         PySpark Code Generator
                 ↓
   production_pipeline.py
```

---

## 📁 New Files to Add

```
backend/
├── codegen/
│   ├── optimizer.py          # Rule pipeline runner
│   ├── pyspark_gen.py        # UPDATED — consumes optimized IR
│   └── rules/
│       ├── __init__.py
│       ├── strip_identity.py
│       ├── mark_fanout.py
│       ├── infer_broadcast.py
│       ├── fix_date_format.py
│       ├── type_null_literals.py
│       └── collapse_passthrough.py
└── tests/
    └── unit/
        └── test_optimizer_rules.py
```

---

## 🔧 Rule Implementations

---

### Rule 1 — `StripIdentityTransforms` (`rules/strip_identity.py`)

**Logic:** For each `IRNode` of type `transform`, remove any assignment where
`lhs == rhs` (column assigned to itself, possibly with backtick quoting).

```python
import re

IDENTITY_PATTERN = re.compile(r"^`?(\w+)`?$")

def strip_identity(node: IRNode) -> IRNode:
    """
    Remove assignments like:  out.col = in.col  (pure passthrough)
    Keep only assignments that actually compute something new.
    """
    if node.type != "transform":
        return node

    cleaned = {}
    for col, expr in node.config["assignments"].items():
        match = IDENTITY_PATTERN.match(expr.strip())
        if match and match.group(1) == col:
            continue   # pure identity — skip
        cleaned[col] = expr

    return replace(node, config={**node.config, "assignments": cleaned})
```

**Impact on node_09:** 18 identity assignments → 0. Only `discount_pct` and
`final_amount` remain. The `.select()` at the end still emits all output columns.

---

### Rule 2 — `MarkFanOutNodes` (`rules/mark_fanout.py`)

**Logic:** Walk the IR, count downstream consumers per node. Any node with
`out_degree > 1` gets tagged with `cache=True` in its config. Also compute
`unpersist_after` — the last consumer node ID.

```python
from collections import Counter

def mark_fanout(nodes: list[IRNode]) -> list[IRNode]:
    out_degree = Counter()
    for n in nodes:
        for upstream_id in n.inputs:
            out_degree[upstream_id] += 1

    result = []
    for n in nodes:
        if out_degree[n.id] > 1:
            n = replace(n, config={**n.config, "cache": True})
        result.append(n)
    return result
```

**Code emitted for node_06:**
```python
df_node_06 = df_node_06.cache()   # fan-out: consumed by node_07, node_08, node_13
```

And after the last consumer write:
```python
df_node_06.unpersist()
```

---

### Rule 3 — `InferBroadcastJoins` (`rules/infer_broadcast.py`)

**Logic:** For join nodes, inspect the `properties` of each input node. If an
input is an `InputFile` with a known small row count OR the file path contains
a known dimension keyword (configurable), tag it for broadcast.

Use a configurable `broadcast_threshold_mb` (default: 10 MB). If the system has
row count metadata from Neo4j (after a profiling pass), use it. Otherwise, fall
back to heuristics (customers table = dimension = broadcast candidate).

```python
DIMENSION_KEYWORDS = {"customer", "product", "lookup", "dim", "ref"}

def infer_broadcast(nodes: list[IRNode]) -> list[IRNode]:
    result = []
    for n in nodes:
        if n.type == "join":
            left_id, right_id = n.inputs
            left_node  = find_by_id(nodes, left_id)
            right_node = find_by_id(nodes, right_id)

            broadcast_side = None
            if is_dimension(left_node):
                broadcast_side = "left"
            elif is_dimension(right_node):
                broadcast_side = "right"

            if broadcast_side:
                n = replace(n, config={**n.config, "broadcast": broadcast_side})
        result.append(n)
    return result
```

**Code emitted for node_05:**
```python
df_node_05 = df_node_04.join(
    F.broadcast(df_node_03),   # customers is a dimension table
    on=['customer_id'],
    how='inner'
)
```

---

### Rule 4 — `FixDateFormatExpressions` (`rules/fix_date_format.py`)

**Logic:** Scan all `F.expr(...)` strings in assignments. Find any pattern
`SUBSTRING(col, 1, 7)` where `col` is a `TimestampType` or `DateType` in the
upstream schema. Replace with `DATE_FORMAT(col, 'yyyy-MM')`.

```python
import re

SUBSTRING_MONTH_PATTERN = re.compile(
    r"SUBSTRING\(`?(\w+)`?,\s*1,\s*7\)", re.IGNORECASE
)

def fix_date_format(nodes: list[IRNode]) -> list[IRNode]:
    result = []
    for n in nodes:
        if n.type != "transform":
            result.append(n)
            continue

        fixed = {}
        for col, expr in n.config["assignments"].items():
            match = SUBSTRING_MONTH_PATTERN.search(expr)
            if match:
                col_name = match.group(1)
                if is_date_or_timestamp(n, col_name):
                    expr = SUBSTRING_MONTH_PATTERN.sub(
                        f"DATE_FORMAT(`{col_name}`, 'yyyy-MM')", expr
                    )
            fixed[col] = expr
        result.append(replace(n, config={**n.config, "assignments": fixed}))
    return result
```

---

### Rule 5 — `TypeNullLiterals` (`rules/type_null_literals.py`)

**Logic:** Scan assignments for `F.expr("NULL")`. Look up the column's type in
the node's output schema. Replace with `F.lit(None).cast(target_type)`.

```python
def type_null_literals(nodes: list[IRNode]) -> list[IRNode]:
    result = []
    for n in nodes:
        if n.type != "transform":
            result.append(n)
            continue

        fixed = {}
        for col, expr in n.config["assignments"].items():
            if expr.strip().upper() == "NULL":
                spark_type = get_spark_type(n.schema, col)
                # Mark as typed null so codegen emits F.lit(None).cast(...)
                fixed[col] = {"__typed_null__": True, "type": spark_type}
            else:
                fixed[col] = expr
        result.append(replace(n, config={**n.config, "assignments": fixed}))
    return result
```

**Code emitted:**
```python
df_node_06 = df_node_06.withColumn('discount_pct', F.lit(None).cast(DecimalType(5, 2)))
df_node_06 = df_node_06.withColumn('final_amount',  F.lit(None).cast(DecimalType(12, 2)))
```

---

### Rule 6 — `CollapsePassthroughNodes` (`rules/collapse_passthrough.py`)

**Logic:** After `StripIdentityTransforms`, if a transform node has zero
remaining assignments (all were identity), mark it as `passthrough=True`.
Codegen emits a simple alias instead of any transformation code.

```python
def collapse_passthrough(nodes: list[IRNode]) -> list[IRNode]:
    result = []
    for n in nodes:
        if n.type == "transform" and len(n.config.get("assignments", {})) == 0:
            n = replace(n, config={**n.config, "passthrough": True})
        result.append(n)
    return result
```

**Code emitted:**
```python
# node_XX is a passthrough — alias upstream
df_node_XX = df_node_YY   # no transformation
```

---

## ⚡ Updated PySpark Generator Changes

Beyond consuming the optimized IR, the generator itself needs these upgrades:

### 1. SparkSession Builder

```python
spark = (
    SparkSession.builder
    .appName("customer_order_enrichment")          # from pipeline name in Neo4j
    .config("spark.sql.adaptive.enabled",               "true")
    .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
    .config("spark.sql.adaptive.skewJoin.enabled",      "true")
    .config("spark.sql.shuffle.partitions",             "200")
    .config("spark.sql.autoBroadcastJoinThreshold",     str(10 * 1024 * 1024))
    .getOrCreate()
)
```

---

### 2. Batch `withColumn` → `select` + `withColumns` (Spark 3.3+)

Instead of:
```python
df = df.withColumn('a', expr_a)
df = df.withColumn('b', expr_b)
```

Emit:
```python
df = df.withColumns({       # single plan node, Spark 3.3+
    'a': expr_a,
    'b': expr_b,
})
```

Fall back to chained `withColumn` if Spark < 3.3.

---

### 3. Coalesce Before Write

```python
# write: HighValueOutput
(
    df_node_09
    .coalesce(4)              # from pipeline DOP parameter stored in Neo4j
    .write
    .mode('overwrite')
    .format('parquet')
    .save('/data/output/high_value_orders')
)
```

---

### 4. Repartition on Join Key Before Heavy Joins

```python
# For non-broadcast joins, repartition both sides on the join key first
df_node_03_repartitioned = df_node_03.repartition(200, 'customer_id')
df_node_04_repartitioned = df_node_04.repartition(200, 'customer_id')
df_node_05 = df_node_03_repartitioned.join(df_node_04_repartitioned, on=['customer_id'], how='inner')
```

---

## 🧪 Testing the Optimizer

### `backend/tests/unit/test_optimizer_rules.py`

```python
def test_strip_identity_removes_passthrough_columns():
    node = IRNode(type="transform", config={"assignments": {
        "order_id":    "`order_id`",         # identity — must be removed
        "final_price": "`price` * 1.18",     # real transform — must be kept
    }})
    result = strip_identity(node)
    assert "order_id"    not in result.config["assignments"]
    assert "final_price" in     result.config["assignments"]

def test_mark_fanout_tags_multi_consumer_nodes():
    # node_06 feeds node_07, node_08, node_13
    nodes = [node_06, node_07, node_08, node_13]   # mock IRNodes
    result = mark_fanout(nodes)
    node_06_result = next(n for n in result if n.id == "node_06")
    assert node_06_result.config["cache"] is True

def test_fix_date_format_replaces_substring_on_timestamp():
    node = IRNode(type="transform", config={"assignments": {
        "order_month": "SUBSTRING(`order_date`, 1, 7)"
    }}, schema={"order_date": TimestampType()})
    result = fix_date_format([node])[0]
    assert "DATE_FORMAT" in result.config["assignments"]["order_month"]
    assert "SUBSTRING"   not in result.config["assignments"]["order_month"]

def test_type_null_literals_emits_typed_cast():
    node = IRNode(type="transform", config={"assignments": {
        "discount_pct": "NULL"
    }}, schema={"discount_pct": DecimalType(5, 2)})
    result = type_null_literals([node])[0]
    assert result.config["assignments"]["discount_pct"]["__typed_null__"] is True
    assert result.config["assignments"]["discount_pct"]["type"] == DecimalType(5, 2)
```

---

## 📊 Before vs After (node_09 ApplyLoyaltyDiscount)

### Before (current output) — 22 lines of chained withColumn
```python
df_node_09 = df_node_07
df_node_09 = df_node_09.withColumn('order_id',       F.expr("`order_id`"))
df_node_09 = df_node_09.withColumn('customer_id',    F.expr("`customer_id`"))
# ... 16 more identity columns ...
df_node_09 = df_node_09.withColumn('discount_pct',   F.expr("(CASE WHEN ...)"))
df_node_09 = df_node_09.withColumn('final_amount',   F.expr("CAST(...)"))
df_node_09 = df_node_09.select(...)
```

### After (optimized output) — 5 lines
```python
df_node_09 = df_node_07.withColumns({
    'discount_pct': F.expr("CASE WHEN loyalty_tier = 'GOLD' THEN 15.00 "
                           "WHEN loyalty_tier = 'SILVER' THEN 10.00 ELSE 5.00 END"),
    'final_amount': F.expr("CAST(order_amount * (1 - discount_pct / 100) AS DECIMAL(12,2))"),
}).select(*OUTPUT_COLUMNS_node_09)
```

**Plan nodes: 22 → 2. Zero identity withColumns. Zero NullType columns.**

---

## 🔢 Build Order for This Addendum

```
1. Add IRNode.config fields: cache, broadcast, passthrough (update models.py)
2. Create backend/codegen/rules/ package with all 6 rules
3. Create backend/codegen/optimizer.py (pipeline runner)
4. Update backend/codegen/pyspark_gen.py to:
   a. Call optimizer before codegen
   b. Emit .cache() / .unpersist() for tagged nodes
   c. Emit F.broadcast() for tagged join inputs
   d. Use .withColumns() (Spark 3.3+) instead of chained .withColumn()
   e. Use typed null literals
   f. Emit SparkSession configs
   g. Emit .coalesce(dop) before writes
5. Write unit tests for all 6 rules
6. Run golden test end-to-end and diff old vs new output
```

---

## ✅ Optimized Output Checklist

A generated `pipeline.py` is production-quality when:

- [ ] No identity `withColumn` calls exist in any transform
- [ ] All fan-out nodes (out-degree > 1) have `.cache()` with matching `.unpersist()`
- [ ] No `F.expr("NULL")` — all null literals are typed
- [ ] No `SUBSTRING(timestamp_col, 1, 7)` — replaced with `DATE_FORMAT`
- [ ] SparkSession has AQE, skew join, and shuffle partition configs set explicitly
- [ ] Join nodes use `F.broadcast()` for known dimension inputs
- [ ] All writes are preceded by `.coalesce(dop)`
- [ ] `appName` is the pipeline name from Neo4j, not a UUID
- [ ] Passthrough-only transform nodes emit a single alias line, not transformation code
