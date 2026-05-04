"""Production-grade SparkSession builder code (string template).

Used by the codegen header. The values are derived from pipeline metadata
(pipeline name, DOP), not hardcoded constants.
"""
from __future__ import annotations

_TEMPLATE = """\
spark = (
    SparkSession.builder
    .appName({app_name!r})

    # ── Adaptive Query Execution ─────────────────────────────────────
    .config("spark.sql.adaptive.enabled",                            "true")
    .config("spark.sql.adaptive.coalescePartitions.enabled",         "true")
    .config("spark.sql.adaptive.coalescePartitions.minPartitionNum", {dop!r})
    .config("spark.sql.adaptive.skewJoin.enabled",                   "true")
    .config("spark.sql.adaptive.skewJoin.skewedPartitionThresholdInBytes", "256mb")

    # ── Join thresholds ──────────────────────────────────────────────
    .config("spark.sql.autoBroadcastJoinThreshold",                  str({broadcast_bytes}))

    # ── Shuffle ──────────────────────────────────────────────────────
    .config("spark.sql.shuffle.partitions",                          {shuffle_partitions!r})

    # ── Serialization (Kryo) ─────────────────────────────────────────
    .config("spark.serializer",                                      "org.apache.spark.serializer.KryoSerializer")
    .config("spark.kryoserializer.buffer.max",                       "512m")

    # ── Memory / columnar ────────────────────────────────────────────
    .config("spark.sql.inMemoryColumnarStorage.compressed",          "true")
    .config("spark.sql.inMemoryColumnarStorage.batchSize",           "20000")

    # ── Parquet ──────────────────────────────────────────────────────
    .config("spark.sql.parquet.compression.codec",                   "snappy")
    .config("spark.sql.parquet.mergeSchema",                         "false")
    .config("spark.sql.parquet.filterPushdown",                      "true")

    # ── Schema safety ────────────────────────────────────────────────
    .config("spark.sql.caseSensitive",                               "false")
    .config("spark.sql.storeAssignmentPolicy",                       "STRICT")

    # ── Tungsten / codegen ───────────────────────────────────────────
    .config("spark.sql.codegen.wholeStage",                          "true")
    .config("spark.sql.codegen.fallback",                            "true")

    .getOrCreate()
)
"""


def build_session_code(
    app_name: str,
    *,
    dop: int = 4,
    shuffle_partitions: str = "200",
    broadcast_threshold_mb: int = 10,
) -> str:
    return _TEMPLATE.format(
        app_name=app_name,
        dop=str(dop),
        shuffle_partitions=str(shuffle_partitions),
        broadcast_bytes=broadcast_threshold_mb * 1024 * 1024,
    )
