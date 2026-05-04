"""Tests for the realistic-dialect .dml parser."""
import pytest

from backend.parser.dml_parser import parse_dml_string, resolve

SAMPLE = """\
-- A comment
DEFINE customer
BEGIN
    customer_id    integer        NOT NULL;
    name           string(50)     NULL;
    balance        decimal(10,2)  NOT NULL;
    signup         date           NULL;
END

DEFINE order_raw
BEGIN
    order_id       string(36)     NOT NULL;
    customer_id    integer        NOT NULL;
END
"""


def test_multiple_defines():
    s = parse_dml_string(SAMPLE)
    assert set(s.keys()) == {"customer", "order_raw"}


def test_field_order_name_then_type():
    s = parse_dml_string(SAMPLE)
    customer = s["customer"]
    names = [f["name"] for f in customer["fields"]]
    assert names == ["customer_id", "name", "balance", "signup"]
    types = [f["type"] for f in customer["fields"]]
    assert types == ["integer", "string", "decimal", "date"]


def test_not_null_two_token():
    s = parse_dml_string(SAMPLE)
    cust = s["customer"]
    by_name = {f["name"]: f for f in cust["fields"]}
    assert by_name["customer_id"]["nullable"] is False
    assert by_name["name"]["nullable"] is True


def test_decimal_precision_scale():
    s = parse_dml_string(SAMPLE)
    bal = next(f for f in s["customer"]["fields"] if f["name"] == "balance")
    assert bal["type"] == "decimal"
    assert bal["args"] == [10, 2]


def test_strips_dash_comments():
    src = """\
DEFINE x
BEGIN
    -- inline comment line
    a integer NOT NULL;  -- trailing comment
END
"""
    s = parse_dml_string(src)
    assert s["x"]["fields"][0]["name"] == "a"


def test_resolve_by_filename():
    s = parse_dml_string(SAMPLE)
    assert resolve(s, "customer.dml")["fields"][0]["name"] == "customer_id"
    assert resolve(s, "order_raw.dml")["fields"][0]["name"] == "order_id"


def test_legacy_record_form():
    """Legacy `record … end;` form should still parse for compatibility."""
    legacy = "record string(20) id; integer age; end;"
    s = parse_dml_string(legacy)
    rec = next(iter(s.values()))
    assert [f["name"] for f in rec["fields"]] == ["id", "age"]


def test_complex_example_parses():
    from pathlib import Path
    from backend.parser.dml_parser import parse_dml_file
    p = Path(__file__).resolve().parents[3] / "examples" / "complex_pipeline" / "customer_order_enrichment.dml"
    s = parse_dml_file(p)
    assert set(s.keys()) == {
        "customer_raw", "customer_normalized", "order_raw",
        "order_normalized", "enriched_order", "standard_summary",
    }


def test_to_struct_type_smoke():
    try:
        from backend.parser.dml_parser import to_struct_type
        from pyspark.sql.types import StructType
    except Exception:
        pytest.skip("PySpark not installed")
    st = to_struct_type(parse_dml_string(SAMPLE)["customer"])
    assert isinstance(st, StructType)
    assert [f.name for f in st.fields] == ["customer_id", "name", "balance", "signup"]


# ── nested records ────────────────────────────────────────────────────────


NESTED = """\
DEFINE customer
BEGIN
    id        decimal(10)   NOT NULL;
    address   record
                  street    string(50)  NULL;
                  city      string(30)  NULL;
                  zip       string(10)  NOT NULL;
              end           NOT NULL;
    name      string(40)    NULL;
END
"""


def test_nested_record_basic():
    s = parse_dml_string(NESTED)
    cust = s["customer"]
    by_name = {f["name"]: f for f in cust["fields"]}
    assert by_name["address"]["type"] == "struct"
    assert by_name["address"]["nullable"] is False
    assert by_name["address"]["array"] is False
    inner = {f["name"]: f for f in by_name["address"]["fields"]}
    assert set(inner) == {"street", "city", "zip"}
    assert inner["zip"]["nullable"] is False
    assert inner["street"]["type"] == "string"


def test_nested_record_with_trailing_name():
    """`end <name>;` after a nested record should be tolerated."""
    src = """\
DEFINE x BEGIN
    addr record
             street string(20) NULL;
         end addr NOT NULL;
END
"""
    s = parse_dml_string(src)
    addr = s["x"]["fields"][0]
    assert addr["name"] == "addr"
    assert addr["type"] == "struct"
    assert addr["nullable"] is False
    assert addr["fields"][0]["name"] == "street"


def test_nested_record_array_of_structs():
    src = """\
DEFINE customer BEGIN
    id        integer       NOT NULL;
    addresses record
                  street string(50) NULL;
                  city   string(30) NULL;
              end[]         NULL;
END
"""
    s = parse_dml_string(src)
    addrs = next(f for f in s["customer"]["fields"] if f["name"] == "addresses")
    assert addrs["type"] == "struct"
    assert addrs["array"] is True
    assert addrs["nullable"] is True
    assert {f["name"] for f in addrs["fields"]} == {"street", "city"}


def test_deeply_nested_records():
    src = """\
DEFINE acct BEGIN
    owner record
              name    string(40)  NULL;
              address record
                          street string(50) NULL;
                          city   string(30) NULL;
                      end             NOT NULL;
          end                         NOT NULL;
END
"""
    s = parse_dml_string(src)
    owner = s["acct"]["fields"][0]
    assert owner["type"] == "struct"
    assert owner["nullable"] is False
    inner = {f["name"]: f for f in owner["fields"]}
    assert inner["address"]["type"] == "struct"
    assert inner["address"]["nullable"] is False
    grand = {f["name"]: f for f in inner["address"]["fields"]}
    assert set(grand) == {"street", "city"}


def test_nested_record_to_struct_type():
    try:
        from backend.parser.dml_parser import to_struct_type
        from pyspark.sql.types import StructType, ArrayType, StringType
    except Exception:
        pytest.skip("PySpark not installed")
    src = """\
DEFINE customer BEGIN
    id        integer       NOT NULL;
    addr      record
                  street string(50) NULL;
                  city   string(30) NULL;
              end             NOT NULL;
    aliases   string(20)[]   NULL;
    histories record
                  ts     datetime   NULL;
                  amount decimal(10,2) NULL;
              end[]           NULL;
END
"""
    st = to_struct_type(parse_dml_string(src)["customer"])
    fields = {f.name: f for f in st.fields}

    assert isinstance(fields["addr"].dataType, StructType)
    addr_inner = {f.name for f in fields["addr"].dataType.fields}
    assert addr_inner == {"street", "city"}

    assert isinstance(fields["aliases"].dataType, ArrayType)
    assert isinstance(fields["aliases"].dataType.elementType, StringType)

    assert isinstance(fields["histories"].dataType, ArrayType)
    assert isinstance(fields["histories"].dataType.elementType, StructType)


# ── delimited / quoted-string type args ───────────────────────────────────


def test_user_case_record_string_newline_delimiter():
    """Original failing case: `record string("\\n") filename; end`."""
    src = 'record\nstring("\\n") filename;\nend'
    s = parse_dml_string(src)
    rec = next(iter(s.values()))
    f = rec["fields"][0]
    assert f["name"] == "filename"
    assert f["type"] == "string"
    assert f["delimiter"] == "\n"
    assert f["args"] == []


def test_user_case_unicode_delimiter_with_trailing_comma_and_default():
    """Second failing case: ¨-delimited fields, trailing comma in args, default value."""
    src = (
        'record\n'
        '    string("¨", ) msisdn;\n'
        '    string("¨", ) filename_base;\n'
        '    decimal("¨", ) file_external_id;\n'
        '    decimal("¨", ) record_no;\n'
        '    string(1) newline = "\\n";\n'
        'end'
    )
    s = parse_dml_string(src)
    rec = next(iter(s.values()))
    fields = {f["name"]: f for f in rec["fields"]}

    assert set(fields) == {"msisdn", "filename_base", "file_external_id", "record_no", "newline"}

    # The four ¨-delimited fields
    for name in ("msisdn", "filename_base", "file_external_id", "record_no"):
        assert fields[name]["delimiter"] == "¨", f"{name} delimiter wrong"
        assert fields[name]["args"] == []

    # Two have type=string, two have type=decimal
    assert fields["msisdn"]["type"] == "string"
    assert fields["file_external_id"]["type"] == "decimal"
    assert fields["record_no"]["type"] == "decimal"

    # The default-value field
    nl = fields["newline"]
    assert nl["type"] == "string"
    assert nl["args"] == [1]
    assert nl.get("delimiter") is None
    assert nl["default"] == "\n"


def test_delimiter_with_length_arg():
    """`string(50, "|")` should give length 50 and delimiter |."""
    src = 'DEFINE x BEGIN a string(50, "|") NULL; END'
    s = parse_dml_string(src)
    f = s["x"]["fields"][0]
    assert f["args"] == [50]
    assert f["delimiter"] == "|"


def test_delimiter_escape_sequences():
    src = (
        'DEFINE x BEGIN\n'
        '    tab   string("\\t") NULL;\n'
        '    bs    string("\\\\") NULL;\n'
        '    crlf  string("\\r\\n") NULL;\n'
        'END'
    )
    s = parse_dml_string(src)
    f = {x["name"]: x for x in s["x"]["fields"]}
    assert f["tab"]["delimiter"] == "\t"
    assert f["bs"]["delimiter"] == "\\"
    assert f["crlf"]["delimiter"] == "\r\n"


def test_default_value_numeric_and_ident():
    src = (
        'DEFINE x BEGIN\n'
        '    n integer NULL = 0;\n'
        '    s string(10) NULL = "hi";\n'
        '    flag boolean NULL = TRUE;\n'
        'END'
    )
    s = parse_dml_string(src)
    f = {x["name"]: x for x in s["x"]["fields"]}
    assert f["n"]["default"] == 0
    assert f["s"]["default"] == "hi"
    assert f["flag"]["default"] == "TRUE"


# ── playground integration: delimited → CSV with right option ─────────────


def test_playground_delimited_routes_to_csv():
    from backend.api.routes.dml_playground import convert, ConvertRequest
    src = (
        'DEFINE feed BEGIN\n'
        '    a string("|") NULL;\n'
        '    b string("|") NULL;\n'
        'END'
    )
    resp = convert(ConvertRequest(dml=src))
    s = resp.schemas[0]
    assert s.recommended_format.name == "csv"
    assert s.feature_flags["has_delimited_fields"] is True
    # The emitted PySpark must set the pipe delimiter, not the default comma.
    assert '.option("delimiter", "|")' in s.pyspark_code


def test_playground_user_unicode_case_emits_uniform_delimiter():
    from backend.api.routes.dml_playground import convert, ConvertRequest
    src = (
        'DEFINE feed BEGIN\n'
        '    msisdn        string("¨", ) NULL;\n'
        '    filename_base string("¨", ) NULL;\n'
        '    record_no     decimal("¨", ) NULL;\n'
        'END'
    )
    resp = convert(ConvertRequest(dml=src))
    s = resp.schemas[0]
    assert s.recommended_format.name == "csv"
    assert '.option("delimiter", "\\u00a8")' in s.pyspark_code or \
           '.option("delimiter", "¨")' in s.pyspark_code


# ── legacy nested-record + arrays + combined nesting ─────────────────────


def test_user_case_legacy_inner_nested_record():
    """The exact failing case: legacy `record … end <name>;` *inline* as a field."""
    src = (
        'record\n'
        '  decimal("\\t") cust_id;\n'
        '  string("\\t") cust_name;\n'
        '  // Nested Record\n'
        '  record\n'
        '    string("\\t") street;\n'
        '    string("\\t") city;\n'
        '    string("\\n") zip;\n'
        '  end address;\n'
        'end;\n'
    )
    s = parse_dml_string(src)
    rec = next(iter(s.values()))
    fields = {f["name"]: f for f in rec["fields"]}
    assert set(fields) == {"cust_id", "cust_name", "address"}
    assert fields["address"]["type"] == "struct"
    inner = {f["name"]: f for f in fields["address"]["fields"]}
    assert set(inner) == {"street", "city", "zip"}
    assert inner["street"]["delimiter"] == "\t"
    assert inner["zip"]["delimiter"] == "\n"


def test_legacy_nested_record_with_modifiers():
    """`record … end <name> NOT NULL;` should parse and apply NOT NULL to the field."""
    src = (
        'record\n'
        '  outer_id integer NULL;\n'
        '  record\n'
        '    inner_id integer NULL;\n'
        '  end inner_block NOT NULL;\n'
        'end;\n'
    )
    s = parse_dml_string(src)
    rec = next(iter(s.values()))
    f = {x["name"]: x for x in rec["fields"]}
    assert f["inner_block"]["type"] == "struct"
    assert f["inner_block"]["nullable"] is False


def test_legacy_nested_record_anonymous_synthesized():
    """`record … end NOT NULL;` (no name) gets a synthesized field name."""
    src = (
        'record\n'
        '  outer_id integer NULL;\n'
        '  record\n'
        '    inner_id integer NULL;\n'
        '  end NOT NULL;\n'
        'end;\n'
    )
    s = parse_dml_string(src)
    rec = next(iter(s.values()))
    anon = next(f for f in rec["fields"] if f["name"].startswith("_anon_record_"))
    assert anon["type"] == "struct"
    assert anon["nullable"] is False
    assert {f["name"] for f in anon["fields"]} == {"inner_id"}


# ── legacy nested vector — three orderings ───────────────────────────────


def test_legacy_nested_array_brackets_after_name():
    """`record … end <name>[];` — brackets after name (already supported)."""
    src = (
        'record\n'
        '  record\n'
        '    line_id integer NULL;\n'
        '  end items[] NULL;\n'
        'end;\n'
    )
    s = parse_dml_string(src)
    f = next(iter(s.values()))["fields"][0]
    assert f["name"] == "items"
    assert f["type"] == "struct"
    assert f["array"] is True


def test_legacy_nested_array_brackets_before_name():
    """`record … end[] <name>;` — brackets before name."""
    src = (
        'record\n'
        '  record\n'
        '    line_id integer NULL;\n'
        '  end[] items NULL;\n'
        'end;\n'
    )
    s = parse_dml_string(src)
    f = next(iter(s.values()))["fields"][0]
    assert f["name"] == "items"
    assert f["type"] == "struct"
    assert f["array"] is True


def test_legacy_nested_array_brackets_before_name_fixed():
    """`record … end[3] <name> NOT NULL;` — fixed length, brackets first."""
    src = (
        'record\n'
        '  record\n'
        '    a integer NULL;\n'
        '    b integer NULL;\n'
        '  end[3] triplet NOT NULL;\n'
        'end;\n'
    )
    s = parse_dml_string(src)
    f = next(iter(s.values()))["fields"][0]
    assert f["name"] == "triplet"
    assert f["type"] == "struct"
    assert f["array"] is True
    assert f["array_length"] == 3
    assert f["nullable"] is False


def test_legacy_nested_anonymous_array():
    """`record … end[];` — fully anonymous array of records."""
    src = (
        'record\n'
        '  outer_id integer NULL;\n'
        '  record\n'
        '    val string(20) NULL;\n'
        '  end[];\n'
        'end;\n'
    )
    s = parse_dml_string(src)
    rec = next(iter(s.values()))
    anon = next(f for f in rec["fields"] if f["name"].startswith("_anon_record_"))
    assert anon["type"] == "struct"
    assert anon["array"] is True


# ── combined: deep nesting + arrays in legacy form ────────────────────────


def test_legacy_combined_nested_with_arrays_inside_arrays():
    """Legacy form, struct→array_of_struct→primitive_array, all in one tree."""
    src = (
        'record\n'
        '  customer_id integer NULL;\n'
        '  record\n'
        '    record\n'
        '      sku       string(20)   NULL;\n'
        '      qty       decimal(10,2) NULL;\n'
        '      modifiers string(20)[] NULL;\n'
        '    end[] line_items NULL;\n'
        '    total decimal(12,2) NULL;\n'
        '  end order;\n'
        'end;\n'
    )
    s = parse_dml_string(src)
    rec = next(iter(s.values()))
    order = next(f for f in rec["fields"] if f["name"] == "order")
    assert order["type"] == "struct"
    inner = {f["name"]: f for f in order["fields"]}
    items = inner["line_items"]
    assert items["type"] == "struct"
    assert items["array"] is True
    line_inner = {f["name"]: f for f in items["fields"]}
    assert line_inner["modifiers"]["array"] is True
    assert line_inner["modifiers"]["type"] == "string"


def test_legacy_combined_round_trips_to_pyspark_struct():
    try:
        from backend.parser.dml_parser import to_struct_type
        from pyspark.sql.types import StructType, ArrayType
    except Exception:
        pytest.skip("PySpark not installed")
    src = (
        'record\n'
        '  customer_id integer NULL;\n'
        '  record\n'
        '    record\n'
        '      sku       string(20)   NULL;\n'
        '      modifiers string(20)[] NULL;\n'
        '    end[] line_items NULL;\n'
        '  end order;\n'
        'end;\n'
    )
    schema = next(iter(parse_dml_string(src).values()))
    st = to_struct_type(schema)
    f = {x.name: x for x in st.fields}
    order = f["order"].dataType
    assert isinstance(order, StructType)
    items = next(x for x in order.fields if x.name == "line_items")
    assert isinstance(items.dataType, ArrayType)
    assert isinstance(items.dataType.elementType, StructType)
    inner = next(x for x in items.dataType.elementType.fields if x.name == "modifiers")
    assert isinstance(inner.dataType, ArrayType)


# ── 2. Nested vectors / arrays of records ─────────────────────────────────


def test_modern_array_of_records_unbounded():
    """`<name> record … end[] [mods];` — modern form, unbounded vector of structs."""
    src = (
        'DEFINE customer BEGIN\n'
        '  id integer NOT NULL;\n'
        '  addresses record\n'
        '                street string(50) NULL;\n'
        '                city   string(30) NULL;\n'
        '            end[] NULL;\n'
        'END\n'
    )
    s = parse_dml_string(src)
    a = next(f for f in s["customer"]["fields"] if f["name"] == "addresses")
    assert a["type"] == "struct"
    assert a["array"] is True
    assert "array_length" not in a   # unbounded


def test_modern_array_of_records_fixed_length():
    """`record … end[5] [mods];` — fixed-occurs vector of structs."""
    src = (
        'DEFINE x BEGIN\n'
        '  contacts record\n'
        '               name  string(40) NULL;\n'
        '               phone string(20) NULL;\n'
        '           end[3] NOT NULL;\n'
        'END\n'
    )
    s = parse_dml_string(src)
    c = s["x"]["fields"][0]
    assert c["type"] == "struct"
    assert c["array"] is True
    assert c["array_length"] == 3
    assert c["nullable"] is False


def test_legacy_array_of_records():
    """Legacy form with array brackets: `record … end <name>[];`."""
    src = (
        'record\n'
        '  outer_id integer NULL;\n'
        '  record\n'
        '    line_id integer NULL;\n'
        '    qty     decimal(10,2) NULL;\n'
        '  end line_items[] NULL;\n'
        'end;\n'
    )
    s = parse_dml_string(src)
    rec = next(iter(s.values()))
    li = next(f for f in rec["fields"] if f["name"] == "line_items")
    assert li["type"] == "struct"
    assert li["array"] is True
    assert {f["name"] for f in li["fields"]} == {"line_id", "qty"}


def test_fixed_length_primitive_vector():
    """`tags string(20)[5] NULL;` — fixed-occurs primitive array."""
    src = 'DEFINE x BEGIN tags string(20)[5] NULL; END'
    s = parse_dml_string(src)
    f = s["x"]["fields"][0]
    assert f["type"] == "string"
    assert f["array"] is True
    assert f["array_length"] == 5


# ── 3. Combined: nested record holding arrays + array of records nested ──


def test_combined_nested_with_inner_arrays():
    """A struct field whose own fields include arrays and arrays of structs."""
    src = (
        'DEFINE customer BEGIN\n'
        '  id integer NOT NULL;\n'
        '  profile record\n'
        '              name      string(40) NULL;\n'
        '              tags      string(20)[]   NULL;\n'
        '              addresses record\n'
        '                            street string(50) NULL;\n'
        '                            city   string(30) NULL;\n'
        '                        end[]                  NULL;\n'
        '          end NOT NULL;\n'
        'END\n'
    )
    s = parse_dml_string(src)
    profile = next(f for f in s["customer"]["fields"] if f["name"] == "profile")
    inner = {f["name"]: f for f in profile["fields"]}
    assert inner["tags"]["type"] == "string"
    assert inner["tags"]["array"] is True
    assert inner["addresses"]["type"] == "struct"
    assert inner["addresses"]["array"] is True
    assert {f["name"] for f in inner["addresses"]["fields"]} == {"street", "city"}


def test_combined_to_struct_type_round_trip():
    """The full StructType conversion handles arbitrary nest+vector combinations."""
    try:
        from backend.parser.dml_parser import to_struct_type
        from pyspark.sql.types import StructType, ArrayType
    except Exception:
        pytest.skip("PySpark not installed")
    src = (
        'DEFINE order BEGIN\n'
        '  order_id integer NOT NULL;\n'
        '  customer record\n'
        '               id   integer NULL;\n'
        '               name string(40) NULL;\n'
        '           end NOT NULL;\n'
        '  items record\n'
        '            sku       string(20) NULL;\n'
        '            qty       decimal(10,2) NULL;\n'
        '            modifiers string(20)[] NULL;\n'
        '        end[] NULL;\n'
        'END\n'
    )
    st = to_struct_type(parse_dml_string(src)["order"])
    f = {x.name: x for x in st.fields}
    # nested struct (single)
    assert isinstance(f["customer"].dataType, StructType)
    # array of struct
    assert isinstance(f["items"].dataType, ArrayType)
    items_elem = f["items"].dataType.elementType
    assert isinstance(items_elem, StructType)
    inner = {x.name: x for x in items_elem.fields}
    # primitive array inside the array-of-struct element
    assert isinstance(inner["modifiers"].dataType, ArrayType)


def test_legacy_nested_with_default_value_user_style():
    """The user's earlier delimiter+default trick should compose with legacy nested."""
    src = (
        'record\n'
        '  cust_id   decimal("¨", ) NULL;\n'
        '  cust_name string("¨", ) NULL;\n'
        '  record\n'
        '    street string("¨", ) NULL;\n'
        '    zip    string("\\n") NULL;\n'
        '  end addr;\n'
        '  newline string(1) NULL = "\\n";\n'
        'end;\n'
    )
    s = parse_dml_string(src)
    rec = next(iter(s.values()))
    f = {x["name"]: x for x in rec["fields"]}
    assert f["cust_id"]["delimiter"] == "¨"
    assert f["addr"]["type"] == "struct"
    inner = {x["name"]: x for x in f["addr"]["fields"]}
    assert inner["zip"]["delimiter"] == "\n"
    assert f["newline"]["default"] == "\n"


# ── Phase 2 features: macros, format-strings, byte-positional, packed/ebcdic ──


# 1) Macro / ${VAR} interpolation in DML

def test_macro_interpolation_in_lengths_and_types():
    src = (
        'DEFINE customer BEGIN\n'
        '    name      string(${MAX_NAME_LEN}) NULL;\n'
        '    sequence  ${ID_TYPE}                NOT NULL;\n'
        '    balance   decimal(${PREC}, ${SCALE}) NULL;\n'
        'END'
    )
    s = parse_dml_string(src, params={
        "MAX_NAME_LEN": "50",
        "ID_TYPE": "integer",
        "PREC": "10",
        "SCALE": "2",
    })
    f = {x["name"]: x for x in s["customer"]["fields"]}
    assert f["name"]["args"] == [50]
    assert f["sequence"]["type"] == "integer"
    assert f["balance"]["args"] == [10, 2]


def test_macro_interpolation_no_params_strips_silently():
    """Unresolved ${VAR} is stripped silently so macro-driven DML can be
    parsed even without the macro values handy."""
    src = 'DEFINE x BEGIN a string(${LEN}) NULL; END'
    s = parse_dml_string(src)   # no params → no crash
    f = s["x"]["fields"][0]
    assert f["type"] == "string"
    # ${LEN} stripped to empty → string() with no length arg
    assert f["args"] == []


# 2) Format-string date/time types

def test_date_format_string_captured():
    src = (
        'DEFINE x BEGIN\n'
        '    birth   date("YYYY-MM-DD")           NULL;\n'
        '    ts      datetime("YYYY-MM-DD HH:MM:SS") NULL;\n'
        'END'
    )
    s = parse_dml_string(src)
    f = {x["name"]: x for x in s["x"]["fields"]}
    # Date: format stored, no delimiter
    assert f["birth"]["format"] == "YYYY-MM-DD"
    assert "delimiter" not in f["birth"]
    # Datetime: format stored, no delimiter
    assert f["ts"]["format"] == "YYYY-MM-DD HH:MM:SS"


def test_playground_emits_date_format_for_csv():
    from backend.api.routes.dml_playground import convert, ConvertRequest
    # Use explicit delimiters so the classifier picks CSV (not fixed_width).
    src = (
        'DEFINE feed BEGIN\n'
        '    id     string("|") NULL;\n'
        '    when   date("YYYY-MM-DD") NULL;\n'
        '    seen   datetime("YYYY-MM-DD HH:MM:SS") NULL;\n'
        'END'
    )
    resp = convert(ConvertRequest(dml=src))
    s = resp.schemas[0]
    assert s.recommended_format.name == "csv"
    # Date format "YYYY-MM-DD" → "yyyy-MM-dd"; timestamp "YYYY-MM-DD HH:MM:SS" → "yyyy-MM-dd HH:mm:ss"
    assert '.option("dateFormat", "yyyy-MM-dd")' in s.pyspark_code
    assert '.option("timestampFormat", "yyyy-MM-dd HH:mm:ss")' in s.pyspark_code


# 3) Packed / EBCDIC primitive types

def test_packed_decimal_recognized():
    src = (
        'DEFINE x BEGIN\n'
        '    amount packed_decimal(10, 2) NOT NULL;\n'
        '    raw    binary(4)              NULL;\n'
        '    name   ebcdic_string(40)      NULL;\n'
        'END'
    )
    s = parse_dml_string(src)
    f = {x["name"]: x for x in s["x"]["fields"]}
    # packed_decimal is normalised to decimal but encoding=packed_decimal preserved
    assert f["amount"]["type"] == "decimal"
    assert f["amount"]["encoding"] == "packed_decimal"
    assert f["amount"]["args"] == [10, 2]
    # binary type
    assert f["raw"]["type"] == "binary"
    assert f["raw"]["encoding"] == "binary"
    # ebcdic_string normalised to string with encoding tag
    assert f["name"]["type"] == "string"
    assert f["name"]["encoding"] == "ebcdic"


def test_binary_round_trips_to_pyspark():
    try:
        from backend.parser.dml_parser import to_struct_type
        from pyspark.sql.types import BinaryType
    except Exception:
        pytest.skip("PySpark not installed")
    src = 'DEFINE x BEGIN raw binary(8) NULL; END'
    st = to_struct_type(parse_dml_string(src)["x"])
    assert isinstance(st.fields[0].dataType, BinaryType)


def test_playground_routes_ebcdic_to_cobrix():
    from backend.api.routes.dml_playground import convert, ConvertRequest
    src = (
        'DEFINE legacy_feed BEGIN\n'
        '    id     ebcdic_string(10) NOT NULL;\n'
        '    amount packed_decimal(8, 2) NULL;\n'
        'END'
    )
    resp = convert(ConvertRequest(dml=src))
    s = resp.schemas[0]
    assert s.recommended_format.name == "ebcdic_cobol"
    assert s.feature_flags["has_ebcdic"] is True
    assert s.feature_flags["has_packed_decimal"] is True
    assert "spark-cobol" in s.pyspark_code
    assert 'copybook_contents' in s.pyspark_code


# 4) Byte-positional fixed-length records

def test_fixed_width_layout_offsets():
    src = (
        'DEFINE rec BEGIN\n'
        '    a string(10)  NOT NULL;\n'
        '    b string(20)  NOT NULL;\n'
        '    c integer     NOT NULL;\n'
        '    d decimal(8)  NOT NULL;\n'
        'END'
    )
    s = parse_dml_string(src)
    rec = s["rec"]
    assert rec["layout"] == "fixed"
    f = {x["name"]: x for x in rec["fields"]}
    assert f["a"]["offset"] == 0
    assert f["a"]["length"] == 10
    assert f["b"]["offset"] == 10
    assert f["b"]["length"] == 20
    assert f["c"]["offset"] == 30
    assert f["c"]["length"] == 4   # default integer = 4 bytes
    assert f["d"]["offset"] == 34
    assert f["d"]["length"] == 8
    assert rec["record_length"] == 42


def test_fixed_width_with_delimited_field_falls_back_to_mixed():
    src = (
        'DEFINE rec BEGIN\n'
        '    a string(10)        NOT NULL;\n'
        '    b string("|")       NOT NULL;\n'
        '    c integer           NOT NULL;\n'
        'END'
    )
    s = parse_dml_string(src)
    assert s["rec"]["layout"] == "mixed"
    assert "record_length" not in s["rec"]


def test_delimited_only_layout_tagged():
    src = (
        'DEFINE feed BEGIN\n'
        '    a string("|") NULL;\n'
        '    b string("|") NULL;\n'
        'END'
    )
    s = parse_dml_string(src)
    assert s["feed"]["layout"] == "delimited"


def test_playground_emits_substring_reader_for_fixed_width():
    from backend.api.routes.dml_playground import convert, ConvertRequest
    src = (
        'DEFINE rec BEGIN\n'
        '    a string(10)  NOT NULL;\n'
        '    b string(20)  NOT NULL;\n'
        '    c integer     NOT NULL;\n'
        'END'
    )
    resp = convert(ConvertRequest(dml=src))
    s = resp.schemas[0]
    assert s.recommended_format.name == "fixed_width"
    assert s.feature_flags["has_fixed_layout"] is True
    # The emitted code should use substring-based reading.
    assert 'spark.read.text(' in s.pyspark_code
    assert 'F.substring("value", 1, 10)' in s.pyspark_code     # field a
    assert 'F.substring("value", 11, 20)' in s.pyspark_code    # field b (offset 10 → 1-indexed 11)
    assert 'F.substring("value", 31, 4)' in s.pyspark_code     # field c
    # Output goes to parquet
    assert '.format("parquet")' in s.pyspark_code


# ── Phase 3: external test-suite gap closures ────────────────────────────


def test_group_keyword_alias_for_record():
    """`group … end <name>;` should parse identically to `record … end <name>;`."""
    src = (
        'record\n'
        '  group\n'
        '    math    decimal(10,2) NULL;\n'
        '    science decimal(10,2) NULL;\n'
        '  end scores;\n'
        'end;\n'
    )
    s = parse_dml_string(src)
    rec = next(iter(s.values()))
    scores = rec["fields"][0]
    assert scores["name"] == "scores"
    assert scores["type"] == "struct"
    assert {f["name"] for f in scores["fields"]} == {"math", "science"}


def test_group_keyword_modern_form():
    """Modern form: `<name> group … end NULL;`."""
    src = (
        'DEFINE student BEGIN\n'
        '    id integer NOT NULL;\n'
        '    scores group\n'
        '               math    integer NULL;\n'
        '               science integer NULL;\n'
        '           end NOT NULL;\n'
        'END\n'
    )
    s = parse_dml_string(src)
    f = next(x for x in s["student"]["fields"] if x["name"] == "scores")
    assert f["type"] == "struct"
    assert f["nullable"] is False


def test_null_indicator_function_arg():
    """`string(",", null(""))` — function-call-shaped null indicator must parse."""
    src = (
        'record\n'
        '  string(",", null("")) name;\n'
        '  string(",", null("\\\\N")) optional;\n'
        'end;\n'
    )
    s = parse_dml_string(src)
    f = {x["name"]: x for x in next(iter(s.values()))["fields"]}
    assert f["name"]["type"] == "string"
    assert f["name"]["delimiter"] == ","
    assert f["name"]["null_indicator"] == ""
    assert f["optional"]["null_indicator"] == "\\N"


def test_c_style_define_macro():
    """`#define NAME value` should be expanded throughout the source."""
    src = (
        '#define DELIM ","\n'
        '#define LEN 50\n'
        'record\n'
        '  string(DELIM) name;\n'
        '  string(LEN) extra;\n'
        'end;\n'
    )
    s = parse_dml_string(src)
    fields = {f["name"]: f for f in next(iter(s.values()))["fields"]}
    assert fields["name"]["delimiter"] == ","
    assert fields["extra"]["args"] == [50]


def test_c_macro_word_boundary_safety():
    """A `#define DELIM ","` should not corrupt `MYDELIMETER`."""
    src = (
        '#define DELIM ","\n'
        'record\n'
        '  string(DELIM)         a;\n'
        '  string(",")           MYDELIMETER;\n'
        'end;\n'
    )
    s = parse_dml_string(src)
    fields = {f["name"]: f for f in next(iter(s.values()))["fields"]}
    # MYDELIMETER must stay intact as a field name
    assert "MYDELIMETER" in fields


def test_unresolved_dollar_var_is_dropped():
    """`${UNRESOLVED}` becomes empty when no params are supplied."""
    src = 'record\n  string(${UNK}) name;\nend;\n'
    s = parse_dml_string(src)   # must not raise
    f = next(iter(s.values()))["fields"][0]
    assert f["name"] == "name"
    assert f["type"] == "string"


# ── lossy mode in to_struct_type ──────────────────────────────────────────


def test_to_struct_type_lossy_collapses_decimal_and_dates():
    try:
        from backend.parser.dml_parser import to_struct_type
        from pyspark.sql.types import (
            StructType, DoubleType, StringType, DecimalType, DateType, TimestampType,
        )
    except Exception:
        pytest.skip("PySpark not installed")

    src = (
        'DEFINE x BEGIN\n'
        '  amount    decimal(10, 2) NULL;\n'
        '  birth     date           NULL;\n'
        '  ts        datetime       NULL;\n'
        '  name      string(40)     NULL;\n'
        'END'
    )
    schema = parse_dml_string(src)["x"]

    # Default (precise) mapping — production use
    precise = to_struct_type(schema)
    by_name_p = {f.name: f for f in precise.fields}
    assert isinstance(by_name_p["amount"].dataType, DecimalType)
    assert isinstance(by_name_p["birth"].dataType, DateType)
    assert isinstance(by_name_p["ts"].dataType, TimestampType)
    assert isinstance(by_name_p["name"].dataType, StringType)

    # Lossy mapping — for downstream consumers that can't take DecimalType
    lossy = to_struct_type(schema, lossy=True)
    by_name_l = {f.name: f for f in lossy.fields}
    assert isinstance(by_name_l["amount"].dataType, DoubleType)
    assert isinstance(by_name_l["birth"].dataType, StringType)
    assert isinstance(by_name_l["ts"].dataType, StringType)
    # Strings stay strings either way
    assert isinstance(by_name_l["name"].dataType, StringType)


def test_lossy_mode_recurses_into_nested_structs():
    try:
        from backend.parser.dml_parser import to_struct_type
        from pyspark.sql.types import StructType, DoubleType, ArrayType
    except Exception:
        pytest.skip("PySpark not installed")

    src = (
        'DEFINE x BEGIN\n'
        '  totals record\n'
        '             gross decimal(10,2) NULL;\n'
        '             tax   decimal(10,2) NULL;\n'
        '         end NULL;\n'
        '  scores decimal(5,0)[] NULL;\n'
        'END'
    )
    schema = parse_dml_string(src)["x"]
    lossy = to_struct_type(schema, lossy=True)
    by = {f.name: f for f in lossy.fields}

    # Nested struct: inner decimals collapsed to Double
    totals_inner = {f.name: f for f in by["totals"].dataType.fields}
    assert isinstance(totals_inner["gross"].dataType, DoubleType)
    assert isinstance(totals_inner["tax"].dataType, DoubleType)

    # Array element type also collapsed
    assert isinstance(by["scores"].dataType, ArrayType)
    assert isinstance(by["scores"].dataType.elementType, DoubleType)


# ── multi-dim arrays + reserved-keyword rejection + empty delimiter ──────


def test_multi_dim_primitive_array():
    src = 'record\n  decimal(",") matrix[][];\nend;\n'
    s = parse_dml_string(src)
    f = next(iter(s.values()))["fields"][0]
    assert f["array"] is True
    assert f["array_dims"] == [None, None]


def test_multi_dim_array_round_trips_to_pyspark():
    try:
        from backend.parser.dml_parser import to_struct_type
        from pyspark.sql.types import ArrayType, DoubleType, StringType
    except Exception:
        pytest.skip("PySpark not installed")
    src = 'record\n  decimal(",") matrix[][];\nend;\n'
    schema = next(iter(parse_dml_string(src).values()))
    st = to_struct_type(schema, lossy=True)
    matrix = st.fields[0].dataType
    assert isinstance(matrix, ArrayType)
    assert isinstance(matrix.elementType, ArrayType)
    # Lossy mode: decimal → DoubleType
    assert isinstance(matrix.elementType.elementType, DoubleType)


def test_three_dim_array_of_struct():
    """Combine struct + multi-dim — exercises the cross-product."""
    src = (
        'record\n'
        '  record\n'
        '    string(",") val;\n'
        '  end cube[][][];\n'
        'end;\n'
    )
    s = parse_dml_string(src)
    f = next(iter(s.values()))["fields"][0]
    assert f["type"] == "struct"
    assert f["array"] is True
    assert f["array_dims"] == [None, None, None]


def test_reserved_keywords_rejected():
    """`union` and `variant` must surface as a clear parse error.
    (`if` was previously here but is now supported as a conditional.)"""
    for kw in ("union", "variant"):
        src = f'record\n  {kw}\n    string(",") a;\n  end;\nend;\n'
        with pytest.raises(ValueError, match="Unsupported DML construct"):
            parse_dml_string(src)


def test_empty_delimiter_rejected():
    src = 'record\n  string("") name;\nend;\n'
    with pytest.raises(ValueError, match="Empty delimiter"):
        parse_dml_string(src)


# ── conditional fields (if/else) ──────────────────────────────────────────


def test_conditional_then_only_block_form():
    """`if (cond) then <field>; end;` — single branch, no else."""
    src = (
        'record\n'
        '  string(",") type;\n'
        '  if (type == "purchase") then\n'
        '    decimal(",") amount;\n'
        '  end;\n'
        'end;\n'
    )
    s = parse_dml_string(src)
    fields = next(iter(s.values()))["fields"]
    by_name = {f["name"]: f for f in fields}
    assert {"type", "amount"} == set(by_name)
    # Conditional field is forced nullable and tagged with the condition.
    amt = by_name["amount"]
    assert amt["nullable"] is True
    assert amt["condition"] == {
        "col": "type", "op": "==", "value": "purchase", "branch": "then",
    }


def test_conditional_then_else():
    """if/else with one field per branch."""
    src = (
        'record\n'
        '  string(",") type;\n'
        '  if (type == "purchase") then\n'
        '    decimal(",") amount;\n'
        '  else\n'
        '    string(",") reason;\n'
        '  end;\n'
        'end;\n'
    )
    s = parse_dml_string(src)
    fields = next(iter(s.values()))["fields"]
    by = {f["name"]: f for f in fields}
    assert by["amount"]["condition"]["branch"] == "then"
    assert by["reason"]["condition"]["branch"] == "else"
    # Both branches must be nullable since only one is populated per row.
    assert by["amount"]["nullable"] is True
    assert by["reason"]["nullable"] is True


def test_conditional_round_trips_to_pyspark():
    """The flattened nullable struct should produce the right StructType."""
    try:
        from backend.parser.dml_parser import to_struct_type
        from pyspark.sql.types import StringType, DoubleType
    except Exception:
        pytest.skip("PySpark not installed")
    src = (
        'record\n'
        '  string(",") type;\n'
        '  if (type == "A") then\n'
        '    decimal(",") amount;\n'
        '  else\n'
        '    string(",") reason;\n'
        '  end;\n'
        'end;\n'
    )
    schema = next(iter(parse_dml_string(src).values()))
    st = to_struct_type(schema, lossy=True)
    by = {f.name: f for f in st.fields}
    assert isinstance(by["amount"].dataType, DoubleType)
    assert isinstance(by["reason"].dataType, StringType)
    # All branch fields are nullable
    assert by["amount"].nullable is True
    assert by["reason"].nullable is True


def test_conditional_with_numeric_comparison():
    """Numeric RHS and `<` operator."""
    src = (
        'record\n'
        '  decimal(",") amount;\n'
        '  if (amount < 100) then\n'
        '    string(",") low_flag;\n'
        '  end;\n'
        'end;\n'
    )
    s = parse_dml_string(src)
    flag = next(f for f in next(iter(s.values()))["fields"] if f["name"] == "low_flag")
    assert flag["condition"]["op"] == "<"
    assert flag["condition"]["value"] == 100


def test_conditional_missing_end_fails():
    """Parser must require the conditional's own `end[;]` — otherwise it
    would steal the parent record's terminator."""
    src = (
        'record\n'
        '  if (flag == 0) then\n'
        '    decimal(",") x;\n'
        '  else\n'
        '    string(",") y;\n'
        'end;\n'
    )
    with pytest.raises(ValueError):
        parse_dml_string(src)


def test_conditional_nested_disallowed():
    """v1 does not support nesting one conditional inside another's branch."""
    src = (
        'record\n'
        '  if (a == 1) then\n'
        '    if (b == 2) then\n'
        '      string(",") x;\n'
        '    end;\n'
        '  end;\n'
        'end;\n'
    )
    with pytest.raises(ValueError, match="Nested"):
        parse_dml_string(src)


def test_conditional_block_without_then_keyword():
    """Some DML omits `then` — the parser should accept either form."""
    src = (
        'record\n'
        '  if (type == "X")\n'
        '    string(",") x;\n'
        '  end;\n'
        'end;\n'
    )
    s = parse_dml_string(src)
    assert next(iter(s.values()))["fields"][0]["name"] == "x"


def test_nested_record_struct_code_emission():
    """The codegen helper should emit a valid `StructType(...)` literal."""
    from backend.components._emit_helpers import schema_dict_to_struct_code
    schema = parse_dml_string(NESTED)["customer"]
    code = schema_dict_to_struct_code(schema)
    # The generated code must reference both StructField and a nested StructType
    # and must compile in a namespace that has the pyspark types available.
    try:
        from pyspark.sql.types import (
            StructType, StructField, StringType, IntegerType, LongType,
            DoubleType, FloatType, BooleanType, DateType, TimestampType,
            DecimalType, ArrayType,
        )
    except Exception:
        pytest.skip("PySpark not installed")
    ns = {
        "StructType": StructType, "StructField": StructField,
        "StringType": StringType, "IntegerType": IntegerType,
        "LongType": LongType, "DoubleType": DoubleType,
        "FloatType": FloatType, "BooleanType": BooleanType,
        "DateType": DateType, "TimestampType": TimestampType,
        "DecimalType": DecimalType, "ArrayType": ArrayType,
    }
    obj = eval(code, ns)
    inner = {f.name: f for f in obj.fields}
    assert isinstance(inner["address"].dataType, StructType)


# ════════════════════════════════════════════════════════════════════════════
# Full DML reference-grammar coverage — Phase 1 + Phase 2 tests.
#
# Phase 1: brace-close nested record · `[int]` unbounded vector ·
#          optional trailing `;` after top-level `end`.
# Phase 2: `type X = record … end;` aliases · annotations · encoding
#          prefixes · `metadata type = record …` · `integer(N)` byte width ·
#          `decimal("format")` form.
# ════════════════════════════════════════════════════════════════════════════


# ── Phase 1: brace-close + [int] ────────────────────────────────────────────


def test_brace_close_nested_record():
    """``record … } NAME;`` — generator-emitted brace-close form."""
    src = (
        'record\n'
        '  string(",") id;\n'
        '  record\n'
        '    string(",") street;\n'
        '    string(",") city;\n'
        '  } address;\n'
        'end;\n'
    )
    s = parse_dml_string(src)
    rec = next(iter(s.values()))
    addr = next(f for f in rec["fields"] if f["name"] == "address")
    assert addr["type"] == "struct"
    assert [f["name"] for f in addr["fields"]] == ["street", "city"]


def test_brace_close_with_array_suffix():
    """``} projects[5];`` — fixed-length array after brace-close."""
    src = (
        'record\n'
        '  record\n'
        '    string(",") proj_id;\n'
        '  } projects[5];\n'
        'end;\n'
    )
    s = parse_dml_string(src)
    rec = next(iter(s.values()))
    proj = rec["fields"][0]
    assert proj["name"] == "projects"
    assert proj["array"] is True
    assert proj["array_length"] == 5


def test_brace_close_with_depending_on_array():
    """``} projects[count];`` — variable-length array depending on a field."""
    src = (
        'record\n'
        '  integer(2) project_count;\n'
        '  record\n'
        '    string(4) proj_id;\n'
        '  } projects[project_count];\n'
        'end\n'
    )
    s = parse_dml_string(src)
    rec = next(iter(s.values()))
    proj = next(f for f in rec["fields"] if f["name"] == "projects")
    assert proj["array"] is True
    assert proj.get("depends_on") == "project_count"


def test_brace_close_with_int_unbounded_array_before_name():
    """``} [int] map_entries;`` — Hive-DML map idiom: brackets BEFORE name."""
    src = (
        'record\n'
        '  record\n'
        '    record\n'
        '      string(",") key;\n'
        '      string(",") value;\n'
        '    } [int] entries;\n'
        '  } meta_info;\n'
        'end\n'
    )
    s = parse_dml_string(src)
    rec = next(iter(s.values()))
    meta = next(f for f in rec["fields"] if f["name"] == "meta_info")
    entries = next(f for f in meta["fields"] if f["name"] == "entries")
    assert entries["array"] is True
    # Unbounded array: `array_length` key is absent (only set for fixed sizes).
    assert "array_length" not in entries


def test_int_unbounded_vector_marker():
    """``string(",")[int] field;`` — `[int]` means unbounded vector."""
    src = (
        'record\n'
        '  string(",")[int] tags;\n'
        'end\n'
    )
    s = parse_dml_string(src)
    rec = next(iter(s.values()))
    tags = rec["fields"][0]
    assert tags["name"] == "tags"
    assert tags["array"] is True
    # Unbounded array: `array_length` key is absent (only set for fixed sizes).
    assert "array_length" not in tags


def test_top_level_end_no_semicolon():
    """Generator-emitted DML often omits the trailing `;` after final `end`."""
    src = (
        'record\n'
        '  string(",") name;\n'
        'end\n'  # no semicolon
    )
    s = parse_dml_string(src)
    assert next(iter(s.values()))["fields"][0]["name"] == "name"


def test_int_bracket_round_trips_to_array_type():
    """`[int]` round-trips to `ArrayType(StringType())` in PySpark."""
    try:
        from pyspark.sql.types import ArrayType, StringType, StructType
    except Exception:
        pytest.skip("PySpark not installed")
    from backend.parser.dml_parser import to_struct_type
    src = 'record\n  string(",")[int] tags;\nend\n'
    schema = next(iter(parse_dml_string(src).values()))
    st = to_struct_type(schema)
    assert isinstance(st, StructType)
    assert isinstance(st.fields[0].dataType, ArrayType)
    assert isinstance(st.fields[0].dataType.elementType, StringType)


# ── Phase 2: encoding prefixes ──────────────────────────────────────────────


def test_encoding_prefix_string():
    """`utf8 string("¨") name;` — encoding prefix recorded, type unchanged."""
    src = 'record\n  utf8 string(",") name;\nend\n'
    s = parse_dml_string(src)
    f = next(iter(s.values()))["fields"][0]
    assert f["type"] == "string"
    assert f.get("encoding") == "utf8"


def test_encoding_prefix_decimal():
    """`ascii decimal(5) emp_id;` — ascii-encoded decimal."""
    src = 'record\n  ascii decimal(5) emp_id;\nend\n'
    s = parse_dml_string(src)
    f = next(iter(s.values()))["fields"][0]
    assert f["type"] == "decimal"
    assert f["args"] == [5]
    assert f.get("encoding") == "ascii"


def test_encoding_prefix_packed_decimal():
    """`packed decimal(9,2) emp_salary;` — packed-decimal."""
    src = 'record\n  packed decimal(9,2) salary;\nend\n'
    s = parse_dml_string(src)
    f = next(iter(s.values()))["fields"][0]
    assert f["type"] == "decimal"
    assert f["args"] == [9, 2]
    assert f.get("encoding") == "packed"


def test_encoding_prefix_top_level_record():
    """`utf8 record … end` — leading prefix at top level is stripped."""
    src = 'utf8 record\n  string(",") name;\nend\n'
    s = parse_dml_string(src)
    rec = next(iter(s.values()))
    assert rec["fields"][0]["name"] == "name"


# ── Phase 2: type aliases + UDT references ──────────────────────────────────


def test_type_alias_declaration_and_reference():
    """`type X = record … end;` declared once, referenced from a field."""
    src = (
        'type address_t = record\n'
        '  string(",") street;\n'
        '  string(",") city;\n'
        'end;\n'
        '\n'
        'record\n'
        '  string(",") name;\n'
        '  address_t home;\n'
        'end;\n'
    )
    s = parse_dml_string(src)
    # The alias itself is NOT a top-level schema.
    assert "address_t" not in s
    # The using record IS a top-level schema with `home` inlined as struct.
    rec = next(iter(s.values()))
    home = next(f for f in rec["fields"] if f["name"] == "home")
    assert home["type"] == "struct"
    assert [f["name"] for f in home["fields"]] == ["street", "city"]
    assert home.get("udt_name") == "address_t"


def test_unknown_udt_errors():
    """Referencing a never-declared type → hard error."""
    src = (
        'record\n'
        '  string(",") name;\n'
        '  unknown_t mystery;\n'
        'end;\n'
    )
    with pytest.raises(ValueError, match="Unknown DML type"):
        parse_dml_string(src)


def test_type_alias_array_of_udt():
    """``vehicle_info_t[int] Vehicle;`` — array of user-defined type."""
    src = (
        'type vehicle_t = record\n'
        '  string(",") make;\n'
        'end;\n'
        '\n'
        'record\n'
        '  vehicle_t[int] Vehicles;\n'
        'end;\n'
    )
    s = parse_dml_string(src)
    rec = next(iter(s.values()))
    vehicles = rec["fields"][0]
    assert vehicles["type"] == "struct"
    assert vehicles["array"] is True
    assert vehicles.get("udt_name") == "vehicle_t"


# ── Phase 2: annotations ────────────────────────────────────────────────────


def test_single_annotation_skipped_and_stored():
    """`@style="element"` parses, lands on field['annotations']."""
    src = (
        'record\n'
        '  string(",") name @style="element";\n'
        'end;\n'
    )
    s = parse_dml_string(src)
    f = next(iter(s.values()))["fields"][0]
    assert f["name"] == "name"
    assert f.get("annotations") == {"style": "element"}


def test_multi_annotation():
    """`@style="attribute", name="type"` — comma-separated multi-annotation."""
    src = (
        'record\n'
        '  string(",") vehicle_type @style="attribute", name="type";\n'
        'end;\n'
    )
    s = parse_dml_string(src)
    f = next(iter(s.values()))["fields"][0]
    assert f.get("annotations") == {"style": "attribute", "name": "type"}


def test_annotation_on_brace_close_record():
    """`} Insured @style="element";` — annotation on a nested record."""
    src = (
        'record\n'
        '  record\n'
        '    string(",") name;\n'
        '  } Insured @style="element";\n'
        'end;\n'
    )
    s = parse_dml_string(src)
    insured = next(iter(s.values()))["fields"][0]
    assert insured["name"] == "Insured"
    assert insured.get("annotations") == {"style": "element"}


# ── Phase 2: integer alias + decimal format string ──────────────────────────


def test_integer_byte_width_4():
    """`integer(4)` → IntegerType."""
    try:
        from pyspark.sql.types import IntegerType
    except Exception:
        pytest.skip("PySpark not installed")
    from backend.parser.dml_parser import to_struct_type
    src = 'record\n  integer(4) year;\nend\n'
    schema = next(iter(parse_dml_string(src).values()))
    st = to_struct_type(schema)
    assert isinstance(st.fields[0].dataType, IntegerType)


def test_integer_byte_width_8():
    """`integer(8)` → LongType (BIGINT)."""
    try:
        from pyspark.sql.types import LongType
    except Exception:
        pytest.skip("PySpark not installed")
    from backend.parser.dml_parser import to_struct_type
    src = 'record\n  integer(8) transaction_id;\nend\n'
    schema = next(iter(parse_dml_string(src).values()))
    st = to_struct_type(schema)
    assert isinstance(st.fields[0].dataType, LongType)


def test_decimal_format_string():
    """`decimal(".2") amount;` → DecimalType(38, 2)."""
    try:
        from pyspark.sql.types import DecimalType
    except Exception:
        pytest.skip("PySpark not installed")
    from backend.parser.dml_parser import to_struct_type
    src = 'record\n  decimal(".2") premium;\nend\n'
    schema = next(iter(parse_dml_string(src).values()))
    st = to_struct_type(schema)
    dt = st.fields[0].dataType
    assert isinstance(dt, DecimalType)
    assert (dt.precision, dt.scale) == (38, 2)


# ── Phase 2: metadata keyword variant ───────────────────────────────────────


def test_metadata_root_keyword():
    """`metadata type = record … end;` parses as the root schema."""
    src = (
        'metadata type = record\n'
        '  string(",") id @style="attribute";\n'
        '  string(",") name;\n'
        'end;\n'
    )
    s = parse_dml_string(src)
    assert "metadata" in s
    assert [f["name"] for f in s["metadata"]["fields"]] == ["id", "name"]


# ── Real-world acceptance gates from real-dml.md ────────────────────────────


REAL_DML_XML_ORDER = (
    'utf8 record\n'
    '  /* Mapping for the id attribute */\n'
    '  decimal(",") id;\n'
    '\n'
    '  /* Mapping for the Customer element */\n'
    '  string(",") Customer;\n'
    '\n'
    '  /* Mapping for the Items wrapper and nested Product elements */\n'
    '  record\n'
    '    string(",")[int] Product;\n'
    '  } Items;\n'
    '\n'
    '  string(",") newline = "\\n";\n'
    'end\n'
)


def test_real_dml_xml_order():
    """Acceptance gate: full Example 1 (XML→DML, simple Order) parses."""
    s = parse_dml_string(REAL_DML_XML_ORDER)
    rec = next(iter(s.values()))
    names = [f["name"] for f in rec["fields"]]
    assert "id" in names and "Customer" in names and "Items" in names
    items = next(f for f in rec["fields"] if f["name"] == "Items")
    assert items["type"] == "struct"
    product = items["fields"][0]
    assert product["name"] == "Product"
    assert product["array"] is True


REAL_DML_COBOL_EMPLOYEE = (
    '/* Generated from COBOL copybook */\n'
    'record\n'
    '  ascii decimal(5) emp_id;\n'
    '  string(20) emp_name;\n'
    '\n'
    '  record\n'
    '    string(10) emp_dept;\n'
    '    packed decimal(9,2) emp_salary;\n'
    '  } emp_details;\n'
    '\n'
    '  ascii decimal(2) project_count;\n'
    '\n'
    '  record\n'
    '    string(4) proj_id;\n'
    '  } projects[project_count];\n'
    '\n'
    '  string(1) newline = "\\n";\n'
    'end\n'
)


def test_real_dml_cobol_employee():
    """Acceptance gate: full Example 3 (COBOL→DML, employee record) parses."""
    s = parse_dml_string(REAL_DML_COBOL_EMPLOYEE)
    rec = next(iter(s.values()))
    names = [f["name"] for f in rec["fields"]]
    assert names[:3] == ["emp_id", "emp_name", "emp_details"]
    salary = next(
        f for f in next(d for d in rec["fields"] if d["name"] == "emp_details")["fields"]
        if f["name"] == "emp_salary"
    )
    assert salary.get("encoding") == "packed"
    projects = next(f for f in rec["fields"] if f["name"] == "projects")
    assert projects["array"] is True
    assert projects.get("depends_on") == "project_count"


REAL_DML_HIVE_SALES = (
    '/* Generated from Hive Table: sales_data */\n'
    'record\n'
    '  integer(8) transaction_id;\n'
    '  string("\\001") customer_name;\n'
    '  decimal(10,2) amount;\n'
    '\n'
    '  record\n'
    '    string("\\001")[int] item;\n'
    '  } items_list;\n'
    '\n'
    '  record\n'
    '    record\n'
    '      string("\\001") key;\n'
    '      string("\\001") value;\n'
    '    } [int] map_entries;\n'
    '  } meta_info;\n'
    '\n'
    '  integer(4) year;\n'
    '  integer(4) month;\n'
    '\n'
    '  string("\\n") newline;\n'
    'end\n'
)


def test_real_dml_hive_sales():
    """Acceptance gate: full Example 4 (Hive→DML, sales_data) parses."""
    s = parse_dml_string(REAL_DML_HIVE_SALES)
    rec = next(iter(s.values()))
    names = [f["name"] for f in rec["fields"]]
    assert "transaction_id" in names and "items_list" in names and "meta_info" in names
    meta = next(f for f in rec["fields"] if f["name"] == "meta_info")
    map_entries = next(f for f in meta["fields"] if f["name"] == "map_entries")
    assert map_entries["array"] is True


REAL_DML_XML_INSURANCE = (
    '/* Generated by xml-to-dml utility */\n'
    '\n'
    'type policy_address_t = record\n'
    '  string(",") Street @style="element";\n'
    '  string(",") City @style="element";\n'
    '  decimal(",") Zip @style="element";\n'
    'end;\n'
    '\n'
    'type vehicle_info_t = record\n'
    '  string(",") vehicle_type @style="attribute", name="type";\n'
    '  string(",") Make @style="element";\n'
    '  decimal(",") Year @style="element";\n'
    '  decimal(".2") Premium @style="element";\n'
    'end;\n'
    '\n'
    'metadata type = record\n'
    '  string(",") id @style="attribute";\n'
    '\n'
    '  record\n'
    '    string(",") Name @style="element";\n'
    '    policy_address_t Address;\n'
    '  } Insured @style="element";\n'
    '\n'
    '  record\n'
    '    vehicle_info_t[int] Vehicle;\n'
    '  } Vehicles @style="element";\n'
    '\n'
    '  string(",") newline = "\\n";\n'
    'end;\n'
)


def test_real_dml_xml_insurance():
    """Acceptance gate: full Example 2 (XML→DML, insurance policy) parses."""
    s = parse_dml_string(REAL_DML_XML_INSURANCE)
    assert "metadata" in s
    rec = s["metadata"]
    insured = next(f for f in rec["fields"] if f["name"] == "Insured")
    assert insured["type"] == "struct"
    address = next(f for f in insured["fields"] if f["name"] == "Address")
    assert address["type"] == "struct"
    assert address.get("udt_name") == "policy_address_t"
    vehicles = next(f for f in rec["fields"] if f["name"] == "Vehicles")
    vehicle = vehicles["fields"][0]
    assert vehicle["array"] is True
    assert vehicle.get("udt_name") == "vehicle_info_t"
