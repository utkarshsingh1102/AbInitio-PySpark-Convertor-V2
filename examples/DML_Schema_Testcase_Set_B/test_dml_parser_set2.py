import pytest
from expected_schemas_set2 import *

from dml_parser import parse_dml
from dml_to_spark import convert_to_spark_schema


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
def test_flat_pipe():
    dml = """
    record
      decimal("|") user_id;
      string("|") username;
      string("\\n") country;
    end;
    """
    run_success_test(dml, flat_pipe)


def test_flat_semicolon():
    dml = """
    record
      string(";") product;
      decimal("\\n") price;
    end;
    """
    run_success_test(dml, flat_semicolon)


# -------------------------
# 2. Nested
# -------------------------
def test_nested_alt():
    dml = """
    record
      decimal(",") id;
      record
        string(",") email;
        string(",") phone;
      end profile;
    end;
    """
    run_success_test(dml, nested_alt)


def test_nested_chain():
    dml = """
    record
      record
        record
          record
            string(",") value;
          end level3;
        end level2;
      end level1;
    end;
    """
    run_success_test(dml, nested_chain)


# -------------------------
# 3. Group
# -------------------------
def test_group_alt():
    dml = """
    record
      group
        decimal(",") views;
        decimal(",") clicks;
      end metrics;
    end;
    """
    run_success_test(dml, group_alt)


# -------------------------
# 4. Arrays
# -------------------------
def test_array_strings():
    dml = """
    record
      string(",") tags[];
    end;
    """
    run_success_test(dml, array_strings)


def test_array_nested_records():
    dml = """
    record
      record
        decimal(",") order_id;
        decimal(",") amount;
      end orders[];
    end;
    """
    run_success_test(dml, array_nested)


# -------------------------
# 5. Union (Fail)
# -------------------------
def test_union_fail_2():
    dml = """
    record
      union
        decimal(",") x;
        decimal(",") y;
      end;
    end;
    """
    run_failure_test(dml)


# -------------------------
# 6. Variant (Fail)
# -------------------------
def test_variant_fail_2():
    dml = """
    record
      variant
        record
          decimal(",") x;
        end;
        record
          decimal(",") y;
        end;
      end;
    end;
    """
    run_failure_test(dml)


# -------------------------
# 7. Conditional (Fail)
# -------------------------
def test_conditional_fail_2():
    dml = """
    record
      if flag == 0 then
        decimal(",") x;
      else
        string(",") y;
    end;
    """
    run_failure_test(dml)


# -------------------------
# 8. Nullable
# -------------------------
def test_nullable_multi():
    dml = """
    record
      string(",", null("NA")) status;
      decimal(",", null("-1")) score;
    end;
    """
    run_success_test(dml, nullable_multi)


# -------------------------
# 9. Fixed Length
# -------------------------
def test_fixed_alt():
    dml = """
    record
      string(5) code;
      decimal(3) value;
    end;
    """
    run_success_test(dml, fixed_alt)


# -------------------------
# 10. Delimited
# -------------------------
def test_delimited_pipe():
    dml = """
    record
      decimal("|") user_id;
      string("|") username;
      string("\\n") country;
    end;
    """
    run_success_test(dml, delimited_pipe)


def test_delimited_semicolon():
    dml = """
    record
      string(";") product;
      decimal("\\n") price;
    end;
    """
    run_success_test(dml, delimited_semicolon)


# -------------------------
# 11. Packed / Binary
# -------------------------
def test_packed_alt():
    dml = """
    record
      decimal("packed decimal", 7) balance;
    end;
    """
    run_success_test(dml, packed_alt)


def test_binary_alt():
    dml = """
    record
      decimal("binary", 2) flag;
    end;
    """
    run_success_test(dml, binary_alt)


# -------------------------
# 12. Date / Time
# -------------------------
def test_date_alt():
    dml = """
    record
      date("YYYY/MM/DD") created_date;
    end;
    """
    run_success_test(dml, date_alt)


def test_datetime_alt():
    dml = """
    record
      datetime("YYYY-MM-DD HH:MM") event_time;
    end;
    """
    run_success_test(dml, datetime_alt)


# -------------------------
# 13. Macro
# -------------------------
def test_macro_alt_define():
    dml = """
    #define SEP "|"
    record
      string(SEP) field1;
    end;
    """
    run_success_test(dml, macro_alt)


def test_macro_alt_env():
    dml = """
    record
      string(${SEP}) field1;
    end;
    """
    run_success_test(dml, macro_alt)