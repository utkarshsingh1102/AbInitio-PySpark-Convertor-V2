# COBOL Copybook → Ab Initio DML — Test Cases

**Scope of the converter under test**
- **Input**: COBOL copybooks, Data Division only
- **Output**: Ab Initio DML `record … end` schema descriptor
- **Out of scope**: Procedure Division, file I/O, control flow, runtime data

All test cases below validate **schema-level** transformation only.

**Legend**
- **Type**: Positive (P), Negative (N), Edge (E)
- **Priority**: High (H), Medium (M), Low (L)

---

## 1. Primitive PIC Clause Mapping

### TC-001 — Unsigned numeric `PIC 9(n)` → `decimal(n)`
- **Type / Priority**: P / H
- **Input**:
  ```cobol
  01 EMP-ID    PIC 9(5).
  ```
- **Expected DML**:
  ```
  record
      decimal(5) emp_id;
  end
  ```
- **Pass Criteria**: Width preserved; name lower-cased with underscore.

### TC-002 — Alphanumeric `PIC X(n)` → `string(n)`
- **Type / Priority**: P / H
- **Input**: `01 EMP-NAME PIC X(30).`
- **Expected DML**: `string(30) emp_name;`

### TC-003 — National `PIC N(n)` → `ustring(n)`
- **Type / Priority**: P / M
- **Input**: `01 CUST-NAME-NAT PIC N(20).`
- **Expected DML**: `ustring(20) cust_name_nat;`

### TC-004 — Signed numeric `PIC S9(n)` (DISPLAY) → signed decimal
- **Type / Priority**: P / H
- **Input**: `01 BAL PIC S9(9).`
- **Expected DML**: Signed zoned decimal representation, e.g. `decimal(9) bal;` with appropriate sign attribute per converter convention.

### TC-005 — Implied decimal `PIC 9(7)V99` → scaled decimal
- **Type / Priority**: P / H
- **Input**: `01 PRICE PIC 9(7)V99.`
- **Expected DML**: `decimal(9.2) price;` (or equivalent `decimal("\.",9)` form per project standard).
- **Pass Criteria**: Scale = 2; total length = 9; no actual decimal point in storage.

### TC-006 — `PIC S9(n)V9(m) COMP-3` → `packed_decimal`
- **Type / Priority**: P / H
- **Input**: `01 SALARY PIC S9(7)V99 COMP-3.`
- **Expected DML**: `packed_decimal(5.2, signed) salary;` (length 5 bytes for 9 digits + sign nibble).
- **Pass Criteria**: Byte length correctly computed as `CEIL((digits+1)/2)`.

### TC-007 — `PIC 9(n) COMP` (binary) → `integer(b)`
- **Type / Priority**: P / H
- **Input examples & expected sizes**:

  | COBOL | DML |
  |---|---|
  | `PIC 9(4) COMP.` | `integer(2)` |
  | `PIC 9(8) COMP.` | `integer(4)` |
  | `PIC 9(18) COMP.` | `integer(8)` |
- **Pass Criteria**: Correct binary width per IBM rules (≤4 digits=2B, 5–9=4B, 10–18=8B).

### TC-008 — `COMP-1` / `COMP-2` → `real`
- **Type / Priority**: P / M
- **Expected DML**: `real(4)` for COMP-1, `real(8)` for COMP-2.

### TC-009 — `COMP-5` (native binary) handling
- **Type / Priority**: E / M
- **Pass Criteria**: Mapped to `integer(b)` matching declared digits; documented as native-binary in comment.

---

## 2. Sign Representation Variants

### TC-010 — `SIGN IS LEADING` / `TRAILING`
- **Type / Priority**: E / M
- **Input**: `01 AMT PIC S9(5) SIGN IS LEADING.`
- **Pass Criteria**: Generated decimal carries leading-sign attribute consistent with Ab Initio DML conventions.

### TC-011 — `SIGN IS LEADING SEPARATE`
- **Type / Priority**: E / M
- **Pass Criteria**: Length increases by 1 byte for separate sign character.

### TC-012 — Default trailing overpunch sign for `S9(n)` DISPLAY
- **Type / Priority**: P / H
- **Pass Criteria**: Correct zoned-decimal-with-overpunch encoding emitted.

---

## 3. Group Items & Nesting

### TC-013 — Single-level group → flat record
- **Type / Priority**: P / H
- **Input**:
  ```cobol
  01 CUSTOMER-REC.
     05 CUST-ID    PIC 9(6).
     05 CUST-NAME  PIC X(40).
     05 CUST-BAL   PIC S9(9)V99 COMP-3.
  ```
- **Expected DML**:
  ```
  record
      decimal(6) cust_id;
      string(40) cust_name;
      packed_decimal(6.2, signed) cust_bal;
  end
  ```

### TC-014 — Nested groups (multiple levels) → nested `record … end`
- **Type / Priority**: P / H
- **Input**:
  ```cobol
  01 ORDER-REC.
     05 ORDER-HDR.
        10 ORDER-ID   PIC 9(8).
        10 ORDER-DT   PIC 9(8).
     05 ORDER-AMT     PIC S9(9)V99 COMP-3.
  ```
- **Expected DML**: Nested subrecord block for `order_hdr`, then `order_amt` at outer level.

### TC-015 — Deeply nested (≥4 levels)
- **Type / Priority**: E / M
- **Pass Criteria**: All levels preserved; indentation correct; no flattening unless configured.

### TC-016 — Multiple `01` items in one copybook
- **Type / Priority**: E / M
- **Pass Criteria**: Each `01` produces a separate top-level `record … end` or is flagged per project convention.

---

## 4. OCCURS (Arrays / Vectors)

### TC-017 — Fixed `OCCURS n TIMES` → array `[n]`
- **Type / Priority**: P / H
- **Input**: `05 MONTHLY-SALES OCCURS 12 TIMES PIC 9(7)V99.`
- **Expected DML**: `decimal(9.2)[12] monthly_sales;`

### TC-018 — `OCCURS` on a group item → array of subrecords
- **Type / Priority**: P / H
- **Input**:
  ```cobol
  05 LINE-ITEM OCCURS 10 TIMES.
     10 ITEM-ID   PIC 9(6).
     10 ITEM-QTY  PIC 9(4) COMP.
  ```
- **Expected DML**: Array of subrecord with two fields, length 10.

### TC-019 — `OCCURS DEPENDING ON` (variable-length) → vector with prefix
- **Type / Priority**: E / H
- **Input**:
  ```cobol
  05 LINE-CNT     PIC 9(3) COMP.
  05 LINES OCCURS 1 TO 100 TIMES DEPENDING ON LINE-CNT
            PIC X(80).
  ```
- **Expected DML**: Vector keyed off `line_cnt` (e.g. `string(80)[integer(2)] lines;` or DML `[line_cnt]` form per convention).

### TC-020 — Nested OCCURS (2-D arrays)
- **Type / Priority**: E / M
- **Pass Criteria**: Outer + inner arrays preserved as nested `[n][m]`.

### TC-021 — `OCCURS` with `INDEXED BY` / `KEY IS`
- **Type / Priority**: E / L
- **Pass Criteria**: Indexes ignored (runtime-only); KEY IS noted in comment.

---

## 5. REDEFINES

### TC-022 — Simple REDEFINES of a numeric as alphanumeric
- **Type / Priority**: E / H
- **Input**:
  ```cobol
  05 RAW-DATE     PIC 9(8).
  05 DATE-PARTS REDEFINES RAW-DATE.
     10 YYYY      PIC 9(4).
     10 MM        PIC 9(2).
     10 DD        PIC 9(2).
  ```
- **Pass Criteria**: One physical field emitted; redefinition recorded as comment OR union/alternate view per project standard. No double-counting of bytes.

### TC-023 — REDEFINES with different lengths (warning)
- **Type / Priority**: N / M
- **Pass Criteria**: If lengths differ, converter emits warning and follows the longer length.

### TC-024 — Nested REDEFINES
- **Type / Priority**: E / M
- **Pass Criteria**: Resolved without infinite loop; comments preserved.

### TC-025 — REDEFINES of a group by another group
- **Type / Priority**: E / M
- **Pass Criteria**: Both views captured; only one occupies storage in DML output.

---

## 6. FILLER, Condition Names, and Skipped Items

### TC-026 — `FILLER` → `void(n)` or named padding
- **Type / Priority**: P / H
- **Input**: `05 FILLER PIC X(10).`
- **Expected DML**: `void(10);` (or `string(10) filler_n;` per config).

### TC-027 — Multiple FILLERs in same record → unique names
- **Type / Priority**: P / M
- **Pass Criteria**: `void(...)` for each, or auto-numbered (`filler_1`, `filler_2`) without collision.

### TC-028 — Level-88 condition names → ignored
- **Type / Priority**: P / H
- **Input**:
  ```cobol
  05 STATUS-CD PIC X.
     88 ACTIVE      VALUE 'A'.
     88 INACTIVE    VALUE 'I'.
  ```
- **Pass Criteria**: Only `string(1) status_cd;` emitted; 88-levels logged but not output.

### TC-029 — Level-66 RENAMES → ignored or commented
- **Type / Priority**: E / L
- **Pass Criteria**: No DML output for 66-level; comment recorded.

### TC-030 — `JUSTIFIED RIGHT` clause
- **Type / Priority**: E / L
- **Pass Criteria**: Mapped to string with right-justify attribute or noted in comment.

---

## 7. Naming, Reserved Words, and Length Rules

### TC-031 — Hyphen → underscore in identifiers
- **Type / Priority**: P / H
- **Input**: `01 FIRST-NAME PIC X(20).`
- **Expected DML**: `string(20) first_name;`

### TC-032 — Mixed case handling
- **Type / Priority**: P / M
- **Pass Criteria**: Output uses consistent casing (typically lower) regardless of input case.

### TC-033 — Ab Initio DML reserved words as field names
- **Type / Priority**: E / H
- **Input**: A field literally named e.g. `RECORD` or `END`.
- **Pass Criteria**: Auto-renamed (e.g. `record_`) or quoted/escaped per project rule; never produces invalid DML.

### TC-034 — Identifiers exceeding DML length limits
- **Type / Priority**: E / M
- **Pass Criteria**: Truncated deterministically; mapping recorded in conversion log.

### TC-035 — Duplicate field names within same record
- **Type / Priority**: N / H
- **Pass Criteria**: Detected; either fail with clear error or auto-disambiguate (per config).

---

## 8. COPY Statement & Copybook Composition

### TC-036 — `COPY` of another copybook
- **Type / Priority**: P / H
- **Pass Criteria**: Referenced copybook expanded in place; resulting record contains all fields.

### TC-037 — `COPY ... REPLACING ==X== BY ==Y==`
- **Type / Priority**: E / M
- **Pass Criteria**: Substitution applied before DML generation; field names reflect replacements.

### TC-038 — Nested `COPY` (copybook within copybook)
- **Type / Priority**: E / M
- **Pass Criteria**: Recursive expansion completes; cycle protection in place.

### TC-039 — Missing copybook on COPY path
- **Type / Priority**: N / H
- **Pass Criteria**: Clear error message naming the missing file; no partial DML emitted.

---

## 9. Edge Cases & Unusual PIC Clauses

### TC-040 — Edited numeric `PIC ZZ,ZZ9.99` (display-only)
- **Type / Priority**: N / M
- **Pass Criteria**: Either (a) mapped to `string(n)` with the formatted width, or (b) rejected with clear message — but never silently misrepresented as numeric.

### TC-041 — Edited alphanumeric (`/`, `B` insertion) in PIC
- **Type / Priority**: E / L
- **Pass Criteria**: Treated as `string(n)` with total edited length.

### TC-042 — `PIC` with `BLANK WHEN ZERO`
- **Type / Priority**: E / L
- **Pass Criteria**: Storage size unchanged in DML; clause preserved as comment.

### TC-043 — `USAGE POINTER` / `USAGE INDEX`
- **Type / Priority**: N / M
- **Pass Criteria**: Either rejected as unsupported or mapped to fixed-size binary with warning — must not silently disappear.

### TC-044 — `SYNCHRONIZED` / `SYNC` clause
- **Type / Priority**: E / M
- **Pass Criteria**: Alignment respected (insert `void(n)` padding) or noted in comment per project rule.

### TC-045 — Empty copybook / only comments
- **Type / Priority**: E / M
- **Pass Criteria**: Tool exits cleanly with informative message; no empty `record end` block.

### TC-046 — Comments in copybook (`* …` in column 7)
- **Type / Priority**: P / M
- **Pass Criteria**: Preserved as DML comments adjacent to corresponding fields.

### TC-047 — Non-standard column layout (free-format COBOL)
- **Type / Priority**: E / M
- **Pass Criteria**: Parser handles both fixed (col 7-72) and free-format input per config.

---

## 10. Negative & Validation Tests

### TC-048 — Invalid PIC character (e.g. `PIC Q(5)`)
- **Type**: N / H
- **Pass Criteria**: Parse error with line number; conversion aborts for that record.

### TC-049 — Mismatched group/level numbers (e.g. 05 then 03)
- **Type**: N / M
- **Pass Criteria**: Validation error; no DML emitted for invalid block.

### TC-050 — Circular REDEFINES
- **Type**: N / M
- **Pass Criteria**: Detected and reported; converter does not hang.

---

## 11. Output Quality / Non-Functional

### TC-051 — Generated DML parses successfully
- **Pass Criteria**: Output passes Ab Initio DML validation (`m_db test` or equivalent) on every test case.

### TC-052 — Byte-length round-trip
- **Pass Criteria**: Sum of DML field lengths equals COBOL record length for every fixed-length copybook.

### TC-053 — Idempotency
- **Pass Criteria**: Re-running the converter on the same input produces byte-identical DML output.

### TC-054 — Traceability
- **Pass Criteria**: Each DML field carries a comment with originating copybook + line number.

### TC-055 — Deterministic ordering
- **Pass Criteria**: Field order in DML matches physical order in copybook regardless of platform / locale.

---

## Recommended Regression Corpus

Maintain one sample copybook per category above so every build re-runs TC-001 → TC-055. Track:

1. Source copybook, expected DML, actual DML, diff.
2. Byte-length comparison (COBOL vs DML).
3. DML-validator pass/fail.
4. Aggregate score = `passed / total × 100`.
