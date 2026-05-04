"""GET /download/{id} — bundle generated .py + .ksh as a zip."""
from __future__ import annotations

import io
import zipfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..deps import job_dir

router = APIRouter()


@router.get("/download/{pipeline_id}")
def download(pipeline_id: str):
    d = job_dir(pipeline_id)
    py_path = d / "pipeline.py"
    ksh_path = d / "pipeline.ksh"
    if not py_path.exists() or not ksh_path.exists():
        raise HTTPException(status_code=404, detail="Run /generate-code first")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("pipeline.py", py_path.read_text())
        zf.writestr("pipeline.ksh", ksh_path.read_text())
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{pipeline_id}.zip"'},
    )
