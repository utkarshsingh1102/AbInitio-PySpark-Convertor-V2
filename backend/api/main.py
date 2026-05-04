"""FastAPI entrypoint."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..graph.client import Neo4jClient
from .routes import convert, dml_playground, dml_visualizer, download, execute, graph, parse, upload

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = Neo4jClient.from_env()
    try:
        client.ensure_indexes()
    except Exception as exc:  # noqa: BLE001
        logging.warning("Neo4j unavailable at startup: %s", exc)
    yield
    client.close()


app = FastAPI(title="Ab Initio → PySpark Conversion Platform", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router)
app.include_router(parse.router)
app.include_router(graph.router)
app.include_router(convert.router)
app.include_router(download.router)
app.include_router(execute.router)
app.include_router(dml_playground.router)
app.include_router(dml_visualizer.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
