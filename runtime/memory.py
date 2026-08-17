"""Module 4: agent memory — episodic, semantic, procedural. All Postgres.

Episodic: past runs (what happened, outcome). Recall is full-text search ranked
  by relevance + recency. An `embedding vector(1536)` column is present but
  unpopulated — # ponytail: FTS recall until an embedding API key is configured;
  then backfill embeddings and switch recall to pgvector cosine.
Semantic: durable facts (vendor is verified, user prefers X). Append-only:
  contradicted facts are superseded, never edited — same philosophy as audit.
Procedural: versioned prompt/policy store; agents fetch the latest version.

Decision note (2026-08-15): evaluated LangMem/Mem0 per ENTERPRISE.md §4 — both
impose their own storage layers and LLM extraction pipelines; our needs are
three tables on infrastructure we already run. Hand-rolled thin.
"""

from typing import Any

import psycopg

from runtime import schema
from psycopg.types.json import Jsonb

DDL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS episodic_memory (
    id         bigserial PRIMARY KEY,
    app        text NOT NULL,
    run_id     text NOT NULL,
    summary    text NOT NULL,
    outcome    jsonb NOT NULL,
    embedding  vector(1536),
    tsv        tsvector GENERATED ALWAYS AS (to_tsvector('english', summary)) STORED,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS episodic_tsv_idx ON episodic_memory USING gin (tsv);

CREATE TABLE IF NOT EXISTS semantic_memory (
    id                bigserial PRIMARY KEY,
    app               text NOT NULL,
    subject           text NOT NULL,
    fact              text NOT NULL,
    detail            jsonb NOT NULL DEFAULT '{}',
    superseded_by     bigint REFERENCES semantic_memory(id),
    created_at        timestamptz NOT NULL DEFAULT now(),
    last_confirmed_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS semantic_subject_idx ON semantic_memory (app, subject);

CREATE TABLE IF NOT EXISTS prompt_store (
    id         bigserial PRIMARY KEY,
    app        text NOT NULL,
    name       text NOT NULL,
    version    int NOT NULL,
    content    text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (app, name, version)
);
"""


def ensure_schema(conn: psycopg.Connection) -> None:
    schema.apply_once(conn, "memory", DDL)


# --- episodic ---

def write_episode(
    conn: psycopg.Connection, app: str, run_id: str, summary: str, outcome: dict
) -> None:
    conn.execute(
        "INSERT INTO episodic_memory (app, run_id, summary, outcome)"
        " VALUES (%s, %s, %s, %s)",
        (app, run_id, summary, Jsonb(outcome)),
    )
    conn.commit()


def recall(conn: psycopg.Connection, app: str, query: str, k: int = 5) -> list[dict]:
    """Top-k relevant episodes: FTS rank, recency as tiebreak (staleness discount)."""
    rows = conn.execute(
        "SELECT run_id, summary, outcome, created_at,"
        "       ts_rank(tsv, plainto_tsquery('english', %s)) AS rank"
        " FROM episodic_memory"
        " WHERE app = %s AND tsv @@ plainto_tsquery('english', %s)"
        " ORDER BY rank DESC, created_at DESC LIMIT %s",
        (query, app, query, k),
    ).fetchall()
    return [
        {"run_id": r, "summary": s, "outcome": o, "at": str(t)}
        for r, s, o, t, _ in rows
    ]


# --- semantic ---

def remember_fact(
    conn: psycopg.Connection, app: str, subject: str, fact: str,
    detail: dict[str, Any] | None = None,
) -> int:
    row = conn.execute(
        "INSERT INTO semantic_memory (app, subject, fact, detail)"
        " VALUES (%s, %s, %s, %s) RETURNING id",
        (app, subject, fact, Jsonb(detail or {})),
    ).fetchone()
    conn.commit()
    return row[0]


def supersede_fact(conn: psycopg.Connection, old_id: int, app: str, subject: str,
                   fact: str, detail: dict[str, Any] | None = None) -> int:
    new_id = remember_fact(conn, app, subject, fact, detail)
    conn.execute(
        "UPDATE semantic_memory SET superseded_by = %s WHERE id = %s", (new_id, old_id)
    )
    conn.commit()
    return new_id


def facts_for(conn: psycopg.Connection, app: str, subject: str) -> list[dict]:
    """Current (non-superseded) facts for a subject, newest first."""
    rows = conn.execute(
        "SELECT id, fact, detail, last_confirmed_at FROM semantic_memory"
        " WHERE app = %s AND subject = %s AND superseded_by IS NULL"
        " ORDER BY id DESC",
        (app, subject),
    ).fetchall()
    return [{"id": i, "fact": f, "detail": d, "confirmed": str(t)} for i, f, d, t in rows]


# --- procedural ---

def save_prompt(conn: psycopg.Connection, app: str, name: str, content: str) -> int:
    version = conn.execute(
        "SELECT coalesce(max(version), 0) + 1 FROM prompt_store"
        " WHERE app = %s AND name = %s",
        (app, name),
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO prompt_store (app, name, version, content) VALUES (%s, %s, %s, %s)",
        (app, name, version, content),
    )
    conn.commit()
    return version


def current_prompt(conn: psycopg.Connection, app: str, name: str) -> str | None:
    row = conn.execute(
        "SELECT content FROM prompt_store WHERE app = %s AND name = %s"
        " ORDER BY version DESC LIMIT 1",
        (app, name),
    ).fetchone()
    return row[0] if row else None
