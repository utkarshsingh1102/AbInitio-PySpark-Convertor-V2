"""POST /upload — accept .mp / .dml / .xfr files, return a job_id."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from ..deps import job_dir

router = APIRouter()

ALLOWED_EXTS = {".mp", ".dml", ".xfr"}


@router.post("/upload")
async def upload(files: list[UploadFile]) -> dict[str, object]:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    job_id = uuid.uuid4().hex[:12]
    target = job_dir(job_id)

    saved: list[str] = []
    for f in files:
        ext = Path(f.filename or "").suffix.lower()
        if ext not in ALLOWED_EXTS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {f.filename!r} (allowed: {sorted(ALLOWED_EXTS)})",
            )
        out_path = target / Path(f.filename or f"upload{ext}").name
        out_path.write_bytes(await f.read())
        saved.append(out_path.name)

    return {"job_id": job_id, "files": saved}
