import os
import sys

# Make the project root importable as `backend.*`
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest


def _neo4j_available() -> bool:
    try:
        from backend.graph.client import Neo4jClient

        c = Neo4jClient.from_env()
        c.run("RETURN 1 AS x")
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture(scope="session")
def neo4j_client():
    if not _neo4j_available():
        pytest.skip("Neo4j not reachable — start docker-compose to run graph tests")
    from backend.graph.client import Neo4jClient

    return Neo4jClient.from_env()
