"""Expected schemas for Set C — uses the lossy mapping (decimal → Double,
date/datetime → String) so it matches what the adapter emits.
"""
from pyspark.sql.types import (
    StructType, StructField, StringType, DoubleType, ArrayType,
)

# 1. Deep nested + arrays
nested_array_complex = StructType([
    StructField("user_id", DoubleType(), True),
    StructField("sessions", ArrayType(
        StructType([
            StructField("session_id", StringType(), True),
            StructField("events", ArrayType(
                StructType([
                    StructField("event_type", StringType(), True),
                    StructField("timestamp", StringType(), True),
                ])
            ), True),
        ])
    ), True),
])

# 2. Nullable + nested combo
nullable_nested = StructType([
    StructField("name", StringType(), True),
    StructField("profile", StructType([
        StructField("email", StringType(), True),
        StructField("age", DoubleType(), True),
    ]), True),
])

# 3. Fixed-length + delimited hybrid
fixed_delimited = StructType([
    StructField("code", StringType(), True),
    StructField("desc", StringType(), True),
])

# 4. Multi-dimensional array (2-d)
multi_array = StructType([
    StructField("matrix", ArrayType(ArrayType(DoubleType())), True),
])

# 5. Macro inside a nested record
macro_nested = StructType([
    StructField("data", StructType([
        StructField("field", StringType(), True),
    ]), True),
])

# 6. Date with nullable indicator
date_nullable = StructType([
    StructField("dob", StringType(), True),
])
