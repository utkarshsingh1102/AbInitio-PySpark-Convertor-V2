import pytest
from expected_schemas_set3 import *

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
# 1. Deep Nested + Arrays
# -------------------------
def test_nested_array_complex():
    dml = """
    record
      decimal(",") user_id;
      record
        string(",") session_id;
        record
          string(",") event_type;
          string(",") timestamp;
        end events[];
      end sessions[];
    end;
    """
    run_success_test(dml, nested_array_complex)


# -------------------------
# 2. Nullable + Nested Combo
# -------------------------
def test_nullable_nested():
    dml = """
    record
      string(",", null("")) name;
      record
        string(",", null("NA")) email;
        decimal(",", null("-1")) age;
      end profile;
    end;
    """
    run_success_test(dml, nullable_nested)


# -------------------------
# 3. Fixed + Delimited Hybrid
# -------------------------
def test_fixed_delimited():
    dml = """
    record
      string(5) code;
      string(",") desc;
    end;
    """
    run_success_test(dml, fixed_delimited)


# -------------------------
# 4. Multi-Dimensional Array
# -------------------------
def test_multi_array():
    dml = """
    record
      decimal(",") matrix[][];
    end;
    """
    run_success_test(dml, multi_array)


# -------------------------
# 5. Macro inside Nested
# -------------------------
def test_macro_nested():
    dml = """
    #define SEP ","
    record
      record
        string(SEP) field;
      end data;
    end;
    """
    run_success_test(dml, macro_nested)


# -------------------------
# 6. Date + Nullable
# -------------------------
def test_date_nullable():
    dml = """
    record
      date("YYYY-MM-DD", null("0000-00-00")) dob;
    end;
    """
    run_success_test(dml, date_nullable)


# -------------------------
# 7. Delimiter Edge Case (FAIL)
# -------------------------
def test_invalid_delimiter_fail():
    dml = """
    record
      string("") name;
    end;
    """
    run_failure_test(dml)


# -------------------------
# 8. Missing End (FAIL)
# -------------------------
def test_missing_end_fail():
    dml = """
    record
      string(",") name;
    """
    run_failure_test(dml)


# -------------------------
# 9. Invalid Array Syntax (FAIL)
# -------------------------
def test_invalid_array_syntax_fail():
    dml = """
    record
      string(",") items[abc];
    end;
    """
    run_failure_test(dml)


# -------------------------
# 10. Mixed Unsupported Features (FAIL)
# -------------------------
def test_union_inside_nested_fail():
    dml = """
    record
      record
        union
          string(",") a;
          string(",") b;
        end;
      end x;
    end;
    """
    run_failure_test(dml)


# -------------------------
# 11. Ambiguous Delimiters
# -------------------------
def test_mixed_delimiters():
    dml = """
    record
      string("|") col1;
      string(",") col2;
      string("\\n") col3;
    end;
    """
    # Should still parse structurally
    ast = parse_dml(dml)
    schema = convert_to_spark_schema(ast)
    assert len(schema.fields) == 3


# -------------------------
# 12. Deep Recursion Stress
# -------------------------
def test_deep_recursion():
    dml = """
    record
      record
        record
          record
            record
              string(",") value;
            end l5;
          end l4;
        end l3;
      end l2;
    end;
    """
    ast = parse_dml(dml)
    schema = convert_to_spark_schema(ast)
    assert schema is not None


# -------------------------
# 13. Large Field Count
# -------------------------
def test_large_flat():
    dml = "record\n"
    for i in range(50):
        dml += f'  string(",") col{i};\n'
    dml += "end;"
    
    ast = parse_dml(dml)
    schema = convert_to_spark_schema(ast)
    assert len(schema.fields) == 50