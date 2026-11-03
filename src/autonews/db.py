from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    region TEXT NOT NULL DEFAULT 'global',
    lang TEXT NOT NULL DEFAULT 'en',
    weight REAL NOT NULL DEFAULT 1.0,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_status TEXT,
    last_checked_at TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    url TEXT NOT NULL,
    canonical_url TEXT,
    title TEXT NOT NULL,
    summary TEXT,
    body TEXT,
    lang TEXT,
    published_at TEXT,
    fetched_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    media_urls TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'new'
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_canonical ON articles(canonical_url);
CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_hash ON articles(content_hash);

CREATE TABLE IF NOT EXISTS stories (
    id INTEGER PRIMARY KEY,
    primary_article_id INTEGER NOT NULL REFERENCES articles(id),
    title_key TEXT NOT NULL,
    region TEXT NOT NULL DEFAULT 'global',
    article_count INTEGER NOT NULL DEFAULT 1,
    score INTEGER,
    score_reason TEXT,
    headline_ru TEXT,
    topic TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stories_status ON stories(status);

CREATE TABLE IF NOT EXISTS story_articles (
    story_id INTEGER NOT NULL REFERENCES stories(id),
    article_id INTEGER NOT NULL REFERENCES articles(id),
    PRIMARY KEY (story_id, article_id)
);

CREATE TABLE IF NOT EXISTS candidates (
    id INTEGER PRIMARY KEY,
    story_id INTEGER NOT NULL REFERENCES stories(id),
    headline_ru TEXT NOT NULL,
    body_ru TEXT NOT NULL,
    hashtags TEXT NOT NULL DEFAULT '',
    media_path TEXT,
    media_kind TEXT,
    media_source_url TEXT,
    attestation TEXT NOT NULL DEFAULT '{}',
    model TEXT,
    token_usage TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'drafted',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates(status);

CREATE TABLE IF NOT EXISTS digests (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    message_id INTEGER
);

CREATE TABLE IF NOT EXISTS digest_items (
    digest_id INTEGER NOT NULL REFERENCES digests(id),
    position INTEGER NOT NULL,
    candidate_id INTEGER NOT NULL REFERENCES candidates(id),
    PRIMARY KEY (digest_id, position)
);

CREATE TABLE IF NOT EXISTS pending (
    token TEXT PRIMARY KEY,
    candidate_id INTEGER NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS publish_log (
    id INTEGER PRIMARY KEY,
    candidate_id INTEGER NOT NULL,
    channel_id TEXT NOT NULL,
    message_id INTEGER,
    published_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS llm_usage (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    role TEXT,
    model TEXT,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    cost REAL NOT NULL DEFAULT 0,
    allowance REAL NOT NULL DEFAULT 0,
    billing_source TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    stage TEXT,
    counters TEXT NOT NULL DEFAULT '{}',
    errors TEXT NOT NULL DEFAULT '[]'
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def start_run(stage: str) -> int:
    with connect() as conn:
        cur = conn.execute("INSERT INTO runs (started_at, stage) VALUES (?, ?)", (now(), stage))
        return int(cur.lastrowid)


def finish_run(run_id: int, counters: dict, errors: list[str]) -> None:
    import json

    with connect() as conn:
        conn.execute(
            "UPDATE runs SET finished_at = ?, counters = ?, errors = ? WHERE id = ?",
            (now(), json.dumps(counters, ensure_ascii=False), json.dumps(errors, ensure_ascii=False), run_id),
        )


def count(conn: sqlite3.Connection, table: str, where: str = "1=1", params: tuple = ()) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", params).fetchone()[0])
