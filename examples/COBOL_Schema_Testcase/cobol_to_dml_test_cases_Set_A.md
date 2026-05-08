# COBOL to DML Conversion — Test Cases

This document contains test cases for validating a COBOL-to-DML (Data Manipulation Language / SQL) conversion application. Test cases cover data type mapping, file operations, control flow, edge cases, and error handling.

**Legend**
- **Type**: Positive (P), Negative (N), Edge (E), Performance (Pf)
- **Priority**: High (H), Medium (M), Low (L)

---

## 1. Data Type Mapping

### TC-001 — Numeric PIC clause to INTEGER
- **Type / Priority**: P / H
- **Description**: Convert `PIC 9(5)` to a SQL `INTEGER` or `NUMERIC(5)` column.
- **Input (COBOL)**:
  ```cobol
  01 EMP-ID    PIC 9(5).
  ```
- **Expected DML**: Column definition `EMP_ID NUMERIC(5)` (or `INT`).
- **Pass Criteria**: Correct precision; no loss of digits.

### TC-002 — Alphanumeric PIC X to VARCHAR
- **Type / Priority**: P / H
- **Input**: `01 EMP-NAME PIC X(30).`
- **Expected DML**: `EMP_NAME VARCHAR(30)` (or `CHAR(30)` if fixed-length is required).
- **Pass Criteria**: Length preserved; trailing spaces handled per config.

### TC-003 — Signed numeric PIC S9(7)V99 to DECIMAL
- **Type / Priority**: P / H
- **Input**: `01 SALARY PIC S9(7)V99 COMP-3.`
- **Expected DML**: `SALARY DECIMAL(9,2)`.
- **Pass Criteria**: Sign retained; implied decimal correctly placed.

### TC-004 — COMP / COMP-3 / COMP-5 binary fields
- **Type / Priority**: P / H
- **Description**: Verify packed-decimal (`COMP-3`) and binary (`COMP`) fields convert to appropriate numeric types without precision loss.
- **Pass Criteria**: Generated `INSERT` values match unpacked COBOL values.

### TC-005 — Date field stored as PIC 9(8)
- **Type / Priority**: E / M
- **Input**: `01 HIRE-DATE PIC 9(8).` (YYYYMMDD)
- **Expected DML**: `HIRE_DATE DATE` with conversion `TO_DATE(:val, 'YYYYMMDD')` in `INSERT`.
- **Pass Criteria**: Date formatting correct; invalid dates flagged.

### TC-006 — Group item (record structure) to table
- **Type / Priority**: P / H
- **Input**:
  ```cobol
  01 CUSTOMER-REC.
     05 CUST-ID    PIC 9(6).
     05 CUST-NAME  PIC X(40).
     05 CUST-BAL   PIC S9(9)V99 COMP-3.
  ```
- **Expected DML**: `CREATE TABLE CUSTOMER (CUST_ID NUMERIC(6) PRIMARY KEY, CUST_NAME VARCHAR(40), CUST_BAL DECIMAL(11,2));` plus parameterized `INSERT`.

### TC-007 — REDEFINES clause
- **Type / Priority**: E / M
- **Description**: Two fields sharing storage. Verify only one logical column is generated and a comment/warning is produced.
- **Pass Criteria**: No duplicate columns; documentation note included.

### TC-008 — OCCURS clause (array) normalization
- **Type / Priority**: P / H
- **Input**: `05 MONTHLY-SALES OCCURS 12 TIMES PIC 9(7)V99.`
- **Expected DML**: A child table `MONTHLY_SALES (PARENT_ID, MONTH_NO, AMOUNT)` with FK and 12 rows per parent.
- **Pass Criteria**: 1:N relationship correctly modeled.

### TC-009 — OCCURS DEPENDING ON (variable array)
- **Type / Priority**: E / M
- **Pass Criteria**: Only actual occurrences inserted; counter column or row-count derived correctly.

---

## 2. File Operations → DML Statements

### TC-010 — Sequential READ → SELECT
- **Type / Priority**: P / H
- **Input**: `READ EMPLOYEE-FILE NEXT RECORD AT END MOVE 'Y' TO EOF-FLAG.`
- **Expected DML**: Cursor-based `SELECT * FROM EMPLOYEE ORDER BY <key>;` with fetch loop and EOF handling.

### TC-011 — Indexed READ by key → SELECT WHERE
- **Input**: `READ EMP-FILE KEY IS EMP-ID INVALID KEY ...`
- **Expected DML**: `SELECT * FROM EMPLOYEE WHERE EMP_ID = :emp_id;` with not-found handler.

### TC-012 — WRITE → INSERT
- **Input**: `WRITE EMP-REC.`
- **Expected DML**: `INSERT INTO EMPLOYEE (col1, col2, ...) VALUES (:c1, :c2, ...);`
- **Pass Criteria**: All record fields included; column order correct.

### TC-013 — REWRITE → UPDATE
- **Input**: `REWRITE EMP-REC.`
- **Expected DML**: `UPDATE EMPLOYEE SET col1=:c1, col2=:c2, ... WHERE <pk>=:pk;`

### TC-014 — DELETE → DELETE
- **Input**: `DELETE EMP-FILE.`
- **Expected DML**: `DELETE FROM EMPLOYEE WHERE <pk>=:pk;`

### TC-015 — START verb (positioning)
- **Type / Priority**: E / M
- **Input**: `START EMP-FILE KEY GREATER THAN EMP-ID.`
- **Expected DML**: Cursor `SELECT ... WHERE EMP_ID > :v ORDER BY EMP_ID;`

### TC-016 — OPEN/CLOSE handling
- **Type / Priority**: P / M
- **Pass Criteria**: `OPEN INPUT/OUTPUT/I-O/EXTEND` mapped to appropriate cursor declarations or transaction blocks; `CLOSE` releases cursor / commits.

---

## 3. Control Flow Conversion

### TC-017 — IF / ELSE → WHERE clause
- **Input**:
  ```cobol
  IF DEPT-CODE = 'HR'
     MOVE 'HUMAN RESOURCES' TO DEPT-NAME.
  ```
- **Expected DML**: Either inline `CASE WHEN DEPT_CODE='HR' THEN 'HUMAN RESOURCES' ...` or `UPDATE ... WHERE DEPT_CODE='HR';` depending on context.

### TC-018 — EVALUATE → CASE expression
- **Input**: `EVALUATE STATUS-CODE WHEN 'A' ... WHEN 'I' ...`
- **Expected DML**: `CASE STATUS_CODE WHEN 'A' THEN ... WHEN 'I' THEN ... END`.

### TC-019 — PERFORM VARYING loop with file write
- **Input**: `PERFORM VARYING I FROM 1 BY 1 UNTIL I > 100 ... WRITE REC ... END-PERFORM.`
- **Expected DML**: Bulk `INSERT ... SELECT` or batched `INSERT` statements; loop variable preserved.

### TC-020 — PERFORM UNTIL with READ loop
- **Pass Criteria**: Converts to cursor `FETCH` loop with proper EOF break.

### TC-021 — Nested IF with multiple AND/OR
- **Type / Priority**: E / M
- **Pass Criteria**: Boolean precedence preserved; parentheses added in SQL `WHERE`.

---

## 4. Aggregations and Derived Logic

### TC-022 — Running total (COMPUTE in loop) → SUM
- **Input**: COBOL accumulator inside a READ loop totaling `SALARY`.
- **Expected DML**: `SELECT SUM(SALARY) FROM EMPLOYEE;`
- **Pass Criteria**: Detects accumulator pattern; emits aggregate query.

### TC-023 — Counter (record count) → COUNT(*)
- **Pass Criteria**: COBOL `ADD 1 TO CNT` inside read loop converted to `SELECT COUNT(*) ...`.

### TC-024 — Control break (group totals) → GROUP BY
- **Type / Priority**: P / H
- **Input**: COBOL with break on `DEPT-ID` summing `SALARY`.
- **Expected DML**: `SELECT DEPT_ID, SUM(SALARY) FROM EMPLOYEE GROUP BY DEPT_ID ORDER BY DEPT_ID;`

### TC-025 — Matching/merge of two files → JOIN
- **Type / Priority**: P / H
- **Description**: Two sequential reads on a common key.
- **Expected DML**: `SELECT ... FROM A INNER JOIN B ON A.KEY = B.KEY;` (or LEFT JOIN if unmatched-master logic exists).

---

## 5. Negative & Error-Handling Tests

### TC-026 — Invalid PIC clause
- **Type**: N
- **Input**: `01 BAD-FIELD PIC Q(5).`
- **Expected**: Parser error with line number; no DML emitted for that field.

### TC-027 — Unsupported COBOL verb
- **Type**: N
- **Input**: A `STRING` / `UNSTRING` / `INSPECT` statement.
- **Expected**: Warning logged; statement preserved as comment in output; conversion continues.

### TC-028 — Duplicate field names within record
- **Type**: N
- **Pass Criteria**: Tool detects ambiguity and either fails fast or auto-renames with documented suffix.

### TC-029 — Missing FILE-CONTROL / SELECT
- **Type**: N
- **Pass Criteria**: Clear error: cannot map file to table without SELECT clause.

### TC-030 — Circular REDEFINES
- **Type**: N
- **Pass Criteria**: Detected and reported; conversion aborts gracefully.

### TC-031 — INVALID KEY without handler
- **Type**: E
- **Pass Criteria**: Tool generates a default exception block in target DML and logs warning.

---

## 6. Edge Cases

### TC-032 — Empty COBOL program
- **Type**: E
- **Pass Criteria**: Tool exits cleanly with "no convertible statements found" message.

### TC-033 — Comments and copybooks (COPY statement)
- **Type**: E / H
- **Pass Criteria**: `COPY` resolved against copybook library; nested copies expanded; comments preserved as SQL comments.

### TC-034 — Reserved SQL words as field names
- **Input**: `01 ORDER PIC X(10).` (ORDER is a SQL keyword)
- **Expected DML**: Quoted/escaped identifier `"ORDER"` or auto-rename per config.

### TC-035 — Field name with hyphens
- **Input**: `01 FIRST-NAME PIC X(20).`
- **Expected DML**: `FIRST_NAME VARCHAR(20)` (hyphen → underscore).

### TC-036 — Very long field/record names (>30 chars)
- **Pass Criteria**: Truncation per target DB limit, with mapping table written to log.

### TC-037 — Special characters in data (quotes, NULLs)
- **Type**: E
- **Pass Criteria**: Single quotes escaped; binary low-values handled or rejected with clear message.

### TC-038 — VSAM alternate index
- **Type**: E / M
- **Pass Criteria**: Alternate keys converted to secondary indexes (`CREATE INDEX ...`).

### TC-039 — Variable-length records (RECORD VARYING)
- **Pass Criteria**: Mapped to VARCHAR with declared max; length field handled.

### TC-040 — Files with FILLER fields
- **Pass Criteria**: FILLERs ignored or named `FILLER_n` based on config; no orphan columns.

---

## 7. Performance & Volume

### TC-041 — Large copybook (>500 fields)
- **Type**: Pf / M
- **Pass Criteria**: Conversion completes within agreed SLA; memory stable.

### TC-042 — Bulk record load (1M+ INSERTs)
- **Type**: Pf / H
- **Pass Criteria**: Tool emits batched/`INSERT ... VALUES (...),(...)` or `COPY`/`BULK INSERT` style output rather than 1M individual statements.

### TC-043 — Multiple programs in single batch
- **Pass Criteria**: Output organized per program; no cross-contamination of generated tables.

---

## 8. Output Quality / Non-Functional

### TC-044 — Generated DML is syntactically valid
- **Pass Criteria**: Output passes `EXPLAIN` / parse check on target DB (Oracle / DB2 / PostgreSQL / SQL Server depending on config).

### TC-045 — Idempotency
- **Pass Criteria**: Re-running converter on same input produces byte-identical DML.

### TC-046 — Round-trip fidelity (sample)
- **Pass Criteria**: Sample data inserted via generated DML matches values from a COBOL run on the same input file.

### TC-047 — Logging and traceability
- **Pass Criteria**: Each generated statement has a comment linking back to source file and line number.

### TC-048 — Target dialect switch
- **Pass Criteria**: Same COBOL input produces correct dialect-specific DML for at least two target databases.

---

## 9. Security / Compliance

### TC-049 — SQL injection safety in generated code
- **Pass Criteria**: All generated `INSERT/UPDATE/DELETE` use bind variables, never literal string concatenation.

### TC-050 — PII field handling
- **Pass Criteria**: Fields tagged as PII (via config) generate masked/encrypted column definitions or warnings.

---

## Test Execution Notes

1. Maintain a sample COBOL corpus covering sequential, indexed, and relative files, plus copybook variants.
2. For each test, store: source COBOL, expected DML, actual DML, diff, and pass/fail.
3. Regression suite should re-run TC-001 through TC-050 on every build.
4. Track conversion accuracy as: `(passed test cases / total test cases) × 100`.
