"""Tests for XML / COBOL / Hive → DML converters.

Each converter must:
  1. Produce DML text matching the style in real-dml.md.
  2. Generate DML that round-trips through `parse_dml_string` without errors.
  3. Preserve the structural intent of the source (field names, types,
     nullability, arrays, nested records).
"""
import pytest

from backend.parser.cobol_to_dml import cobol_copybook_to_dml
from backend.parser.dml_parser import parse_dml_string
from backend.parser.hive_to_dml import hive_ddl_to_dml
from backend.parser.xml_to_dml import xml_to_dml


def _reparse(dml: str) -> dict:
    """Helper: parse generated DML back through the DML parser."""
    schemas = parse_dml_string(dml)
    assert schemas, "Generated DML did not produce any schemas"
    return next(iter(schemas.values()))


# ════════════════════════════════════════════════════════════════════════════
# Hive → DML
# ════════════════════════════════════════════════════════════════════════════


def test_hive_basic_columns_round_trip():
    ddl = """
    CREATE TABLE customers (
      id BIGINT,
      name STRING,
      age INT
    );
    """
    out = hive_ddl_to_dml(ddl)
    assert out["table_name"] == "customers"
    assert "integer(8) id" in out["dml"]
    assert "string name" in out["dml"]
    assert "integer(4) age" in out["dml"]
    assert out["dml"].startswith("/* Generated from Hive Table: customers */")
    assert "\nrecord\n" in out["dml"]
    assert out["dml"].rstrip().endswith("end")
    schema = _reparse(out["dml"])
    assert [f["name"] for f in schema["fields"]] == ["id", "name", "age"]


def test_hive_decimal_precision_scale():
    out = hive_ddl_to_dml("CREATE TABLE t (amount DECIMAL(10,2));")
    assert "decimal(10,2) amount" in out["dml"]
    schema = _reparse(out["dml"])
    assert schema["fields"][0]["args"] == [10, 2]


def test_hive_array_renders_as_int_marker():
    """ARRAY<T> wraps in a single-field record:
        record { T[int] item; } colname;
    """
    out = hive_ddl_to_dml("CREATE TABLE t (tags ARRAY<STRING>);")
    assert "[int]" in out["dml"]
    assert "} tags" in out["dml"]
    schema = _reparse(out["dml"])
    tags = schema["fields"][0]
    assert tags["type"] == "struct"
    assert tags["array"] is False  # outer wrapper is not the array
    item = tags["fields"][0]
    assert item["name"] == "item"
    assert item["array"] is True


def test_hive_map_renders_as_struct_with_int_marker():
    """MAP<K,V> wraps in a double-record idiom:
        record { record { K key; V value; }[int] map_entries; } colname;
    """
    out = hive_ddl_to_dml("CREATE TABLE t (meta MAP<STRING,STRING>);")
    assert "} [int] map_entries" in out["dml"]
    assert "} meta" in out["dml"]
    schema = _reparse(out["dml"])
    meta = schema["fields"][0]
    assert meta["type"] == "struct"
    assert meta["array"] is False  # outer wrapper is not the array
    map_entries = meta["fields"][0]
    assert map_entries["name"] == "map_entries"
    assert map_entries["type"] == "struct"
    assert map_entries["array"] is True


def test_hive_struct_renders_as_nested_record():
    out = hive_ddl_to_dml("CREATE TABLE t (addr STRUCT<street:STRING, city:STRING>);")
    assert "record" in out["dml"] and "} addr" in out["dml"]
    schema = _reparse(out["dml"])
    addr = schema["fields"][0]
    assert addr["type"] == "struct"
    assert [f["name"] for f in addr["fields"]] == ["street", "city"]


def test_hive_row_format_delimited_applied_to_strings_only():
    """Hive's field terminator goes on string fields; numeric fields stay
    bare. Matches real-dml.md Example 4 style."""
    ddl = """
    CREATE TABLE t (
      id BIGINT,
      name STRING,
      amount DECIMAL(10,2)
    )
    ROW FORMAT DELIMITED FIELDS TERMINATED BY ',';
    """
    out = hive_ddl_to_dml(ddl)
    # name is delimited; id and amount are not.
    assert 'string(",") name' in out["dml"]
    assert "integer(8) id" in out["dml"]
    assert "decimal(10,2) amount" in out["dml"]


def test_hive_partition_columns_appended():
    ddl = """
    CREATE TABLE sales (id BIGINT, amount DECIMAL(8,2))
    PARTITIONED BY (year INT, month INT);
    """
    out = hive_ddl_to_dml(ddl)
    schema = _reparse(out["dml"])
    names = [f["name"] for f in schema["fields"]]
    assert names == ["id", "amount", "year", "month"]


def test_hive_octal_delimiter_preserved():
    """Hive's `\\001` (SOH) is the canonical default field separator."""
    ddl = "CREATE TABLE t (a STRING) ROW FORMAT DELIMITED FIELDS TERMINATED BY '\\001';"
    out = hive_ddl_to_dml(ddl)
    # Should be rendered as `string("\001")` octal-escaped.
    assert '"\\001"' in out["dml"] or "\x01" in out["dml"]
    schema = _reparse(out["dml"])
    assert schema["fields"][0].get("delimiter") == "\x01"


def test_hive_stored_as_returned_in_extras():
    out = hive_ddl_to_dml("CREATE TABLE t (a INT) STORED AS PARQUET;")
    assert out["stored_as"] == "parquet"


def test_hive_uniontype_rejected():
    with pytest.raises(ValueError, match="UNIONTYPE"):
        hive_ddl_to_dml("CREATE TABLE t (x UNIONTYPE<INT,STRING>);")


def test_hive_real_world_sales_data():
    """Acceptance gate: Hive DDL from real-dml.md → equivalent DML."""
    ddl = """
    CREATE TABLE sales_data (
        transaction_id  BIGINT,
        customer_name   STRING,
        amount          DECIMAL(10,2),
        items_list      ARRAY<STRING>,
        meta_info       MAP<STRING, STRING>
    )
    PARTITIONED BY (year INT, month INT)
    ROW FORMAT DELIMITED
    FIELDS TERMINATED BY '\\001';
    """
    out = hive_ddl_to_dml(ddl)
    schema = _reparse(out["dml"])
    names = [f["name"] for f in schema["fields"]]
    assert names == ["transaction_id", "customer_name", "amount",
                     "items_list", "meta_info", "year", "month"]
    by_name = {f["name"]: f for f in schema["fields"]}
    # ARRAY<STRING> wraps in a record { item } — outer struct, inner array.
    assert by_name["items_list"]["type"] == "struct"
    assert by_name["items_list"]["fields"][0]["name"] == "item"
    assert by_name["items_list"]["fields"][0]["array"] is True
    # MAP<K,V> double-wraps — outer struct, inner map_entries struct with array.
    assert by_name["meta_info"]["type"] == "struct"
    map_entries = by_name["meta_info"]["fields"][0]
    assert map_entries["name"] == "map_entries"
    assert map_entries["array"] is True


def test_hive_parquet_drops_delimiters_on_strings():
    """STORED AS PARQUET is a binary format — `FIELDS TERMINATED BY` is a
    Hive-serde detail with no DML meaning, so string fields render bare.
    """
    ddl = """
    CREATE TABLE t (
      id BIGINT,
      name STRING
    )
    ROW FORMAT DELIMITED FIELDS TERMINATED BY '\\001'
    STORED AS PARQUET;
    """
    out = hive_ddl_to_dml(ddl)
    assert out["stored_as"] == "parquet"
    # Bare `string`, no `("\001")` arg.
    assert "string name" in out["dml"]
    assert '"\\001"' not in out["dml"]
    schema = _reparse(out["dml"])
    name_field = next(f for f in schema["fields"] if f["name"] == "name")
    assert name_field.get("delimiter") is None


def test_hive_textfile_keeps_delimiters():
    """STORED AS TEXTFILE keeps the per-string delimiter — text format
    needs it for record splitting."""
    ddl = """
    CREATE TABLE t (
      id BIGINT,
      name STRING
    )
    ROW FORMAT DELIMITED FIELDS TERMINATED BY '\\001'
    STORED AS TEXTFILE;
    """
    out = hive_ddl_to_dml(ddl)
    assert out["stored_as"] == "textfile"
    assert 'string("\\001") name' in out["dml"]


def test_hive_output_has_header_and_banners():
    """The sales_data fixture should emit the readability banners shown in
    real-dml.md Example 4: a header line, section banners for primitives /
    ARRAY / MAP / partition columns, and column-aligned trailing /* TYPE */
    comments."""
    ddl = """
    CREATE TABLE sales_data (
        transaction_id  BIGINT,
        customer_name   STRING,
        amount          DECIMAL(10,2),
        items_list      ARRAY<STRING>,
        meta_info       MAP<STRING, STRING>
    )
    PARTITIONED BY (year INT, month INT)
    ROW FORMAT DELIMITED
    FIELDS TERMINATED BY '\\001';
    """
    dml = hive_ddl_to_dml(ddl)["dml"]
    assert "/* Generated from Hive Table: sales_data */" in dml
    assert "/* Basic Hive Types */" in dml
    assert "/* Hive ARRAY becomes a DML Vector */" in dml
    assert "/* Hive MAP becomes a Vector of Key-Value pairs */" in dml
    assert "/* Partition columns */" in dml

    # Column-aligned trailing comments: the BIGINT and DECIMAL(10,2) lines
    # in the first run should put their `/*` at the same column.
    def _comment_col(needle: str) -> int:
        line = next(L for L in dml.splitlines() if needle in L and "/*" in L)
        return line.index("/*")
    assert _comment_col("transaction_id") == _comment_col("amount")

    # The two partition-column lines form their own run; they should also
    # align (and at a different column, since they're a separate block).
    assert _comment_col("year") == _comment_col("month")


def test_hive_long_alias():
    """LONG is a legacy alias for BIGINT — should map to integer(8)."""
    out = hive_ddl_to_dml(
        "CREATE TABLE t (record_id LONG, amount BIGINT) "
        "ROW FORMAT DELIMITED FIELDS TERMINATED BY '\\001';"
    )
    assert "integer(8) record_id" in out["dml"]
    assert "integer(8) amount" in out["dml"]


def test_hive_trailing_comma_tolerated():
    out = hive_ddl_to_dml("""
        CREATE TABLE trailing_comma (
            id     BIGINT,
            name   STRING,
            amount DECIMAL(10,2),
        )
        ROW FORMAT DELIMITED FIELDS TERMINATED BY '\\001';
    """)
    schema = _reparse(out["dml"])
    assert [f["name"] for f in schema["fields"]] == ["id", "name", "amount"]


def test_hive_stored_by_serde_clause():
    """STORED BY 'class' [WITH SERDEPROPERTIES (...)] doesn't change schema
    columns — just walks past the clause."""
    out = hive_ddl_to_dml("""
        CREATE TABLE hbase_table (
            row_key STRING,
            col1    STRING,
            col2    BIGINT
        )
        STORED BY 'org.apache.hadoop.hive.hbase.HBaseStorageHandler'
        WITH SERDEPROPERTIES ('hbase.columns.mapping' = ':key,cf1:col1,cf1:col2');
    """)
    schema = _reparse(out["dml"])
    assert [f["name"] for f in schema["fields"]] == ["row_key", "col1", "col2"]
    assert out["stored_as"] == "by_serde"


def test_hive_timestamp_with_local_time_zone():
    """Hive 3.x TIMESTAMP WITH LOCAL TIME ZONE → plain timestamp; the
    timezone metadata is discarded."""
    out = hive_ddl_to_dml("""
        CREATE TABLE tz_aware (
            event_ts TIMESTAMP WITH LOCAL TIME ZONE,
            created  TIMESTAMP
        )
        ROW FORMAT DELIMITED FIELDS TERMINATED BY '\\001';
    """)
    schema = _reparse(out["dml"])
    by_name = {f["name"]: f for f in schema["fields"]}
    # Both timestamps round-trip as plain `timestamp` (datetime in DML's
    # internal alias map). The timezone-discard note should appear in the
    # generated DML as a comment for the tz-aware column.
    assert by_name["event_ts"]["type"] in ("datetime", "timestamp")
    assert by_name["created"]["type"] in ("datetime", "timestamp")
    assert "TIMESTAMP WITH LOCAL TIME ZONE" in out["dml"]


def test_hive_empty_struct_clear_error():
    with pytest.raises(ValueError, match="Empty STRUCT"):
        hive_ddl_to_dml(
            "CREATE TABLE t (x STRUCT<>) ROW FORMAT DELIMITED "
            "FIELDS TERMINATED BY '\\001';"
        )


def test_hive_alter_table_clear_error():
    with pytest.raises(ValueError, match="ALTER TABLE is not supported"):
        hive_ddl_to_dml("ALTER TABLE sales_data ADD COLUMNS (new_col STRING);")


def test_hive_create_view_clear_error():
    with pytest.raises(ValueError, match="CREATE VIEW is not supported"):
        hive_ddl_to_dml(
            "CREATE VIEW v AS SELECT year, SUM(amount) FROM t GROUP BY year;"
        )


def test_hive_non_ddl_clear_error():
    with pytest.raises(ValueError, match="not appear to be valid Hive DDL"):
        hive_ddl_to_dml("Hello, this is not SQL at all!")


def test_hive_exact_duplicate_columns_rejected():
    """Two columns with identical names is invalid Hive — must reject."""
    with pytest.raises(ValueError, match="Duplicate column name: 'id'"):
        hive_ddl_to_dml(
            "CREATE TABLE t (id STRING, id INT) "
            "ROW FORMAT DELIMITED FIELDS TERMINATED BY '\\001';"
        )


def test_hive_case_insensitive_duplicate_columns_rejected():
    """Hive normalises identifiers to lowercase: Name == name == NAME."""
    with pytest.raises(ValueError, match="case normalization"):
        hive_ddl_to_dml(
            "CREATE TABLE t (Name STRING, name INT, NAME DOUBLE) "
            "ROW FORMAT DELIMITED FIELDS TERMINATED BY '\\001';"
        )


def test_hive_special_char_columns_sanitized_and_mapped():
    """Hive backticks let columns contain ``-``, ``@``, ``#``, ``$`` etc.
    DML can't accept these — the converter should rewrite each to ``_``
    (or a leading ``_`` for things that strip the first char) and surface
    the original→DML mapping so callers can preserve lineage."""
    out = hive_ddl_to_dml("""
        CREATE TABLE special_chars (
            `user-id`     STRING,
            `@timestamp`  BIGINT,
            `#value`      DOUBLE,
            `$amount`     DECIMAL(10,2)
        )
        ROW FORMAT DELIMITED FIELDS TERMINATED BY '\\001';
    """)
    # Sanitized names appear in the DML.
    assert "user_id" in out["dml"]
    assert "_timestamp" in out["dml"]
    assert "_value" in out["dml"]
    assert "_amount" in out["dml"]
    # Lineage map preserves the original Hive names.
    assert out["column_renames"] == {
        "user-id":    "user_id",
        "@timestamp": "_timestamp",
        "#value":     "_value",
        "$amount":    "_amount",
    }
    # Re-parses cleanly.
    schema = _reparse(out["dml"])
    names = [f["name"] for f in schema["fields"]]
    assert names == ["user_id", "_timestamp", "_value", "_amount"]


def test_hive_no_renames_omitted_from_response():
    """When every column is already a valid identifier, no rename map is
    surfaced — keeps the response lean for the common case."""
    out = hive_ddl_to_dml(
        "CREATE TABLE plain (id BIGINT, name STRING) "
        "ROW FORMAT DELIMITED FIELDS TERMINATED BY '\\001';"
    )
    assert "column_renames" not in out


def test_hive_special_char_collision_caught_by_dup_detector():
    """``user-id`` and ``user_id`` both sanitize to ``user_id`` — the
    case-insensitive duplicate detector catches the collision."""
    with pytest.raises(ValueError, match="Duplicate column"):
        hive_ddl_to_dml(
            "CREATE TABLE collision (`user-id` STRING, user_id INT) "
            "ROW FORMAT DELIMITED FIELDS TERMINATED BY '\\001';"
        )


def test_hive_ctas_clear_error():
    """CTAS schema is derived by running the SELECT — we can't infer types
    without a live metastore. Reject with a clear error pointing at the
    DESCRIBE EXTENDED workaround."""
    ctas = """
    CREATE TABLE ctas_complex
    STORED AS PARQUET
    AS
    SELECT
        id,
        explode(map('a', 1, 'b', 2)) AS (k, v),
        named_struct(
            'nested',
            array(named_struct('x', 1, 'y', 2))
        ) AS complex_col
    FROM source_table;
    """
    with pytest.raises(ValueError, match="CTAS .* is not supported"):
        hive_ddl_to_dml(ctas)


def test_hive_simple_ctas_clear_error():
    """The plain CREATE TABLE name AS SELECT form (no STORED AS) also
    triggers the CTAS error — the SELECT is the discriminator."""
    with pytest.raises(ValueError, match="CTAS .* is not supported"):
        hive_ddl_to_dml(
            "CREATE TABLE copy_of_users AS SELECT * FROM users;"
        )


def test_hive_create_table_like_clear_error():
    """CREATE TABLE LIKE copies a schema from another table — also
    requires metastore access we don't have."""
    with pytest.raises(ValueError, match="CREATE TABLE LIKE is not supported"):
        hive_ddl_to_dml("CREATE TABLE shadow LIKE source;")


def test_hive_partition_column_collides_with_data_column():
    """A partition column with the same name as a regular column is a
    Hive error and our converter should refuse to emit DML for it."""
    with pytest.raises(ValueError, match="Duplicate column name"):
        hive_ddl_to_dml(
            "CREATE TABLE t (year INT, amount DECIMAL(10,2)) "
            "PARTITIONED BY (year INT) "
            "ROW FORMAT DELIMITED FIELDS TERMINATED BY '\\001';"
        )


# ════════════════════════════════════════════════════════════════════════════
# COBOL → DML
# ════════════════════════════════════════════════════════════════════════════


def test_cobol_basic_copybook():
    src = """
    01  CUSTOMER-RECORD.
        05  CUSTOMER-ID    PIC 9(05).
        05  CUSTOMER-NAME  PIC X(20).
    """
    out = cobol_copybook_to_dml(src)
    assert out["record_name"] == "customer_record"
    assert "decimal(5,0) customer_id" in out["dml"]
    assert "string(20) customer_name" in out["dml"]
    schema = _reparse(out["dml"])
    assert [f["name"] for f in schema["fields"]] == ["customer_id", "customer_name"]


def test_cobol_packed_decimal_rendered_with_packed_prefix():
    src = "01 R. 05 BAL PIC S9(7)V99 COMP-3."
    out = cobol_copybook_to_dml(src)
    assert "packed decimal(9,2)" in out["dml"]
    schema = _reparse(out["dml"])
    f = schema["fields"][0]
    assert f["encoding"] == "packed"
    assert f["args"] == [9, 2]


def test_cobol_nested_levels_render_as_nested_record():
    src = """
    01  EMPLOYEE.
        05  EMP-ID         PIC 9(05).
        05  EMP-DETAILS.
            10  EMP-DEPT   PIC X(10).
            10  EMP-SALARY PIC S9(7)V99 COMP-3.
    """
    out = cobol_copybook_to_dml(src)
    schema = _reparse(out["dml"])
    by_name = {f["name"]: f for f in schema["fields"]}
    assert by_name["emp_details"]["type"] == "struct"
    inner = {f["name"]: f for f in by_name["emp_details"]["fields"]}
    assert inner["emp_salary"]["encoding"] == "packed"


def test_cobol_occurs_fixed_renders_array_on_primitive():
    """For primitive fields, DML puts brackets between type-args and name:
    `string(10)[5] items;` — matches real-dml.md Example 1's form."""
    src = """
    01  R.
        05  ITEMS  OCCURS 5 TIMES PIC X(10).
    """
    out = cobol_copybook_to_dml(src)
    assert "[5] items" in out["dml"]
    schema = _reparse(out["dml"])
    items = schema["fields"][0]
    assert items["array_length"] == 5


def test_cobol_occurs_depending_on_renders_after_name():
    """Matches real-dml.md Example 3 style: `} projects[project_count];`."""
    src = """
    01  R.
        05  CTR PIC 9(2).
        05  ITEMS OCCURS 1 TO 5 TIMES DEPENDING ON CTR.
            10  ID PIC X(4).
    """
    out = cobol_copybook_to_dml(src)
    assert "} items[ctr];" in out["dml"]
    schema = _reparse(out["dml"])
    items = next(f for f in schema["fields"] if f["name"] == "items")
    assert items["depends_on"] == "ctr"


def test_cobol_redefines_rejected():
    src = """
    01 R. 05 A PIC X(10). 05 B REDEFINES A PIC 9(10).
    """
    with pytest.raises(ValueError, match="REDEFINES"):
        cobol_copybook_to_dml(src)


def test_cobol_real_world_employee():
    """Acceptance gate: Example 3 from real-dml.md."""
    src = """
    01  EMPLOYEE-RECORD.
        05  EMP-ID              PIC 9(05).
        05  EMP-NAME            PIC X(20).
        05  EMP-DETAILS.
            10  EMP-DEPT        PIC X(10).
            10  EMP-SALARY      PIC S9(7)V99  COMP-3.
        05  PROJECT-COUNT       PIC 9(02).
        05  PROJECTS            OCCURS 1 TO 5 TIMES
                                DEPENDING ON PROJECT-COUNT.
            10  PROJ-ID         PIC X(04).
    """
    out = cobol_copybook_to_dml(src)
    schema = _reparse(out["dml"])
    names = [f["name"] for f in schema["fields"]]
    assert names == ["emp_id", "emp_name", "emp_details",
                     "project_count", "projects"]
    by_name = {f["name"]: f for f in schema["fields"]}
    assert by_name["projects"]["depends_on"] == "project_count"


# ════════════════════════════════════════════════════════════════════════════
# XML / XSD → DML
# ════════════════════════════════════════════════════════════════════════════


def test_xml_sample_simple():
    xml = "<Order><Id>101</Id><Customer>John</Customer></Order>"
    out = xml_to_dml(xml, mode="sample")
    assert out["record_name"] == "Order"
    assert out["mode"] == "sample"
    assert "utf8 record" in out["dml"]
    schema = _reparse(out["dml"])
    names = [f["name"] for f in schema["fields"]]
    assert "Id" in names and "Customer" in names


def test_xml_sample_attribute_becomes_field():
    xml = '<Order id="101"><Customer>John</Customer></Order>'
    out = xml_to_dml(xml, mode="sample")
    schema = _reparse(out["dml"])
    by_name = {f["name"]: f for f in schema["fields"]}
    # Attribute should be present as a field at the top level.
    assert "id" in by_name


def test_xml_sample_repeated_element_array():
    xml = "<Items><Product>A</Product><Product>B</Product></Items>"
    out = xml_to_dml(xml, mode="sample")
    assert "[int]" in out["dml"]
    schema = _reparse(out["dml"])
    assert schema["fields"][0]["array"] is True


def test_xml_sample_real_world_order():
    """Acceptance gate: Example 1 from real-dml.md."""
    xml = """
    <Order id="101">
      <Customer>John Doe</Customer>
      <Items>
        <Product>Laptop</Product>
        <Product>Mouse</Product>
      </Items>
    </Order>
    """
    out = xml_to_dml(xml, mode="sample")
    assert "utf8 record" in out["dml"]
    assert "/* Mapping for the 'id' attribute */" in out["dml"]
    assert "/* Mapping for the 'Customer' element */" in out["dml"]
    schema = _reparse(out["dml"])
    items = next(f for f in schema["fields"] if f["name"] == "Items")
    assert items["type"] == "struct"
    product = items["fields"][0]
    assert product["array"] is True


def test_xsd_simple_element():
    xsd = """<?xml version="1.0"?>
    <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:element name="Customer" type="xs:string"/>
    </xs:schema>
    """
    out = xml_to_dml(xsd, mode="xsd")
    assert out["record_name"] == "Customer"
    assert out["mode"] == "xsd"
    schema = _reparse(out["dml"])
    f = schema["fields"][0]
    assert f["type"] == "string"


def test_xsd_max_occurs_unbounded_array():
    xsd = """<?xml version="1.0"?>
    <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:element name="Items">
        <xs:complexType>
          <xs:sequence>
            <xs:element name="Product" type="xs:string" maxOccurs="unbounded"/>
          </xs:sequence>
        </xs:complexType>
      </xs:element>
    </xs:schema>
    """
    out = xml_to_dml(xsd, mode="xsd")
    assert "[int]" in out["dml"]
    schema = _reparse(out["dml"])
    assert schema["fields"][0]["array"] is True


def test_xsd_decimal_with_facets():
    xsd = """<?xml version="1.0"?>
    <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:element name="Price">
        <xs:simpleType>
          <xs:restriction base="xs:decimal">
            <xs:totalDigits value="10"/>
            <xs:fractionDigits value="2"/>
          </xs:restriction>
        </xs:simpleType>
      </xs:element>
    </xs:schema>
    """
    out = xml_to_dml(xsd, mode="xsd")
    assert "decimal(10,2)" in out["dml"]
    schema = _reparse(out["dml"])
    assert schema["fields"][0]["args"] == [10, 2]


def test_xsd_attribute_with_required_use():
    xsd = """<?xml version="1.0"?>
    <xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
      <xs:element name="Order">
        <xs:complexType>
          <xs:attribute name="id" type="xs:string" use="required"/>
        </xs:complexType>
      </xs:element>
    </xs:schema>
    """
    out = xml_to_dml(xsd, mode="xsd")
    assert "NOT NULL" in out["dml"]
    schema = _reparse(out["dml"])
    f = schema["fields"][0]
    assert f["nullable"] is False


def test_xml_auto_detect_picks_xsd_when_root_is_schema():
    xsd = (
        '<?xml version="1.0"?>'
        '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
        '<xs:element name="X" type="xs:int"/>'
        '</xs:schema>'
    )
    out = xml_to_dml(xsd)  # mode="auto"
    assert out["mode"] == "xsd"


def test_xml_auto_detect_picks_sample_when_not_xsd():
    out = xml_to_dml("<Order><Id>1</Id></Order>")
    assert out["mode"] == "sample"


def test_xml_malformed_rejected():
    with pytest.raises(ValueError, match="Malformed"):
        xml_to_dml("<not<valid>>")


def test_xml_empty_rejected():
    with pytest.raises(ValueError, match="empty"):
        xml_to_dml("")


# ════════════════════════════════════════════════════════════════════════════
# End-to-end: source → DML → PySpark `StructType` (round-trip everything)
# ════════════════════════════════════════════════════════════════════════════


def test_hive_dml_round_trips_to_struct_type():
    try:
        from pyspark.sql.types import StructType, LongType, DecimalType
    except Exception:
        pytest.skip("PySpark not installed")
    from backend.parser.dml_parser import to_struct_type

    out = hive_ddl_to_dml(
        "CREATE TABLE t (id BIGINT, amount DECIMAL(10,2));"
    )
    schema = _reparse(out["dml"])
    st = to_struct_type(schema)
    assert isinstance(st, StructType)
    by_name = {f.name: f for f in st.fields}
    assert isinstance(by_name["id"].dataType, LongType)
    assert isinstance(by_name["amount"].dataType, DecimalType)


def test_cobol_dml_round_trips_to_struct_type():
    try:
        from pyspark.sql.types import StructType, StringType, DecimalType
    except Exception:
        pytest.skip("PySpark not installed")
    from backend.parser.dml_parser import to_struct_type

    out = cobol_copybook_to_dml(
        "01 R. 05 NAME PIC X(10). 05 AMOUNT PIC S9(5)V99 COMP-3."
    )
    schema = _reparse(out["dml"])
    st = to_struct_type(schema)
    assert isinstance(st, StructType)
    by_name = {f.name: f for f in st.fields}
    assert isinstance(by_name["name"].dataType, StringType)
    assert isinstance(by_name["amount"].dataType, DecimalType)


def test_xml_dml_round_trips_to_struct_type():
    try:
        from pyspark.sql.types import StructType
    except Exception:
        pytest.skip("PySpark not installed")
    from backend.parser.dml_parser import to_struct_type

    out = xml_to_dml("<Order><Id>1</Id><Customer>John</Customer></Order>", mode="sample")
    schema = _reparse(out["dml"])
    st = to_struct_type(schema)
    assert isinstance(st, StructType)
