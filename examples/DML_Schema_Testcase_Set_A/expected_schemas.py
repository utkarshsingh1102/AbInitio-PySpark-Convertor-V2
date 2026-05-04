from pyspark.sql.types import *

# ---- Flat ----
flat_basic = StructType([
    StructField("name", StringType(), True),
    StructField("age", DoubleType(), True),
    StructField("city", StringType(), True),
])

flat_mixed = StructType([
    StructField("id", DoubleType(), True),
    StructField("email", StringType(), True),
    StructField("dob", StringType(), True),  # assuming string if not mapped
])

# ---- Nested ----
nested_simple = StructType([
    StructField("name", StringType(), True),
    StructField("address", StructType([
        StructField("city", StringType(), True),
        StructField("state", StringType(), True),
    ]), True)
])

nested_deep = StructType([
    StructField("outer", StructType([
        StructField("inner", StructType([
            StructField("deep", StringType(), True)
        ]), True)
    ]), True)
])

# ---- Group (treated as struct) ----
group_basic = StructType([
    StructField("scores", StructType([
        StructField("math", DoubleType(), True),
        StructField("science", DoubleType(), True),
    ]), True)
])

# ---- Arrays ----
array_variable = StructType([
    StructField("items", ArrayType(StringType()), True)
])

array_fixed = StructType([
    StructField("scores", ArrayType(DoubleType()), True)
])

# ---- Nullable ----
nullable_basic = StructType([
    StructField("name", StringType(), True)
])

# ---- Fixed Length ----
fixed_basic = StructType([
    StructField("name", StringType(), True),
    StructField("age", DoubleType(), True),
])

# ---- Delimited ----
# The DML in test_delimited_csv declares only `name` and `age` (no `city`),
# so this can't alias `flat_basic` (which has 3 fields). Define it directly.
delimited_csv = StructType([
    StructField("name", StringType(), True),
    StructField("age", DoubleType(), True),
])

delimited_tsv = StructType([
    StructField("col1", StringType(), True),
    StructField("col2", StringType(), True),
])

# ---- Packed/Binary ----
packed_decimal = StructType([
    StructField("amount", DoubleType(), True)
])

binary_type = StructType([
    StructField("value", DoubleType(), True)
])

# ---- Date ----
date_format = StructType([
    StructField("dob", StringType(), True)
])

datetime_format = StructType([
    StructField("ts", StringType(), True)
])

# ---- Macro ----
macro_basic = StructType([
    StructField("name", StringType(), True)
])