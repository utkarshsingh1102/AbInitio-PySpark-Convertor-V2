# Hive → DML Schema Converter — Test Cases

> **Coverage:** Smoke · Easy · Medium · Hard · Stress  
> **Reference Output Format:** Based on `sales_data` example (delimiter `\001`, `\n` newline terminator, partition columns appended as standard fields)

---

## Table of Contents

1. [Smoke Tests](#1-smoke-tests)
2. [Easy — Primitive Types](#2-easy--primitive-types)
3. [Medium — Collections & Structs](#3-medium--collections--structs)
4. [Hard — Nested & Edge Cases](#4-hard--edge-cases--nested-types)
5. [Stress Tests](#5-stress-tests)

---

## 1. Smoke Tests

> **Purpose:** Verify the converter doesn't crash and produces structurally valid DML output for the most minimal valid inputs.

---

### SM-01 — Minimal Single-Column Table

**Description:** The absolute smallest valid Hive table. One column, no partitions, no complex types.

**Input:**
```sql
CREATE TABLE minimal (
    id BIGINT
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: minimal */
record
  integer(8) id;                              /* BIGINT */
  string("\n") newline;
end
```

**Pass Criteria:**
- `record` / `end` block present
- `integer(8)` used for BIGINT
- `newline` terminator appended
- No crash

---

### SM-02 — Table with Only Partition Columns

**Description:** A table that has no regular columns — only partition keys. Edge case for partition-only schema.

**Input:**
```sql
CREATE TABLE partition_only ()
PARTITIONED BY (year INT, month INT)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: partition_only */
record
  integer(4) year;                            /* INT */
  integer(4) month;                           /* INT */
  string("\n") newline;
end
```

**Pass Criteria:**
- Partition columns are rendered as standard `integer(4)` fields
- No crash on empty column list
- `newline` appended

---

### SM-03 — Table with No ROW FORMAT Clause

**Description:** Valid Hive DDL without an explicit `ROW FORMAT` block. Converter must apply a default delimiter or handle gracefully.

**Input:**
```sql
CREATE TABLE no_row_format (
    name STRING
);
```

**Expected Behavior:**
- Either uses a system default delimiter (e.g., `\001`) OR outputs a warning comment in DML
- Does NOT crash
- `string(...)` field is present

---

### SM-04 — Table Name with Underscore and Numbers

**Description:** Ensures the converter correctly parses non-alphabetic table names.

**Input:**
```sql
CREATE TABLE raw_events_v2 (
    event_id INT
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: raw_events_v2 */
record
  integer(4) event_id;                        /* INT */
  string("\n") newline;
end
```

**Pass Criteria:**
- Header comment uses full table name `raw_events_v2`
- No truncation of name

---

## 2. Easy — Primitive Types

> **Purpose:** Validate that all Hive primitive data types map to correct DML types individually and in combination.

---

### E-01 — All Integer Variants

**Description:** Covers TINYINT, SMALLINT, INT, BIGINT — each must map to the correct `integer(N)` byte width.

**Input:**
```sql
CREATE TABLE integer_types (
    col_tinyint    TINYINT,
    col_smallint   SMALLINT,
    col_int        INT,
    col_bigint     BIGINT
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: integer_types */
record
  integer(1) col_tinyint;                     /* TINYINT */
  integer(2) col_smallint;                    /* SMALLINT */
  integer(4) col_int;                         /* INT */
  integer(8) col_bigint;                      /* BIGINT */
  string("\n") newline;
end
```

**Type Mapping Table:**

| Hive Type | DML Type     |
|-----------|-------------|
| TINYINT   | integer(1)  |
| SMALLINT  | integer(2)  |
| INT       | integer(4)  |
| BIGINT    | integer(8)  |

---

### E-02 — Floating Point Types

**Description:** Covers FLOAT, DOUBLE, DOUBLE PRECISION.

**Input:**
```sql
CREATE TABLE float_types (
    col_float    FLOAT,
    col_double   DOUBLE,
    col_dbl_prec DOUBLE PRECISION
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: float_types */
record
  float(4) col_float;                         /* FLOAT */
  float(8) col_double;                        /* DOUBLE */
  float(8) col_dbl_prec;                      /* DOUBLE PRECISION */
  string("\n") newline;
end
```

---

### E-03 — DECIMAL Variants

**Description:** DECIMAL with different precision and scale combinations, including edge values.

**Input:**
```sql
CREATE TABLE decimal_types (
    price          DECIMAL(10, 2),
    rate           DECIMAL(5, 4),
    big_num        DECIMAL(38, 10),
    no_scale       DECIMAL(18, 0),
    default_dec    DECIMAL
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: decimal_types */
record
  decimal(10,2) price;                        /* DECIMAL(10,2) */
  decimal(5,4) rate;                          /* DECIMAL(5,4) */
  decimal(38,10) big_num;                     /* DECIMAL(38,10) */
  decimal(18,0) no_scale;                     /* DECIMAL(18,0) */
  decimal(10,0) default_dec;                  /* DECIMAL → default precision(10,0) */
  string("\n") newline;
end
```

**Pass Criteria:**
- Precision and scale preserved exactly
- `DECIMAL` without args defaults to `decimal(10,0)` (Hive default)

---

### E-04 — String Types (STRING, VARCHAR, CHAR)

**Description:** All Hive string variants. VARCHAR and CHAR carry length constraints.

**Input:**
```sql
CREATE TABLE string_types (
    col_string   STRING,
    col_varchar  VARCHAR(255),
    col_char     CHAR(10)
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: string_types */
record
  string("\001") col_string;                  /* STRING */
  string("\001",255) col_varchar;             /* VARCHAR(255) */
  string("\001",10) col_char;                 /* CHAR(10) */
  string("\n") newline;
end
```

**Pass Criteria:**
- `STRING` → unbounded `string("\001")`
- `VARCHAR(N)` / `CHAR(N)` → `string("\001", N)` with length constraint

---

### E-05 — Boolean and Binary Types

**Input:**
```sql
CREATE TABLE bool_binary (
    is_active  BOOLEAN,
    raw_bytes  BINARY
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: bool_binary */
record
  integer(1) is_active;                       /* BOOLEAN → 1-byte integer */
  bytes raw_bytes;                            /* BINARY */
  string("\n") newline;
end
```

---

### E-06 — Date and Timestamp Types

**Input:**
```sql
CREATE TABLE time_types (
    event_date   DATE,
    event_ts     TIMESTAMP,
    interval_day INTERVAL
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: time_types */
record
  date event_date;                            /* DATE */
  timestamp event_ts;                         /* TIMESTAMP */
  string("\001") interval_day;                /* INTERVAL → fallback string */
  string("\n") newline;
end
```

**Pass Criteria:**
- `DATE` → `date`
- `TIMESTAMP` → `timestamp`
- `INTERVAL` → graceful fallback (string or converter-defined mapping)

---

### E-07 — Mixed Primitives (All-in-One)

**Description:** A realistic table with all primitive types together. Validates correct DML generation without interference between types.

**Input:**
```sql
CREATE TABLE employee (
    emp_id         BIGINT,
    emp_name       STRING,
    department     VARCHAR(100),
    salary         DECIMAL(12, 2),
    is_active      BOOLEAN,
    joining_date   DATE,
    last_login     TIMESTAMP,
    rating         FLOAT
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: employee */
record
  integer(8) emp_id;                          /* BIGINT */
  string("\001") emp_name;                    /* STRING */
  string("\001",100) department;              /* VARCHAR(100) */
  decimal(12,2) salary;                       /* DECIMAL(12,2) */
  integer(1) is_active;                       /* BOOLEAN */
  date joining_date;                          /* DATE */
  timestamp last_login;                       /* TIMESTAMP */
  float(4) rating;                            /* FLOAT */
  string("\n") newline;
end
```

---

### E-08 — Column Names with Special Patterns

**Description:** Column names using underscores, leading digits (backtick-quoted in Hive), and ALL CAPS.

**Input:**
```sql
CREATE TABLE naming_edge (
    `1st_column`    STRING,
    UPPER_CASE_COL  INT,
    col_with__double_underscore BIGINT
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected Behavior:**
- Backtick-quoted names are stripped of backticks in DML
- Output uses the raw identifier: `1st_column`, `UPPER_CASE_COL`, etc.
- No crash

---

## 3. Medium — Collections & Structs

> **Purpose:** Validate correct DML generation for Hive collection types: ARRAY, MAP, and STRUCT, individually and in simple combinations.

---

### M-01 — ARRAY of Primitive (STRING)

**Input:**
```sql
CREATE TABLE array_string (
    tags ARRAY<STRING>
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: array_string */
record
  /* Hive ARRAY becomes a DML Vector */
  record
    string("\001")[int] item;
  } tags;
  string("\n") newline;
end
```

---

### M-02 — ARRAY of Each Primitive Type

**Description:** One table per ARRAY element type to verify vector element type mapping.

**Input:**
```sql
CREATE TABLE array_primitives (
    int_list     ARRAY<INT>,
    bigint_list  ARRAY<BIGINT>,
    float_list   ARRAY<FLOAT>,
    double_list  ARRAY<DOUBLE>,
    bool_list    ARRAY<BOOLEAN>,
    date_list    ARRAY<DATE>
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: array_primitives */
record
  record
    integer(4)[int] item;
  } int_list;
  record
    integer(8)[int] item;
  } bigint_list;
  record
    float(4)[int] item;
  } float_list;
  record
    float(8)[int] item;
  } double_list;
  record
    integer(1)[int] item;
  } bool_list;
  record
    date[int] item;
  } date_list;
  string("\n") newline;
end
```

---

### M-03 — MAP with Primitive Key and Value

**Input:**
```sql
CREATE TABLE map_primitive (
    attributes MAP<STRING, STRING>,
    scores     MAP<STRING, INT>
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: map_primitive */
record
  /* Hive MAP becomes a Vector of Key-Value pairs */
  record
    record
      string("\001") key;
      string("\001") value;
    } [int] map_entries;
  } attributes;
  record
    record
      string("\001") key;
      integer(4) value;
    } [int] map_entries;
  } scores;
  string("\n") newline;
end
```

---

### M-04 — Simple STRUCT

**Input:**
```sql
CREATE TABLE struct_simple (
    address STRUCT<
        street: STRING,
        city:   STRING,
        zip:    INT
    >
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: struct_simple */
record
  /* Hive STRUCT becomes a nested DML record */
  record
    string("\001") street;
    string("\001") city;
    integer(4) zip;
  } address;
  string("\n") newline;
end
```

---

### M-05 — Single Partition Column

**Input:**
```sql
CREATE TABLE orders_daily (
    order_id   BIGINT,
    amount     DECIMAL(10,2)
)
PARTITIONED BY (dt STRING)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: orders_daily */
record
  integer(8) order_id;                        /* BIGINT */
  decimal(10,2) amount;                       /* DECIMAL(10,2) */
  /* Partition columns are often included as standard fields */
  string("\001") dt;                          /* STRING */
  string("\n") newline;
end
```

---

### M-06 — Multiple Partition Columns (Mixed Types)

**Input:**
```sql
CREATE TABLE events_partitioned (
    event_id   BIGINT,
    payload    STRING
)
PARTITIONED BY (year INT, month INT, region VARCHAR(50))
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: events_partitioned */
record
  integer(8) event_id;                        /* BIGINT */
  string("\001") payload;                     /* STRING */
  /* Partition columns are often included as standard fields */
  integer(4) year;                            /* INT */
  integer(4) month;                           /* INT */
  string("\001",50) region;                   /* VARCHAR(50) */
  string("\n") newline;
end
```

---

### M-07 — Different Field Delimiters

**Description:** Validates that the converter correctly picks up and uses non-default delimiters.

**Input — Tab delimited:**
```sql
CREATE TABLE tab_delimited (
    col1 STRING,
    col2 INT
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\t';
```

**Expected DML Output:**
```
/* Generated from Hive Table: tab_delimited */
record
  string("\t") col1;                          /* STRING */
  integer(4) col2;                            /* INT */
  string("\n") newline;
end
```

**Input — Pipe delimited:**
```sql
CREATE TABLE pipe_delimited (
    col1 STRING,
    col2 INT
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '|';
```

**Expected DML Output:**
```
/* Generated from Hive Table: pipe_delimited */
record
  string("|") col1;                           /* STRING */
  integer(4) col2;                            /* INT */
  string("\n") newline;
end
```

---

### M-08 — STRUCT with DECIMAL Field

**Description:** Struct containing a DECIMAL — validates precision/scale preservation inside nested types.

**Input:**
```sql
CREATE TABLE product_catalog (
    product STRUCT<
        id:    INT,
        name:  STRING,
        price: DECIMAL(8,2)
    >
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: product_catalog */
record
  record
    integer(4) id;
    string("\001") name;
    decimal(8,2) price;
  } product;
  string("\n") newline;
end
```

---

### M-09 — IF NOT EXISTS Clause

**Description:** DDL contains `IF NOT EXISTS` — converter must ignore this clause and process normally.

**Input:**
```sql
CREATE TABLE IF NOT EXISTS log_events (
    log_id  BIGINT,
    message STRING
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected:** Same output as if `IF NOT EXISTS` were absent. No crash.

---

### M-10 — EXTERNAL TABLE

**Description:** External tables are valid Hive DDL. Converter must handle the `EXTERNAL` keyword.

**Input:**
```sql
CREATE EXTERNAL TABLE ext_data (
    id     BIGINT,
    value  STRING
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001'
LOCATION '/data/external/';
```

**Expected:** Correct DML output ignoring `EXTERNAL` and `LOCATION` clauses. Optional: a comment in DML indicating it was an external table.

---

## 4. Hard — Edge Cases & Nested Types

> **Purpose:** Validate correct handling of deep nesting, Hive-specific edge cases, reserved words, and complex combinations.

---

### H-01 — ARRAY of STRUCT

**Input:**
```sql
CREATE TABLE orders (
    line_items ARRAY<STRUCT<
        product_id: INT,
        quantity:   INT,
        unit_price: DECIMAL(8,2)
    >>
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: orders */
record
  record
    record
      integer(4) product_id;
      integer(4) quantity;
      decimal(8,2) unit_price;
    } [int] item;
  } line_items;
  string("\n") newline;
end
```

---

### H-02 — MAP with ARRAY Value

**Input:**
```sql
CREATE TABLE tag_groups (
    category_tags MAP<STRING, ARRAY<STRING>>
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: tag_groups */
record
  record
    record
      string("\001") key;
      record
        string("\001")[int] item;
      } value;
    } [int] map_entries;
  } category_tags;
  string("\n") newline;
end
```

---

### H-03 — MAP with STRUCT Value

**Input:**
```sql
CREATE TABLE user_profiles (
    profile_map MAP<STRING, STRUCT<
        age:    INT,
        active: BOOLEAN
    >>
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: user_profiles */
record
  record
    record
      string("\001") key;
      record
        integer(4) age;
        integer(1) active;
      } value;
    } [int] map_entries;
  } profile_map;
  string("\n") newline;
end
```

---

### H-04 — ARRAY of ARRAY (2-Level Nesting)

**Input:**
```sql
CREATE TABLE matrix_data (
    matrix ARRAY<ARRAY<INT>>
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: matrix_data */
record
  record
    record
      integer(4)[int] item;
    } [int] item;
  } matrix;
  string("\n") newline;
end
```

---

### H-05 — STRUCT Inside STRUCT (2-Level Deep)

**Input:**
```sql
CREATE TABLE company (
    hq STRUCT<
        address: STRUCT<
            street: STRING,
            city:   STRING,
            pin:    INT
        >,
        phone: STRING
    >
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: company */
record
  record
    record
      string("\001") street;
      string("\001") city;
      integer(4) pin;
    } address;
    string("\001") phone;
  } hq;
  string("\n") newline;
end
```

---

### H-06 — STRUCT Inside STRUCT Inside STRUCT (3-Level Deep)

**Input:**
```sql
CREATE TABLE deep_struct (
    level1 STRUCT<
        level2: STRUCT<
            level3: STRUCT<
                value: STRING
            >
        >
    >
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: deep_struct */
record
  record
    record
      record
        string("\001") value;
      } level3;
    } level2;
  } level1;
  string("\n") newline;
end
```

**Pass Criteria:**
- 3 levels of nested `record` blocks
- Correct closing braces at each level

---

### H-07 — Reserved Word as Column Name

**Description:** Hive allows backtick-quoting reserved words as column names. Converter must handle this without failure.

**Input:**
```sql
CREATE TABLE reserved_cols (
    `select`   STRING,
    `from`     INT,
    `where`    BIGINT,
    `order`    DECIMAL(5,2)
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: reserved_cols */
record
  string("\001") select;                      /* STRING */
  integer(4) from;                            /* INT */
  integer(8) where;                           /* BIGINT */
  decimal(5,2) order;                         /* DECIMAL(5,2) */
  string("\n") newline;
end
```

**Pass Criteria:** Backticks stripped, no parser crash

---

### H-08 — Column Name Collision with DML Keywords

**Description:** Column names that are valid DML keywords (e.g., `record`, `end`, `int`, `string`).

**Input:**
```sql
CREATE TABLE dml_keyword_cols (
    `record`  STRING,
    `end`     INT,
    `string`  BIGINT
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected Behavior:**
- Either output the name as-is (escaped/quoted in DML if required)
- OR raise a named warning: `"Column name 'record' conflicts with DML keyword"`
- Must NOT silently produce broken DML

---

### H-09 — Very Long Column Names (64 Characters)

**Description:** Hive allows column names up to 128 characters. DML may have limits. Test at 64 chars.

**Input:**
```sql
CREATE TABLE long_col_names (
    this_is_a_very_long_column_name_that_has_sixty_four_chars_xx1234 STRING
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected:** Column name preserved exactly or truncated with a warning. No crash.

---

### H-10 — NULL Handling Clause (STORED AS NULLFORMAT)

**Input:**
```sql
CREATE TABLE null_format_test (
    id   BIGINT,
    name STRING
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001'
NULL DEFINED AS '';
```

**Expected Behavior:** `NULL DEFINED AS` is ignored in DML output (or noted as a comment). No crash.

---

### H-11 — Table with COMMENT Clause

**Input:**
```sql
CREATE TABLE documented_table (
    emp_id   BIGINT    COMMENT 'Employee primary key',
    emp_name STRING    COMMENT 'Full name of employee'
)
COMMENT 'Stores employee records'
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected Behavior:**
- Table comment and column comments are either: (a) preserved as DML `/* ... */` comments, or (b) silently dropped
- No crash regardless of choice

---

### H-12 — STORED AS Clause Variants

**Description:** `STORED AS` changes the underlying file format (ORC, Parquet, Avro, TextFile). Converter must handle or ignore without failure.

**Inputs (one each):**
```sql
-- ORC
CREATE TABLE orc_table (id BIGINT) STORED AS ORC;

-- Parquet
CREATE TABLE parquet_table (id BIGINT) STORED AS PARQUET;

-- Avro
CREATE TABLE avro_table (id BIGINT) STORED AS AVRO;

-- TextFile (default)
CREATE TABLE text_table (id BIGINT) STORED AS TEXTFILE;
```

**Expected Behavior:** DML output is identical across all — `STORED AS` is metadata, not schema. No crash.

---

### H-13 — SERDE Format (ROW FORMAT SERDE)

**Description:** Some Hive tables use a custom SerDe instead of DELIMITED.

**Input:**
```sql
CREATE TABLE json_serde_table (
    user_id  BIGINT,
    payload  STRING
)
ROW FORMAT SERDE 'org.apache.hive.hcatalog.data.JsonSerDe'
STORED AS TEXTFILE;
```

**Expected Behavior:**
- No delimiter is extractable from DDL
- Converter uses a system default delimiter or emits a warning comment
- DML fields are generated correctly

---

### H-14 — Complex Full Example (All Type Families)

**Description:** Combines all type families in one table: primitives, ARRAY, MAP, STRUCT, partition, and comments.

**Input:**
```sql
CREATE TABLE analytics_event (
    event_id        BIGINT,
    user_name       VARCHAR(200),
    score           DECIMAL(6,3),
    is_premium      BOOLEAN,
    occurred_at     TIMESTAMP,
    tags            ARRAY<STRING>,
    metadata        MAP<STRING, STRING>,
    device          STRUCT<
                        type:   STRING,
                        os:     STRING,
                        version: DECIMAL(4,1)
                    >,
    raw_payload     BINARY
)
COMMENT 'Analytics events table'
PARTITIONED BY (event_date DATE, region VARCHAR(50))
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: analytics_event */
record
  integer(8) event_id;                        /* BIGINT */
  string("\001",200) user_name;               /* VARCHAR(200) */
  decimal(6,3) score;                         /* DECIMAL(6,3) */
  integer(1) is_premium;                      /* BOOLEAN */
  timestamp occurred_at;                      /* TIMESTAMP */
  record
    string("\001")[int] item;
  } tags;
  record
    record
      string("\001") key;
      string("\001") value;
    } [int] map_entries;
  } metadata;
  record
    string("\001") type;
    string("\001") os;
    decimal(4,1) version;
  } device;
  bytes raw_payload;                          /* BINARY */
  /* Partition columns are often included as standard fields */
  date event_date;                            /* DATE */
  string("\001",50) region;                   /* VARCHAR(50) */
  string("\n") newline;
end
```

---

### H-15 — Duplicate Column Names

**Description:** Invalid Hive DDL but tests converter robustness.

**Input:**
```sql
CREATE TABLE dup_cols (
    id STRING,
    id INT
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected Behavior:**
- Converter raises a clear error: `"Duplicate column name: id"`
- Does NOT silently overwrite or produce invalid DML
- Error includes column name and position

---

### H-16 — Zero-Length VARCHAR / CHAR

**Description:** Edge value for string length constraint.

**Input:**
```sql
CREATE TABLE zero_len_string (
    col1 VARCHAR(0),
    col2 CHAR(0)
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected Behavior:**
- Either: `string("\001", 0)` — length zero preserved
- Or: a validation error — `VARCHAR(0)` is invalid in Hive
- Must NOT crash silently

---

## 5. Stress Tests

> **Purpose:** Test converter performance, memory handling, and correctness under high-volume and deeply nested inputs.

---

### ST-01 — Wide Table (100 Columns, All Primitives)

**Description:** Table with 100 primitive-type columns. Validates no truncation, no column loss, and linear processing time.

**Input (abbreviated):**
```sql
CREATE TABLE wide_table_100 (
    col_001 BIGINT,
    col_002 STRING,
    col_003 DECIMAL(10,2),
    col_004 BOOLEAN,
    col_005 TIMESTAMP,
    col_006 FLOAT,
    col_007 DATE,
    col_008 INT,
    col_009 DOUBLE,
    col_010 SMALLINT,
    -- ... repeat pattern to col_100
    col_100 VARCHAR(255)
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

> **Generation Note:** Generate columns `col_001` through `col_100` cycling through: `BIGINT, STRING, DECIMAL(10,2), BOOLEAN, TIMESTAMP, FLOAT, DATE, INT, DOUBLE, SMALLINT`

**Pass Criteria:**
- Exactly 100 field entries in DML output
- `newline` terminator present at end
- No column skipped or duplicated
- Conversion completes within 2 seconds

---

### ST-02 — Wide Table (500 Columns)

**Description:** Extends ST-01 to 500 columns. Performance + correctness.

**Pass Criteria:**
- All 500 fields present in DML
- Conversion completes within 10 seconds
- No memory crash

---

### ST-03 — Deep Nesting (5-Level STRUCT)

**Description:** A STRUCT nested 5 levels deep. Tests parser stack depth and recursive DML generation.

**Input:**
```sql
CREATE TABLE deep_5 (
    l1 STRUCT<
        l2: STRUCT<
            l3: STRUCT<
                l4: STRUCT<
                    l5: STRUCT<
                        value: STRING
                    >
                >
            >
        >
    >
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: deep_5 */
record
  record
    record
      record
        record
          record
            string("\001") value;
          } l5;
        } l4;
      } l3;
    } l2;
  } l1;
  string("\n") newline;
end
```

**Pass Criteria:**
- 5 opening `record` blocks
- 5 closing `}` lines + outer `end`
- No stack overflow

---

### ST-04 — Deep Nesting (10-Level STRUCT)

**Description:** 10-level deep STRUCT. Extreme parser depth test.

**Pass Criteria:**
- Correct indentation at all 10 levels
- No crash / stack overflow
- Output is valid DML structure

---

### ST-05 — ARRAY of 5-Level Nested STRUCT

**Description:** Combines deep nesting with array vector — a real-world pattern in event schema designs.

**Input:**
```sql
CREATE TABLE nested_event (
    events ARRAY<STRUCT<
        id: INT,
        context: STRUCT<
            session: STRUCT<
                id:     STRING,
                device: STRUCT<
                    type: STRING,
                    os:   STRING
                >
            >
        >
    >>
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Pass Criteria:**
- Outer vector wrapper present
- All struct levels correctly nested inside
- No mismatched `record` / `}` pairs

---

### ST-06 — 50 ARRAYs in One Table

**Description:** Table with 50 ARRAY columns. Tests repeated vector generation without bleed between definitions.

**Input (abbreviated):**
```sql
CREATE TABLE many_arrays (
    arr_001 ARRAY<STRING>,
    arr_002 ARRAY<INT>,
    arr_003 ARRAY<BIGINT>,
    -- ... to arr_050
    arr_050 ARRAY<DECIMAL(10,2)>
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Pass Criteria:**
- 50 independent `record { ... }[int] item;` vector blocks
- Element types are correct per column definition
- No sharing/bleed between array definitions

---

### ST-07 — 50 MAP Columns in One Table

**Description:** 50 MAP columns with different key/value type combinations.

**Input (abbreviated):**
```sql
CREATE TABLE many_maps (
    map_001 MAP<STRING, STRING>,
    map_002 MAP<STRING, INT>,
    map_003 MAP<STRING, BIGINT>,
    map_004 MAP<STRING, DECIMAL(10,2)>,
    map_005 MAP<STRING, BOOLEAN>,
    -- ... repeating pattern to map_050
    map_050 MAP<STRING, TIMESTAMP>
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Pass Criteria:**
- 50 independent MAP blocks with correct key/value types
- No cross-contamination between MAP definitions

---

### ST-08 — Wide Table + Mixed Complex Types (200 Columns)

**Description:** 200-column table mixing primitives, ARRAYs, MAPs, and STRUCTs. Simulates a real-world denormalized lakehouse table.

**Distribution:**
- 100 primitive columns (BIGINT, STRING, DECIMAL, etc.)
- 40 ARRAY columns
- 40 MAP columns
- 20 STRUCT columns

**Pass Criteria:**
- All 200 columns present in DML
- Each type generated correctly with no cross-type interference
- Conversion completes in under 30 seconds

---

### ST-09 — Very Long String as Default Value (TBLPROPERTIES)

**Description:** DDL with TBLPROPERTIES containing very long strings. Parser must skip them cleanly.

**Input:**
```sql
CREATE TABLE tblprops_test (
    id BIGINT
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001'
TBLPROPERTIES (
    'transient_lastDdlTime'='1700000000',
    'comment'='AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
);
```

**Pass Criteria:**
- `id BIGINT` correctly generated
- TBLPROPERTIES fully ignored
- No crash on long string value

---

### ST-10 — Repeatedly Partitioned Wide Table

**Description:** Wide table with 20 partition columns. Simulates an over-partitioned data lake table.

**Input (abbreviated):**
```sql
CREATE TABLE over_partitioned (
    event_id BIGINT,
    payload  STRING
)
PARTITIONED BY (
    year INT, month INT, day INT,
    hour INT, minute INT,
    region VARCHAR(50), country VARCHAR(50), city VARCHAR(100),
    device_type VARCHAR(50), platform VARCHAR(50),
    channel VARCHAR(50), campaign_id BIGINT,
    ab_group CHAR(1), experiment_id INT,
    user_tier VARCHAR(20), is_internal BOOLEAN,
    source VARCHAR(50), env VARCHAR(10),
    version INT, build_id BIGINT
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Pass Criteria:**
- `event_id` and `payload` as standard fields
- All 20 partition columns appended with correct types
- `newline` terminates the record
- No column missing

---

## Appendix — Type Mapping Reference

| Hive Type          | DML Type              | Notes                              |
|--------------------|-----------------------|----------------------------------  |
| TINYINT            | integer(1)            |                                    |
| SMALLINT           | integer(2)            |                                    |
| INT / INTEGER      | integer(4)            |                                    |
| BIGINT             | integer(8)            |                                    |
| FLOAT              | float(4)              |                                    |
| DOUBLE             | float(8)              |                                    |
| DOUBLE PRECISION   | float(8)              | Alias for DOUBLE                   |
| DECIMAL(p,s)       | decimal(p,s)          | Default: decimal(10,0)             |
| STRING             | string("\001")        | Delimiter from DDL                 |
| VARCHAR(n)         | string("\001",n)      |                                    |
| CHAR(n)            | string("\001",n)      |                                    |
| BOOLEAN            | integer(1)            | 0/1 representation                 |
| BINARY             | bytes                 |                                    |
| DATE               | date                  |                                    |
| TIMESTAMP          | timestamp             |                                    |
| ARRAY<T>           | record { T[int] item; } |                                  |
| MAP<K,V>           | record { record { K key; V value; }[int] map_entries; } | |
| STRUCT<f:T,...>    | record { T f; ... }   | Named nested record                |

---

*Generated for Hive → DML Schema Converter · Test Suite v1.0*
