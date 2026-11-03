from __future__ import annotations

from .db import connect, now

DIGEST_QUERY = """
SELECT di.position, c.id AS candidate_id, c.headline_ru, c.status, s.score, s.region,
       (SELECT s2.name FROM story_articles sa
          JOIN articles a ON a.id = sa.article_id
          JOIN sources s2 ON s2.id = a.source_id
        WHERE sa.story_id = c.story_id ORDER BY s2.weight DESC LIMIT 1) AS source_name
  FROM digest_items di
  JOIN candidates c ON c.id = di.candidate_id
  JOIN stories s ON s.id = c.story_id
 WHERE di.digest_id = ?
 ORDER BY di.position
"""


def create_digest(limit: int = 25) -> tuple[int, str] | None:
    with connect() as conn:
        rows = conn.execute(
            "SELECT c.id, c.story_id, s.score FROM candidates c JOIN stories s ON s.id = c.story_id "
            "WHERE c.status = 'drafted' AND c.id NOT IN (SELECT candidate_id FROM digest_items) "
            "ORDER BY s.score DESC, c.created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        if not rows:
            return None
        cur = conn.execute("INSERT INTO digests (created_at) VALUES (?)", (now(),))
        digest_id = int(cur.lastrowid)
        for position, row in enumerate(rows, start=1):
            conn.execute(
                "INSERT INTO digest_items (digest_id, position, candidate_id) VALUES (?, ?, ?)",
                (digest_id, position, row["id"]),
            )
    return digest_id, digest_text(digest_id)


def latest_digest() -> int | None:
    with connect() as conn:
        row = conn.execute("SELECT id FROM digests ORDER BY id DESC LIMIT 1").fetchone()
    return int(row["id"]) if row else None


def digest_text(digest_id: int) -> str:
    with connect() as conn:
        rows = conn.execute(DIGEST_QUERY, (digest_id,)).fetchall()
    lines = ["Новые кандидаты. /show N — черновик, /post N — опубликовать, /skip N — отклонить.", ""]
    for row in rows:
        headline = (row["headline_ru"] or "без заголовка")[:95]
        source = row["source_name"] or "?"
        region = (row["region"] or "").upper()
        lines.append(f"{row['position']}. [{row['score']}] {headline} — {source} {region}")
    return "\n".join(lines)


def split_message(text: str, limit: int = 3800) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.splitlines():
        if size + len(line) + 1 > limit and current:
            parts.append("\n".join(current))
            current = []
            size = 0
        current.append(line)
        size += len(line) + 1
    if current:
        parts.append("\n".join(current))
    return parts


def candidate_at(digest_id: int, position: int):
    with connect() as conn:
        row = conn.execute(
            "SELECT c.*, s.score, s.region FROM digest_items di "
            "JOIN candidates c ON c.id = di.candidate_id JOIN stories s ON s.id = c.story_id "
            "WHERE di.digest_id = ? AND di.position = ?",
            (digest_id, position),
        ).fetchone()
    return row


def latest_candidate_at(position: int):
    digest_id = latest_digest()
    if digest_id is None:
        return None
    return candidate_at(digest_id, position)
