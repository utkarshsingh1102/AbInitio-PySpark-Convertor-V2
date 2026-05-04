"""Run the generated .ksh script and yield log lines as they arrive.

Provides both a sync ``stream_ksh`` (used by tests) and an async
``stream_ksh_async`` (used by FastAPI's SSE response so the event loop
doesn't block and lines are pushed to the client as they're produced).
"""
from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import AsyncIterator, Iterator


def stream_ksh(workdir: Path, env_overrides: dict[str, str] | None = None) -> Iterator[str]:
    """Sync version. Yields one line per stdout line; final yield is
    ``__exit__:N`` carrying the process exit code.
    """
    ksh = workdir / "pipeline.ksh"
    if not ksh.exists():
        yield f"[error] {ksh} not found"
        yield "__exit__:127"
        return

    yield f"[runner] starting {ksh.name}"

    env = {**os.environ, **(env_overrides or {})}
    shell = "ksh" if _which("ksh") else "bash"
    proc = subprocess.Popen(
        [shell, str(ksh)],
        cwd=str(workdir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        yield line.rstrip("\n")
    proc.wait()
    yield f"__exit__:{proc.returncode}"


async def stream_ksh_async(
    workdir: Path, env_overrides: dict[str, str] | None = None
) -> AsyncIterator[str]:
    """Async version: doesn't block the event loop while spark-submit runs."""
    ksh = workdir / "pipeline.ksh"
    if not ksh.exists():
        yield f"[error] {ksh} not found"
        yield "__exit__:127"
        return

    yield f"[runner] starting {ksh.name}"

    env = {**os.environ, **(env_overrides or {})}
    shell = "ksh" if _which("ksh") else "bash"

    # `python -u` already on driver — but the bash subprocess is what writes
    # the lines; bash uses line-buffered output by default for terminals
    # and block-buffered for pipes. Keep PYTHONUNBUFFERED on for safety.
    env.setdefault("PYTHONUNBUFFERED", "1")

    proc = await asyncio.create_subprocess_exec(
        shell, str(ksh),
        cwd=str(workdir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )
    assert proc.stdout is not None

    while True:
        raw = await proc.stdout.readline()
        if not raw:
            break
        yield raw.decode(errors="replace").rstrip("\n")

    rc = await proc.wait()
    yield f"__exit__:{rc}"


def _which(cmd: str) -> str | None:
    for path in os.environ.get("PATH", "").split(os.pathsep):
        full = os.path.join(path, cmd)
        if os.path.isfile(full) and os.access(full, os.X_OK):
            return full
    return None
