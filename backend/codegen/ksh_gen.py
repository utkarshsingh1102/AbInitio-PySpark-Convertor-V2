"""Generate a production .ksh wrapper around the emitted PySpark script."""
from __future__ import annotations

from typing import Any

from ..ir.models import IRNode

_TEMPLATE = """\
#!/usr/bin/env bash
set -uo pipefail

PIPELINE_NAME="${{PIPELINE_NAME:-{pipeline_name}}}"
INPUT_FILE="${{INPUT_FILE:-{default_input}}}"
OUTPUT_FILE="${{OUTPUT_FILE:-{default_output}}}"
LOG_DIR="${{LOG_DIR:-logs}}"
RETRIES="${{RETRIES:-{retries}}}"
SPARK_MASTER="${{SPARK_MASTER:-local[*]}}"

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/${{PIPELINE_NAME}}_$(date +%Y%m%d_%H%M%S).log"

echo "[$(date)] Starting: $PIPELINE_NAME" | tee -a "$LOG_FILE"

EXIT_CODE=1
attempt=0
while [ $attempt -lt $RETRIES ]; do
  attempt=$((attempt + 1))
  echo "[$(date)] Attempt $attempt of $RETRIES" | tee -a "$LOG_FILE"

  # Run spark-submit and tee its output. We capture spark-submit's exit
  # code via PIPESTATUS (requires bash + pipefail set above).
  spark-submit \\
    --master "$SPARK_MASTER" \\
    {extra_flags}pipeline.py \\
      --input  "$INPUT_FILE" \\
      --output "$OUTPUT_FILE" \\
    2>&1 | tee -a "$LOG_FILE"
  EXIT_CODE=${{PIPESTATUS[0]}}

  if [ "$EXIT_CODE" = "0" ]; then
    echo "[$(date)] Completed successfully" | tee -a "$LOG_FILE"
    exit 0
  fi
  echo "[$(date)] FAILED: exit=$EXIT_CODE (attempt $attempt)" | tee -a "$LOG_FILE"
done

echo "[$(date)] FAILED after $RETRIES attempts" | tee -a "$LOG_FILE"
exit "$EXIT_CODE"
"""


def generate_ksh(
    ir_nodes: list[IRNode],
    pipeline_name: str = "pipeline",
    retries: int = 1,
    spark_flags: list[str] | None = None,
) -> str:
    default_input, default_output = _resolve_io_paths(ir_nodes)
    flags = " \\\n    ".join(spark_flags or [])
    extra = f"{flags} \\\n    " if flags else ""
    return _TEMPLATE.format(
        pipeline_name=pipeline_name,
        default_input=default_input or "data/input",
        default_output=default_output or "data/output",
        retries=retries,
        extra_flags=extra,
    )


def _resolve_io_paths(ir_nodes: list[IRNode]) -> tuple[str, str]:
    in_path = ""
    out_path = ""
    for n in ir_nodes:
        if n.ir_type == "read" and not in_path:
            in_path = n.config.get("filename") or n.config.get("path") or ""
        if n.ir_type == "write":
            out_path = n.config.get("filename") or n.config.get("path") or out_path
    return in_path, out_path
