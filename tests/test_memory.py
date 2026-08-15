"""Memory: episodic recall by relevance, semantic supersede, prompt versioning."""

import uuid

import psycopg
import pytest

from runtime import memory
from runtime.config import DATABASE_URL


@pytest.fixture
def conn():
    with psycopg.connect(DATABASE_URL) as c:
        memory.ensure_schema(c)
        yield c


def test_episodic_recall_ranks_relevant(conn):
    app = f"app-{uuid.uuid4().hex[:8]}"
    memory.write_episode(conn, app, "r1", "invoice from Acme Corp approved", {"ok": True})
    memory.write_episode(conn, app, "r2", "PTO balance question answered", {"ok": True})
    memory.write_episode(conn, app, "r3", "invoice from Acme Corp flagged fraud", {"ok": False})

    hits = memory.recall(conn, app, "Acme invoice")
    assert len(hits) == 2
    assert all("Acme" in h["summary"] for h in hits)
    assert memory.recall(conn, app, "vacation days") == []  # no match, no noise


def test_semantic_supersede_hides_old_fact(conn):
    app = f"app-{uuid.uuid4().hex[:8]}"
    old = memory.remember_fact(conn, app, "vendor:acme", "bank account ends 1234")
    facts = memory.facts_for(conn, app, "vendor:acme")
    assert len(facts) == 1

    memory.supersede_fact(conn, old, app, "vendor:acme", "bank account ends 9999")
    facts = memory.facts_for(conn, app, "vendor:acme")
    assert len(facts) == 1
    assert facts[0]["fact"] == "bank account ends 9999"

    # the old fact still exists in storage (append-only), just not current
    total = conn.execute(
        "SELECT count(*) FROM semantic_memory WHERE app = %s", (app,)
    ).fetchone()[0]
    assert total == 2


def test_prompt_versioning(conn):
    app = f"app-{uuid.uuid4().hex[:8]}"
    assert memory.current_prompt(conn, app, "planner") is None
    assert memory.save_prompt(conn, app, "planner", "v1 text") == 1
    assert memory.save_prompt(conn, app, "planner", "v2 text") == 2
    assert memory.current_prompt(conn, app, "planner") == "v2 text"
