# Hive → DML Schema Converter — Test Cases (Set 2)

> **Coverage:** Smoke · Easy · Medium · Hard · Stress  
> **Note:** All test cases in this file are fresh — zero overlap with Test Set 1.  
> New angles covered: DDL syntax variations, non-STRING MAP keys, COLLECTION/MAP KEY terminators,  
> STRUCT with embedded collections, DDL comment styles, Hive 3.x types, malformed input handling,  
> deeply branched schemas, and high-volume stress variants not present in Set 1.

---

## Table of Contents

1. [Smoke Tests](#1-smoke-tests)
2. [Easy — DDL Syntax Variations & Type Aliases](#2-easy--ddl-syntax-variations--type-aliases)
3. [Medium — Non-STRING MAP Keys, Collection Terminators, STRUCT with Collections](#3-medium--non-string-map-keys-collection-terminators--struct-with-collections)
4. [Hard — ARRAY of MAP, MAP of MAP, Branched STRUCT, Malformed Input Handling](#4-hard--arraymap-mapmap-branched-struct--malformed-input-handling)
5. [Stress Tests](#5-stress-tests)

---

## 1. Smoke Tests

> **Purpose:** Verify parser robustness against DDL formatting and syntax variants not tested in Set 1.

---

### SM2-01 — All Lowercase DDL Keywords

**Description:** Hive DDL is case-insensitive. Parser must handle fully lowercase keywords.

**Input:**
```sql
create table lowercase_test (
    id bigint,
    name string
)
row format delimited
fields terminated by '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: lowercase_test */
record
  integer(8) id;                              /* BIGINT */
  string("\001") name;                        /* STRING */
  string("\n") newline;
end
```

**Pass Criteria:** Keywords treated case-insensitively. No crash.

---

### SM2-02 — Mixed Case DDL Keywords

**Description:** Realistic mixed-case DDL (e.g., `Create Table`, `Partitioned By`).

**Input:**
```sql
Create Table MixedCase_Table (
    Col_One Bigint,
    Col_Two String
)
Partitioned By (Dt String)
Row Format Delimited
Fields Terminated By '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: MixedCase_Table */
record
  integer(8) Col_One;                         /* BIGINT */
  string("\001") Col_Two;                     /* STRING */
  /* Partition columns are often included as standard fields */
  string("\001") Dt;                          /* STRING */
  string("\n") newline;
end
```

---

### SM2-03 — Database-Qualified Table Name (db.table)

**Description:** Hive allows `CREATE TABLE db_name.table_name`. Parser must handle the dot-qualified form.

**Input:**
```sql
CREATE TABLE analytics_db.session_logs (
    session_id BIGINT,
    duration   INT
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: analytics_db.session_logs */
record
  integer(8) session_id;                      /* BIGINT */
  integer(4) duration;                        /* INT */
  string("\n") newline;
end
```

**Pass Criteria:** Table name in header comment includes the DB prefix. No crash.

---

### SM2-04 — DDL with Extra Whitespace and Blank Lines

**Description:** DDL with irregular indentation, multiple blank lines, and trailing spaces. Validates that the tokenizer/lexer is whitespace-tolerant.

**Input:**
```sql
CREATE   TABLE    spaced_table   (

    col_a     BIGINT   ,

    col_b     STRING

)
ROW    FORMAT    DELIMITED
FIELDS   TERMINATED   BY   '\001'  ;
```

**Expected DML Output:**
```
/* Generated from Hive Table: spaced_table */
record
  integer(8) col_a;                           /* BIGINT */
  string("\001") col_b;                       /* STRING */
  string("\n") newline;
end
```

---

### SM2-05 — DDL with Inline SQL Comments (--)

**Description:** DDL containing `--` single-line comments. Parser must skip them.

**Input:**
```sql
-- This is the events table
CREATE TABLE events_with_comments (
    event_id  BIGINT,    -- primary key
    user_id   BIGINT,    -- FK to users
    payload   STRING     -- raw JSON
)
-- Partitioned for performance
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: events_with_comments */
record
  integer(8) event_id;                        /* BIGINT */
  integer(8) user_id;                         /* BIGINT */
  string("\001") payload;                     /* STRING */
  string("\n") newline;
end
```

**Pass Criteria:** All `--` comments stripped before parsing. No column loss.

---

### SM2-06 — DDL with Block Comments (/* */)

**Description:** DDL with `/* */` style block comments embedded in the schema.

**Input:**
```sql
/* Master product table */
CREATE TABLE products (
    /* Identifiers */
    product_id   BIGINT,
    sku          VARCHAR(50),
    /* Pricing */
    list_price   DECIMAL(10,2),
    cost_price   DECIMAL(10,2)
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: products */
record
  integer(8) product_id;                      /* BIGINT */
  string("\001",50) sku;                      /* VARCHAR(50) */
  decimal(10,2) list_price;                   /* DECIMAL(10,2) */
  decimal(10,2) cost_price;                   /* DECIMAL(10,2) */
  string("\n") newline;
end
```

---

### SM2-07 — Windows-Style Line Endings (CRLF)

**Description:** DDL file saved on Windows with `\r\n` line endings. Parser must handle carriage returns.

**Input (raw bytes contain `\r\n`):**
```
CREATE TABLE crlf_table (\r\n    id BIGINT,\r\n    name STRING\r\n)\r\nROW FORMAT DELIMITED\r\nFIELDS TERMINATED BY '\001';\r\n
```

**Expected:** Same DML as a Unix-format DDL with identical content. No `\r` character embedded in any field name.

---

### SM2-08 — ONLY One Complex Type Column (No Primitives)

**Description:** Table that has only one column and it is a complex type. Validates that the converter doesn't require any primitives.

**Input:**
```sql
CREATE TABLE array_only (
    tags ARRAY<STRING>
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: array_only */
record
  record
    string("\001")[int] item;
  } tags;
  string("\n") newline;
end
```

---

## 2. Easy — DDL Syntax Variations & Type Aliases

> **Purpose:** Cover Hive type aliases, NUMERIC type, INTERVAL variants, and single-char identifiers — none present in Set 1.

---

### E2-01 — INTEGER as Alias for INT

**Description:** `INTEGER` is a valid Hive alias for `INT`. Must map to `integer(4)`.

**Input:**
```sql
CREATE TABLE integer_alias (
    col_integer INTEGER,
    col_int     INT
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: integer_alias */
record
  integer(4) col_integer;                     /* INTEGER → alias for INT */
  integer(4) col_int;                         /* INT */
  string("\n") newline;
end
```

---

### E2-02 — NUMERIC as Alias for DECIMAL

**Description:** Hive accepts `NUMERIC(p,s)` as a synonym for `DECIMAL(p,s)`.

**Input:**
```sql
CREATE TABLE numeric_alias (
    tax_rate    NUMERIC(5, 4),
    grand_total NUMERIC(12, 2),
    plain_num   NUMERIC
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: numeric_alias */
record
  decimal(5,4) tax_rate;                      /* NUMERIC(5,4) → DECIMAL */
  decimal(12,2) grand_total;                  /* NUMERIC(12,2) → DECIMAL */
  decimal(10,0) plain_num;                    /* NUMERIC → default decimal(10,0) */
  string("\n") newline;
end
```

---

### E2-03 — LONG as Alias for BIGINT (Hive Legacy)

**Description:** Some legacy Hive DDL uses `LONG` as a type. Converter should map it to `integer(8)` or produce a named warning.

**Input:**
```sql
CREATE TABLE legacy_long (
    record_id LONG,
    amount    BIGINT
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected Behavior:**
- `LONG` → `integer(8)` with comment `/* LONG → BIGINT alias */`
- OR: explicit warning logged, field still emitted

---

### E2-04 — Single-Character Column Names

**Description:** Column names that are single alphabetic characters. Parser must not confuse them with keywords.

**Input:**
```sql
CREATE TABLE single_char_cols (
    a BIGINT,
    b STRING,
    c DECIMAL(5,2),
    d BOOLEAN,
    e TIMESTAMP
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: single_char_cols */
record
  integer(8) a;                               /* BIGINT */
  string("\001") b;                           /* STRING */
  decimal(5,2) c;                             /* DECIMAL(5,2) */
  integer(1) d;                               /* BOOLEAN */
  timestamp e;                                /* TIMESTAMP */
  string("\n") newline;
end
```

---

### E2-05 — Column Names Starting with Underscore

**Description:** Hive allows column names starting with `_`. Common in ETL metadata columns.

**Input:**
```sql
CREATE TABLE underscore_cols (
    _ingestion_ts  TIMESTAMP,
    _source_file   STRING,
    _batch_id      BIGINT,
    _is_deleted    BOOLEAN
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: underscore_cols */
record
  timestamp _ingestion_ts;                    /* TIMESTAMP */
  string("\001") _source_file;               /* STRING */
  integer(8) _batch_id;                       /* BIGINT */
  integer(1) _is_deleted;                     /* BOOLEAN */
  string("\n") newline;
end
```

---

### E2-06 — CHAR(1) Single Character

**Description:** Edge value for CHAR — length exactly 1. Validates that the length is preserved and not dropped.

**Input:**
```sql
CREATE TABLE char_one (
    flag         CHAR(1),
    status_code  CHAR(1),
    grade        CHAR(1)
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: char_one */
record
  string("\001",1) flag;                      /* CHAR(1) */
  string("\001",1) status_code;              /* CHAR(1) */
  string("\001",1) grade;                     /* CHAR(1) */
  string("\n") newline;
end
```

---

### E2-07 — DECIMAL with Maximum Hive Precision (38)

**Description:** Hive's maximum DECIMAL precision is 38. Test boundary value.

**Input:**
```sql
CREATE TABLE max_decimal (
    col_max_prec  DECIMAL(38, 38),
    col_max_scale DECIMAL(38, 0),
    col_mid       DECIMAL(19, 9)
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: max_decimal */
record
  decimal(38,38) col_max_prec;               /* DECIMAL(38,38) */
  decimal(38,0) col_max_scale;               /* DECIMAL(38,0) */
  decimal(19,9) col_mid;                      /* DECIMAL(19,9) */
  string("\n") newline;
end
```

---

### E2-08 — LINES TERMINATED BY Clause

**Description:** DDL specifies a custom line terminator (`LINES TERMINATED BY`). Validates that the converter uses this for the trailing `newline` field.

**Input:**
```sql
CREATE TABLE custom_newline (
    id   BIGINT,
    name STRING
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001'
LINES TERMINATED BY '\n';
```

**Expected DML Output:**
```
/* Generated from Hive Table: custom_newline */
record
  integer(8) id;                              /* BIGINT */
  string("\001") name;                        /* STRING */
  string("\n") newline;
end
```

**Variant — Custom Line Terminator:**
```sql
LINES TERMINATED BY '\r\n';
```
**Expected:** `string("\r\n") newline;`

---

### E2-09 — Trailing Comma in Column List

**Description:** Some DDL generators emit a trailing comma after the last column (before the closing parenthesis). Tests parser tolerance.

**Input:**
```sql
CREATE TABLE trailing_comma (
    id     BIGINT,
    name   STRING,
    amount DECIMAL(10,2),
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected Behavior:**
- Either: parsed correctly, trailing comma silently ignored
- Or: clear parse error — `"Unexpected token ')' after ','"`
- Must NOT emit an extra blank field

---

### E2-10 — VARCHAR at Maximum Hive Length (65535)

**Description:** VARCHAR maximum length in Hive is 65535. Test boundary.

**Input:**
```sql
CREATE TABLE max_varchar (
    big_text VARCHAR(65535),
    mid_text VARCHAR(32767),
    tiny_text VARCHAR(1)
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: max_varchar */
record
  string("\001",65535) big_text;             /* VARCHAR(65535) */
  string("\001",32767) mid_text;             /* VARCHAR(32767) */
  string("\001",1) tiny_text;               /* VARCHAR(1) */
  string("\n") newline;
end
```

---

## 3. Medium — Non-STRING MAP Keys, Collection Terminators & STRUCT with Collections

> **Purpose:** Cover MAP with integer/date/boolean keys, COLLECTION ITEMS TERMINATED BY, MAP KEYS TERMINATED BY, and STRUCTs that contain ARRAYs or MAPs internally — none covered in Set 1.

---

### M2-01 — MAP with INT Key

**Description:** MAP keys can be any primitive. INT key is common in dimension lookups.

**Input:**
```sql
CREATE TABLE int_key_map (
    id_to_name MAP<INT, STRING>
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: int_key_map */
record
  record
    record
      integer(4) key;
      string("\001") value;
    } [int] map_entries;
  } id_to_name;
  string("\n") newline;
end
```

---

### M2-02 — MAP with BIGINT Key

**Input:**
```sql
CREATE TABLE bigint_key_map (
    user_scores MAP<BIGINT, DECIMAL(5,2)>
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: bigint_key_map */
record
  record
    record
      integer(8) key;
      decimal(5,2) value;
    } [int] map_entries;
  } user_scores;
  string("\n") newline;
end
```

---

### M2-03 — MAP with BOOLEAN Key

**Description:** Unusual but valid — BOOLEAN key. Two possible keys (true/false). Tests key type variety.

**Input:**
```sql
CREATE TABLE bool_key_map (
    flag_counts MAP<BOOLEAN, INT>
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: bool_key_map */
record
  record
    record
      integer(1) key;
      integer(4) value;
    } [int] map_entries;
  } flag_counts;
  string("\n") newline;
end
```

---

### M2-04 — MAP with TIMESTAMP Value

**Input:**
```sql
CREATE TABLE event_timestamps (
    event_times MAP<STRING, TIMESTAMP>
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: event_timestamps */
record
  record
    record
      string("\001") key;
      timestamp value;
    } [int] map_entries;
  } event_times;
  string("\n") newline;
end
```

---

### M2-05 — MAP with DATE Value

**Input:**
```sql
CREATE TABLE deadline_map (
    milestones MAP<STRING, DATE>
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: deadline_map */
record
  record
    record
      string("\001") key;
      date value;
    } [int] map_entries;
  } milestones;
  string("\n") newline;
end
```

---

### M2-06 — COLLECTION ITEMS TERMINATED BY Clause

**Description:** Hive DDL can specify `COLLECTION ITEMS TERMINATED BY` to define the delimiter for ARRAY and STRUCT elements. Converter should note or use this.

**Input:**
```sql
CREATE TABLE collection_delim (
    tags ARRAY<STRING>
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001'
COLLECTION ITEMS TERMINATED BY '\002';
```

**Expected Behavior:**
- DML is generated correctly for the ARRAY
- The collection delimiter `\002` is either: (a) noted in a comment, or (b) used in the vector definition if the DML spec supports it
- No crash

---

### M2-07 — MAP KEYS TERMINATED BY Clause

**Description:** Hive DDL with `MAP KEYS TERMINATED BY` defining the separator between MAP key and value in the file.

**Input:**
```sql
CREATE TABLE map_key_delim (
    kv_pairs MAP<STRING, STRING>
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001'
COLLECTION ITEMS TERMINATED BY '\002'
MAP KEYS TERMINATED BY '\003';
```

**Expected Behavior:**
- DML record block generated correctly
- MAP KEYS TERMINATED BY noted as comment or metadata, not lost silently
- No crash

---

### M2-08 — STRUCT with an Embedded ARRAY Field

**Description:** A STRUCT that has one of its fields typed as ARRAY. Tests that the converter handles mixed-type struct fields correctly.

**Input:**
```sql
CREATE TABLE struct_with_array (
    user_detail STRUCT<
        name:   STRING,
        tags:   ARRAY<STRING>,
        age:    INT
    >
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: struct_with_array */
record
  record
    string("\001") name;
    record
      string("\001")[int] item;
    } tags;
    integer(4) age;
  } user_detail;
  string("\n") newline;
end
```

---

### M2-09 — STRUCT with an Embedded MAP Field

**Input:**
```sql
CREATE TABLE struct_with_map (
    product_info STRUCT<
        product_id:  INT,
        attributes:  MAP<STRING, STRING>,
        price:       DECIMAL(8,2)
    >
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: struct_with_map */
record
  record
    integer(4) product_id;
    record
      record
        string("\001") key;
        string("\001") value;
      } [int] map_entries;
    } attributes;
    decimal(8,2) price;
  } product_info;
  string("\n") newline;
end
```

---

### M2-10 — STRUCT with Both ARRAY and MAP Fields

**Description:** A single STRUCT field containing both an ARRAY and a MAP as sub-fields. Common in event schema designs.

**Input:**
```sql
CREATE TABLE enriched_event (
    event STRUCT<
        id:       BIGINT,
        tags:     ARRAY<STRING>,
        props:    MAP<STRING, STRING>,
        score:    DECIMAL(5,2)
    >
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: enriched_event */
record
  record
    integer(8) id;
    record
      string("\001")[int] item;
    } tags;
    record
      record
        string("\001") key;
        string("\001") value;
      } [int] map_entries;
    } props;
    decimal(5,2) score;
  } event;
  string("\n") newline;
end
```

---

### M2-11 — STRUCT with 15 Fields

**Description:** A STRUCT with a large number of flat fields. Tests that all sub-fields are emitted in the correct order without truncation.

**Input:**
```sql
CREATE TABLE wide_struct (
    person STRUCT<
        f01: STRING,
        f02: STRING,
        f03: INT,
        f04: BIGINT,
        f05: DECIMAL(10,2),
        f06: BOOLEAN,
        f07: DATE,
        f08: TIMESTAMP,
        f09: FLOAT,
        f10: DOUBLE,
        f11: VARCHAR(100),
        f12: CHAR(1),
        f13: SMALLINT,
        f14: TINYINT,
        f15: BINARY
    >
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Pass Criteria:**
- All 15 sub-fields present in correct order
- Each typed correctly per mapping table
- Correct outer `record` / `}` wrapping

---

### M2-12 — CLUSTERED BY Clause

**Description:** `CLUSTERED BY` is a Hive DDL clause for bucketing. Converter must skip it without crash.

**Input:**
```sql
CREATE TABLE bucketed_table (
    user_id  BIGINT,
    event    STRING
)
CLUSTERED BY (user_id) INTO 32 BUCKETS
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected:** DML for `user_id` and `event` generated correctly. `CLUSTERED BY` ignored. No crash.

---

### M2-13 — SKEWED BY Clause

**Description:** `SKEWED BY` optimizes storage for skewed values. Must be ignored gracefully.

**Input:**
```sql
CREATE TABLE skewed_table (
    country  STRING,
    revenue  DECIMAL(12,2)
)
SKEWED BY (country) ON ('US', 'IN', 'CN')
STORED AS DIRECTORIES
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected:** DML for `country` and `revenue` generated. `SKEWED BY` clause ignored. No crash.

---

### M2-14 — STORED BY Clause (HBase SerDe)

**Description:** HBase-backed Hive tables use `STORED BY`. Schema must still parse correctly.

**Input:**
```sql
CREATE TABLE hbase_table (
    row_key  STRING,
    col1     STRING,
    col2     BIGINT
)
STORED BY 'org.apache.hadoop.hive.hbase.HBaseStorageHandler'
WITH SERDEPROPERTIES ('hbase.columns.mapping' = ':key,cf1:col1,cf1:col2');
```

**Expected:** DML for `row_key`, `col1`, `col2` generated. `STORED BY` / `WITH SERDEPROPERTIES` ignored. No crash.

---

### M2-15 — Table with TBLPROPERTIES Only (No ROW FORMAT)

**Description:** Table has `TBLPROPERTIES` but no `ROW FORMAT DELIMITED` block.

**Input:**
```sql
CREATE TABLE tbl_props_only (
    id   BIGINT,
    name STRING
)
TBLPROPERTIES ('creator'='utkarsh', 'version'='1');
```

**Expected Behavior:**
- DML generated with system-default delimiter for string fields
- TBLPROPERTIES silently ignored
- No crash

---

## 4. Hard — ARRAY<MAP>, MAP<MAP>, Branched STRUCT & Malformed Input Handling

> **Purpose:** Cover type combinations and error scenarios not present in Set 1.

---

### H2-01 — ARRAY of MAP

**Description:** Each element of the ARRAY is a MAP. Common in JSON-sourced schemas.

**Input:**
```sql
CREATE TABLE array_of_map (
    kv_list ARRAY<MAP<STRING, STRING>>
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: array_of_map */
record
  record
    record
      record
        string("\001") key;
        string("\001") value;
      } [int] map_entries;
    } [int] item;
  } kv_list;
  string("\n") newline;
end
```

---

### H2-02 — ARRAY of MAP with STRUCT Value

**Description:** Multi-level combination: ARRAY > MAP > STRUCT.

**Input:**
```sql
CREATE TABLE array_map_struct (
    records ARRAY<MAP<STRING, STRUCT<
        id:    INT,
        label: STRING
    >>>
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: array_map_struct */
record
  record
    record
      record
        string("\001") key;
        record
          integer(4) id;
          string("\001") label;
        } value;
      } [int] map_entries;
    } [int] item;
  } records;
  string("\n") newline;
end
```

---

### H2-03 — MAP of MAP (Nested MAP Value)

**Description:** A MAP whose value type is itself another MAP.

**Input:**
```sql
CREATE TABLE map_of_map (
    nested_map MAP<STRING, MAP<STRING, INT>>
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: map_of_map */
record
  record
    record
      string("\001") key;
      record
        record
          string("\001") key;
          integer(4) value;
        } [int] map_entries;
      } value;
    } [int] map_entries;
  } nested_map;
  string("\n") newline;
end
```

---

### H2-04 — ARRAY of ARRAY of STRUCT (3-Level)

**Description:** ARRAY > ARRAY > STRUCT — tests three levels of compound nesting.

**Input:**
```sql
CREATE TABLE triple_nested (
    grid ARRAY<ARRAY<STRUCT<
        x: INT,
        y: INT,
        label: STRING
    >>>
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: triple_nested */
record
  record
    record
      record
        integer(4) x;
        integer(4) y;
        string("\001") label;
      } [int] item;
    } [int] item;
  } grid;
  string("\n") newline;
end
```

---

### H2-05 — Branched STRUCT (Multiple Complex Sub-Fields)

**Description:** A STRUCT where multiple sub-fields are themselves complex types (one ARRAY, one MAP, one nested STRUCT). Tests correct DML indentation for a "wide" nesting tree.

**Input:**
```sql
CREATE TABLE branched (
    root STRUCT<
        tags:    ARRAY<STRING>,
        props:   MAP<STRING, INT>,
        child:   STRUCT<
            name:   STRING,
            scores: ARRAY<DECIMAL(5,2)>
        >,
        count:   BIGINT
    >
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: branched */
record
  record
    record
      string("\001")[int] item;
    } tags;
    record
      record
        string("\001") key;
        integer(4) value;
      } [int] map_entries;
    } props;
    record
      string("\001") name;
      record
        decimal(5,2)[int] item;
      } scores;
    } child;
    integer(8) count;
  } root;
  string("\n") newline;
end
```

---

### H2-06 — STRUCT with Repeated Sub-Field Names Across Levels

**Description:** Two different STRUCTs at different columns both have a sub-field named `id`. Tests that there is no naming collision between separate struct definitions.

**Input:**
```sql
CREATE TABLE dual_struct (
    person STRUCT<
        id:   INT,
        name: STRING
    >,
    company STRUCT<
        id:   BIGINT,
        name: STRING,
        code: VARCHAR(10)
    >
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: dual_struct */
record
  record
    integer(4) id;
    string("\001") name;
  } person;
  record
    integer(8) id;
    string("\001") name;
    string("\001",10) code;
  } company;
  string("\n") newline;
end
```

**Pass Criteria:** Both `id` fields exist independently. No collision or merge.

---

### H2-07 — Column Name Same as Table Name

**Description:** Column name matches the table name exactly.

**Input:**
```sql
CREATE TABLE events (
    events   STRING,
    event_id BIGINT
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected:** DML has `string("\001") events;` — no special treatment. No crash.

---

### H2-08 — Partition Column Name Collides with Regular Column Name

**Description:** A partition column has the same name as a regular data column. Invalid in Hive, but converter must handle gracefully.

**Input:**
```sql
CREATE TABLE col_collision (
    year   INT,
    amount DECIMAL(10,2)
)
PARTITIONED BY (year INT)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected Behavior:**
- Clear error: `"Partition column 'year' conflicts with existing column 'year'"`
- Converter does NOT silently duplicate the field
- Does NOT crash with an unhandled exception

---

### H2-09 — Non-ASCII Column Name (Unicode Identifier)

**Description:** Hive supports Unicode identifiers when backtick-quoted. Converter must not corrupt or crash.

**Input:**
```sql
CREATE TABLE unicode_cols (
    `产品名称`   STRING,
    `数量`       INT,
    `金额`       DECIMAL(10,2)
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected Behavior:**
- Either: Unicode names preserved as-is in DML output
- Or: A mapping to ASCII-safe identifiers with a comment
- Must NOT crash or produce garbled output

---

### H2-10 — Empty STRUCT (No Sub-Fields)

**Description:** An edge case where a STRUCT has zero fields. Invalid in Hive schema but tests parser boundary.

**Input:**
```sql
CREATE TABLE empty_struct (
    empty_col STRUCT<>
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected Behavior:**
- Clear error: `"Empty STRUCT definition for column 'empty_col'"`
- Or: Emits an empty `record { } empty_col;` block with a warning
- Must NOT produce silently broken DML

---

### H2-11 — Completely Invalid DDL Input (Non-SQL String)

**Description:** Input is not DDL at all. Tests that the converter fails fast with a clear error.

**Input:**
```
Hello, this is not SQL at all!
```

**Expected Behavior:**
- Error: `"Input does not appear to be valid Hive DDL"`
- No partial DML output
- No unhandled exception / stack trace exposed to caller

---

### H2-12 — ALTER TABLE Instead of CREATE TABLE

**Description:** Caller accidentally passes an `ALTER TABLE` statement.

**Input:**
```sql
ALTER TABLE sales_data ADD COLUMNS (new_col STRING);
```

**Expected Behavior:**
- Error: `"Expected CREATE TABLE statement, got ALTER TABLE"`
- Or: Graceful rejection with a descriptive message
- Must NOT silently return empty output

---

### H2-13 — CREATE VIEW Instead of CREATE TABLE

**Description:** A `CREATE VIEW` statement passed to the converter.

**Input:**
```sql
CREATE VIEW sales_summary AS
SELECT year, SUM(amount) FROM sales_data GROUP BY year;
```

**Expected Behavior:**
- Error: `"CREATE VIEW is not supported — provide a CREATE TABLE statement"`
- Must NOT attempt to parse the SELECT body as a schema

---

### H2-14 — DECIMAL Scale Larger Than Precision

**Description:** `DECIMAL(4, 6)` — scale greater than precision. Invalid in Hive.

**Input:**
```sql
CREATE TABLE invalid_decimal (
    col1 DECIMAL(4, 6)
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected Behavior:**
- Error: `"Invalid DECIMAL: scale (6) cannot exceed precision (4)"`
- No partial DML emitted
- Clear column reference in error message

---

### H2-15 — Hive 3.x TIMESTAMP WITH LOCAL TIME ZONE

**Description:** Hive 3.x introduced `TIMESTAMP WITH LOCAL TIME ZONE`. Converter must handle or reject with a clear message.

**Input:**
```sql
CREATE TABLE tz_aware (
    event_ts  TIMESTAMP WITH LOCAL TIME ZONE,
    created   TIMESTAMP
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected Behavior:**
- Either: `TIMESTAMP WITH LOCAL TIME ZONE` → `timestamp` (with comment noting timezone info is lost)
- Or: Named warning: `"TIMESTAMP WITH LOCAL TIME ZONE mapped to timestamp (timezone metadata discarded)"`
- Must NOT crash

---

### H2-16 — Table with 10 Partition Columns of All Primitive Types

**Description:** Stress-tests the partition column rendering with diverse types.

**Input:**
```sql
CREATE TABLE diverse_partitions (
    record_id BIGINT
)
PARTITIONED BY (
    p_tinyint   TINYINT,
    p_smallint  SMALLINT,
    p_int       INT,
    p_bigint    BIGINT,
    p_float     FLOAT,
    p_double    DOUBLE,
    p_decimal   DECIMAL(10,2),
    p_string    STRING,
    p_date      DATE,
    p_boolean   BOOLEAN
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Expected DML Output:**
```
/* Generated from Hive Table: diverse_partitions */
record
  integer(8) record_id;                       /* BIGINT */
  /* Partition columns are often included as standard fields */
  integer(1) p_tinyint;                       /* TINYINT */
  integer(2) p_smallint;                      /* SMALLINT */
  integer(4) p_int;                           /* INT */
  integer(8) p_bigint;                        /* BIGINT */
  float(4) p_float;                           /* FLOAT */
  float(8) p_double;                          /* DOUBLE */
  decimal(10,2) p_decimal;                    /* DECIMAL(10,2) */
  string("\001") p_string;                    /* STRING */
  date p_date;                                /* DATE */
  integer(1) p_boolean;                       /* BOOLEAN */
  string("\n") newline;
end
```

---

## 5. Stress Tests

> **Purpose:** High-volume tests using schemas and patterns not tested in Set 1.

---

### ST2-01 — 1000-Column Wide Table (All BIGINT)

**Description:** Extreme width test with a homogeneous type. Focus is on parser memory and output completeness at 10× the volume of Set 1 ST-01.

**Generation Rule:** `col_0001 BIGINT` through `col_1000 BIGINT`

**Pass Criteria:**
- Exactly 1000 field entries in DML
- No skipped or duplicated columns
- `newline` field present at end
- Conversion completes within 60 seconds

---

### ST2-02 — 20-Level Deep STRUCT Nesting

**Description:** Extends Set 1's 10-level test to 20 levels. Tests parser recursion limit and stack safety.

**Input (abbreviated):**
```sql
CREATE TABLE ultra_deep (
    l01 STRUCT<
        l02: STRUCT<
            l03: STRUCT<
                l04: STRUCT<
                    l05: STRUCT<
                        l06: STRUCT<
                            l07: STRUCT<
                                l08: STRUCT<
                                    l09: STRUCT<
                                        l10: STRUCT<
                                            l11: STRUCT<
                                                l12: STRUCT<
                                                    l13: STRUCT<
                                                        l14: STRUCT<
                                                            l15: STRUCT<
                                                                l16: STRUCT<
                                                                    l17: STRUCT<
                                                                        l18: STRUCT<
                                                                            l19: STRUCT<
                                                                                l20: STRUCT<
                                                                                    leaf: STRING
                                                                                >
                                                                            >
                                                                        >
                                                                    >
                                                                >
                                                            >
                                                        >
                                                    >
                                                >
                                            >
                                        >
                                    >
                                >
                            >
                        >
                    >
                >
            >
        >
    >
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\001';
```

**Pass Criteria:**
- 20 nested `record` blocks + outer container
- 20 closing `}` lines + `end`
- No stack overflow / recursion limit error

---

### ST2-03 — 100 STRUCT Columns (All Flat, 5 Fields Each)

**Description:** Table with 100 top-level STRUCT columns, each having 5 primitive sub-fields. Tests repeated STRUCT generation for correctness and performance.

**Generation Rule:** `struct_001` through `struct_100`, each containing:
```
STRUCT<a: INT, b: STRING, c: DECIMAL(5,2), d: BOOLEAN, e: BIGINT>
```

**Pass Criteria:**
- 100 outer `record { ... }` blocks
- Each block has exactly 5 sub-fields
- No field from one STRUCT bleeds into another
- Conversion completes within 30 seconds

---

### ST2-04 — Table with 50 Columns of ARRAY<MAP<STRING, STRING>>

**Description:** Same complex type repeated 50 times. Tests that repeated identical structures don't cause shared-state bugs.

**Generation Rule:** `kv_001` through `kv_050`, each typed as `ARRAY<MAP<STRING, STRING>>`

**Pass Criteria:**
- 50 completely independent ARRAY>MAP blocks
- Each has its own `map_entries` vector definition
- No structure sharing or reference aliasing in output

---

### ST2-05 — Deeply Branched Schema (Wide + Deep Combined)

**Description:** A 10-column table where each column is a STRUCT with 10 sub-fields, and 3 of those sub-fields are themselves complex types. Tests the converter under both breadth and depth simultaneously.

**Structure per column:**
```
STRUCT<
    f1: STRING, f2: INT, f3: BIGINT, f4: DECIMAL(5,2),
    f5: ARRAY<STRING>,
    f6: MAP<STRING, INT>,
    f7: STRUCT<x: INT, y: INT>,
    f8: BOOLEAN, f9: DATE, f10: TIMESTAMP
>
```

**Pass Criteria:**
- All 10 top-level STRUCT columns generated
- All 10 sub-fields per STRUCT present in correct order
- ARRAY, MAP, and nested STRUCT rendered correctly within each outer STRUCT
- No field or block lost due to depth/breadth interaction
- Conversion completes within 60 seconds

---

### ST2-06 — 100-Column Mixed: All Different Delimiters Per Batch

**Description:** Run the converter 10 times on the same 10-column table, each time with a different `FIELDS TERMINATED BY` delimiter. Validates that delimiter state does not leak between runs.

**Delimiters to test (one table DDL per run):**

| Run | Delimiter  | Expected String Prefix  |
|-----|------------|-------------------------|
| 1   | `'\001'`   | `string("\001")`        |
| 2   | `'\t'`     | `string("\t")`          |
| 3   | `','`      | `string(",")`           |
| 4   | `'|'`      | `string("|")`           |
| 5   | `';'`      | `string(";")`           |
| 6   | `':'`      | `string(":")`           |
| 7   | `'\002'`   | `string("\002")`        |
| 8   | `'^'`      | `string("^")`           |
| 9   | `'~'`      | `string("~")`           |
| 10  | `'\003'`   | `string("\003")`        |

**Pass Criteria:**
- Each run produces the correct delimiter in string field definitions
- No previous run's delimiter appears in a subsequent run's output

---

### ST2-07 — Consecutive Conversions (Statelessness Test)

**Description:** Run the converter 20 times in sequence on 20 different DDL inputs. After all runs, verify that each output matches what it would produce if run in isolation. Detects global/static state leaks.

**Inputs:** 20 DDL files from the following test IDs (mix of Set 1 and Set 2):
`E-07, M-06, H-01, H-05, H-14, M2-08, M2-10, H2-01, H2-02, H2-05, E2-04, E2-07, M2-01, M2-04, H2-04, H2-06, SM2-01, SM2-03, E2-09 (error case), H2-11 (error case)`

**Pass Criteria:**
- All successful conversions match isolated run output byte-for-byte
- Error cases produce the same error message in run 19–20 as they would in isolation
- No cross-contamination of type state, delimiter state, or column registry

---

### ST2-08 — Maximum Realistic Schema (Medallion Lakehouse Simulation)

**Description:** Simulates a real-world Gold-layer lakehouse table — wide, mixed types, multiple complex columns, and many partition keys.

**Schema Summary:**
- 60 primitive columns (IDs, metrics, flags, timestamps)
- 10 ARRAY columns (tags, categories, event sequences)
- 10 MAP columns (metadata, properties, scores)
- 10 STRUCT columns (addresses, devices, sessions)
- 5 STRUCT columns containing embedded ARRAY or MAP
- 10 partition columns (date, region, channel, tier, etc.)

**Total column count:** 105 (95 data + 10 partition)

**Pass Criteria:**
- All 105 columns present in DML output
- All complex types correctly nested
- Partition columns appended last, before `newline`
- Conversion completes within 120 seconds
- DML is syntactically valid (passes DML validator if available)

---

### ST2-09 — Repeated Parsing of Identical DDL (Idempotency)

**Description:** Parse the same DDL 100 times. Verify that every output is byte-identical. Detects non-determinism, random ordering bugs, or timestamp injection.

**Input:** Use the `analytics_event` table from Set 1 H-14.

**Pass Criteria:**
- All 100 outputs are byte-identical
- Run time per invocation is within 10% of the mean

---

### ST2-10 — DDL String of 50,000 Characters

**Description:** A single DDL string that is 50K characters long, achieved via a table with many columns and verbose COMMENT clauses on each column. Tests parser memory and string-handling at scale.

**Generation Rule:**
- 200 columns, each with a `COMMENT 'This is a long descriptive comment for column N that describes its purpose in detail'`
- Each COMMENT string padded to ~200 characters

**Pass Criteria:**
- All 200 columns correctly parsed (comments stripped, not included in column names)
- Conversion completes without OOM or timeout
- DML output has exactly 200 field lines + `newline` + `end`

---

## Appendix — New Type Mapping Additions (Set 2)

| Hive Type                       | DML Type       | Notes                                        |
|---------------------------------|----------------|----------------------------------------------|
| INTEGER                         | integer(4)     | Alias for INT                                |
| NUMERIC(p,s)                    | decimal(p,s)   | Alias for DECIMAL                            |
| LONG                            | integer(8)     | Legacy alias for BIGINT                      |
| TIMESTAMP WITH LOCAL TIME ZONE  | timestamp      | Timezone metadata discarded (with warning)   |
| MAP<INT, V>                     | record { record { integer(4) key; V value; } [int] map_entries; } | INT key |
| MAP<BIGINT, V>                  | record { record { integer(8) key; V value; } [int] map_entries; } | BIGINT key |
| MAP<BOOLEAN, V>                 | record { record { integer(1) key; V value; } [int] map_entries; } | BOOLEAN key |
| ARRAY<MAP<K,V>>                 | record { record { record { K key; V value; } [int] map_entries; } [int] item; } | |
| MAP<K, MAP<K2,V2>>              | Nested map_entries vector                    | MAP of MAP                                   |

---

*Generated for Hive → DML Schema Converter · Test Suite v2.0 — No overlap with Test Set 1*
