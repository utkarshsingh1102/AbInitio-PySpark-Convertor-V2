import pytest
from expected_schemas import *

# You must implement these in your project
from dml_parser import parse_dml
from dml_to_spark import convert_to_spark_schema


# -------------------------
# Helper
# -------------------------
def run_success_test(dml, expected_schema):
    ast = parse_dml(dml)
    schema = convert_to_spark_schema(ast)
    assert schema == expected_schema


def run_failure_test(dml):
    with pytest.raises(Exception):
        parse_dml(dml)


# -------------------------
# 1. Flat
# -------------------------
def test_flat_basic():
    dml = """
    record
      string(",") name;
      decimal(",") age;
      string("\\n") city;
    end;
    """
    run_success_test(dml, flat_basic)


def test_flat_mixed():
    dml = """
    record
      decimal(",") id;
      string(",") email;
      date("YYYYMMDD") dob;
    end;
    """
    run_success_test(dml, flat_mixed)


# -------------------------
# 2. Nested
# -------------------------
def test_nested_simple():
    dml = """
    record
      string(",") name;
      record
        string(",") city;
        string(",") state;
      end address;
    end;
    """
    run_success_test(dml, nested_simple)


def test_nested_deep():
    dml = """
    record
      record
        record
          string(",") deep;
        end inner;
      end outer;
    end;
    """
    run_success_test(dml, nested_deep)


# -------------------------
# 3. Group
# -------------------------
def test_group_basic():
    dml = """
    record
      group
        decimal(",") math;
        decimal(",") science;
      end scores;
    end;
    """
    run_success_test(dml, group_basic)


# -------------------------
# 4. Arrays
# -------------------------
def test_array_variable():
    dml = """
    record
      string(",") items[];
    end;
    """
    run_success_test(dml, array_variable)


def test_array_fixed():
    dml = """
    record
      decimal(",") scores[5];
    end;
    """
    run_success_test(dml, array_fixed)


# -------------------------
# 5. Union (Fail)
# -------------------------
def test_union_fail():
    dml = """
    record
      union
        string(",") name;
        decimal(",") id;
      end;
    end;
    """
    run_failure_test(dml)


# -------------------------
# 6. Variant (Fail)
# -------------------------
def test_variant_fail():
    dml = """
    record
      variant
        record
          string(",") a;
        end;
        record
          string(",") b;
        end;
      end;
    end;
    """
    run_failure_test(dml)


# -------------------------
# 7. Conditional (Fail)
# -------------------------
def test_conditional_fail():
    dml = """
    record
      if type == "A" then
        string(",") a;
      end;
    end;
    """
    run_failure_test(dml)


# -------------------------
# 8. Nullable
# -------------------------
def test_nullable():
    dml = """
    record
      string(",", null("")) name;
    end;
    """
    run_success_test(dml, nullable_basic)


# -------------------------
# 9. Fixed Length
# -------------------------
def test_fixed_length():
    dml = """
    record
      string(10) name;
      decimal(5) age;
    end;
    """
    run_success_test(dml, fixed_basic)


# -------------------------
# 10. Delimited
# -------------------------
def test_delimited_csv():
    dml = """
    record
      string(",") name;
      decimal(",") age;
    end;
    """
    run_success_test(dml, delimited_csv)


def test_delimited_tsv():
    dml = """
    record
      string("\\t") col1;
      string("\\t") col2;
    end;
    """
    run_success_test(dml, delimited_tsv)


# -------------------------
# 11. Packed / Binary
# -------------------------
def test_packed():
    dml = """
    record
      decimal("packed decimal", 5) amount;
    end;
    """
    run_success_test(dml, packed_decimal)


def test_binary():
    dml = """
    record
      decimal("binary", 4) value;
    end;
    """
    run_success_test(dml, binary_type)


# -------------------------
# 12. Date / Time
# -------------------------
def test_date():
    dml = """
    record
      date("YYYY-MM-DD") dob;
    end;
    """
    run_success_test(dml, date_format)


def test_datetime():
    dml = """
    record
      datetime("YYYY-MM-DD HH:MM:SS") ts;
    end;
    """
    run_success_test(dml, datetime_format)


# -------------------------
# 13. Macro
# -------------------------
def test_macro_define():
    dml = """
    #define DELIM ","
    record
      string(DELIM) name;
    end;
    """
    run_success_test(dml, macro_basic)


def test_macro_env():
    dml = """
    record
      string(${DELIM}) name;
    end;
    """
    run_success_test(dml, macro_basic)