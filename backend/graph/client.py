"""Neo4j driver wrapper.

A thin wrapper that:
  - lazily initializes the official ``neo4j`` driver from env vars
  - exposes ``run`` / ``run_write`` helpers for one-shot queries
  - applies required indexes on first use
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

from neo4j import Driver, GraphDatabase


_INDEX_STATEMENTS = [
    "CREATE INDEX component_pipeline IF NOT EXISTS FOR (c:Component) ON (c.id, c.pipeline_id)",
    "CREATE INDEX pipeline_id        IF NOT EXISTS FOR (p:Pipeline)  ON (p.id)",
    "CREATE INDEX schema_id          IF NOT EXISTS FOR (s:Schema)    ON (s.id)",
]


class Neo4jClient:
    """Singleton-style Neo4j client.

    Use either via ``Neo4jClient.from_env()`` or construct directly.
    Always call ``close()`` on shutdown (FastAPI lifespan handles this).
    """

    _instance: "Neo4jClient | None" = None

    def __init__(self, uri: str, user: str, password: str):
        self._driver: Driver = GraphDatabase.driver(uri, auth=(user, password))
        self._indexes_applied = False

    # ---- factories -----------------------------------------------------------
    @classmethod
    def from_env(cls) -> "Neo4jClient":
        if cls._instance is not None:
            return cls._instance
        uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        user = os.environ.get("NEO4J_USER", "neo4j")
        pwd = os.environ.get("NEO4J_PASSWORD", "password")
        cls._instance = cls(uri, user, pwd)
        return cls._instance

    # ---- lifecycle -----------------------------------------------------------
    def close(self) -> None:
        self._driver.close()
        type(self)._instance = None

    def ensure_indexes(self) -> None:
        if self._indexes_applied:
            return
        with self._driver.session() as s:
            for stmt in _INDEX_STATEMENTS:
                s.run(stmt)
        self._indexes_applied = True

    # ---- query helpers -------------------------------------------------------
    @contextmanager
    def session(self) -> Iterator[Any]:
        with self._driver.session() as s:
            yield s

    def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        with self._driver.session() as s:
            result = s.run(query, **params)
            return [r.data() for r in result]

    def run_write(self, query: str, **params: Any) -> list[dict[str, Any]]:
        def _tx(tx):
            res = tx.run(query, **params)
            return [r.data() for r in res]

        with self._driver.session() as s:
            return s.execute_write(_tx)
