from pyspark.sql.types import *

# ---- Flat ----
flat_pipe = StructType([
    StructField("user_id", DoubleType(), True),
    StructField("username", StringType(), True),
    StructField("country", StringType(), True),
])

flat_semicolon = StructType([
    StructField("product", StringType(), True),
    StructField("price", DoubleType(), True),
])

# ---- Nested ----
nested_alt = StructType([
    StructField("id", DoubleType(), True),
    StructField("profile", StructType([
        StructField("email", StringType(), True),
        StructField("phone", StringType(), True),
    ]), True)
])

nested_chain = StructType([
    StructField("level1", StructType([
        StructField("level2", StructType([
            StructField("level3", StructType([
                StructField("value", StringType(), True)
            ]), True)
        ]), True)
    ]), True)
])

# ---- Group ----
group_alt = StructType([
    StructField("metrics", StructType([
        StructField("views", DoubleType(), True),
        StructField("clicks", DoubleType(), True),
    ]), True)
])

# ---- Arrays ----
array_strings = StructType([
    StructField("tags", ArrayType(StringType()), True)
])

array_nested = StructType([
    StructField("orders", ArrayType(
        StructType([
            StructField("order_id", DoubleType(), True),
            StructField("amount", DoubleType(), True)
        ])
    ), True)
])

# ---- Nullable ----
nullable_multi = StructType([
    StructField("status", StringType(), True),
    StructField("score", DoubleType(), True),
])

# ---- Fixed Length ----
fixed_alt = StructType([
    StructField("code", StringType(), True),
    StructField("value", DoubleType(), True),
])

# ---- Delimited ----
delimited_pipe = flat_pipe

delimited_semicolon = flat_semicolon

# ---- Packed/Binary ----
packed_alt = StructType([
    StructField("balance", DoubleType(), True)
])

binary_alt = StructType([
    StructField("flag", DoubleType(), True)
])

# ---- Date ----
date_alt = StructType([
    StructField("created_date", StringType(), True)
])

datetime_alt = StructType([
    StructField("event_time", StringType(), True)
])

# ---- Macro ----
macro_alt = StructType([
    StructField("field1", StringType(), True)
])