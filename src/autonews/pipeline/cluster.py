from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from ..config import Settings
from ..db import connect, now

STOPWORDS = {
    "a", "an", "the", "of", "to", "in", "on", "for", "and", "with", "at", "by", "from", "as",
    "is", "are", "be", "this", "that", "its", "it", "new", "first", "how", "why", "what",
    "will", "has", "have", "was", "were", "after", "before", "over", "under", "more", "most",
    "than", "into", "about", "up", "down", "out", "off", "says", "said", "report", "reports",
    "could", "would", "should", "may", "might", "can", "just", "now", "here", "there",
    "also", "but", "or", "not", "all", "his", "her", "their", "they", "we", "you", "our",
    "car", "cars", "vehicle", "vehicles", "auto", "news", "model", "models", "year",
}

TOKEN_RE = re.compile(r"[a-zA-Zа-яА-Я0-9][a-zA-Zа-яА-Я0-9\-\.]*")


def normalize_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for raw in TOKEN_RE.findall(text.lower()):
        token = raw.strip("-.")
        if not token:
            continue
        if token in STOPWORDS:
            continue
        if token.isdigit():
            tokens.add(token)
            continue
        if len(token) < 3:
            continue
        tokens.add(token)
    return tokens


def similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    union = len(a | b)
    jaccard = inter / union
    containment = inter / min(len(a), len(b))
    return 0.5 * jaccard + 0.5 * containment


def cluster(settings: Settings) -> dict:
    counters = {"processed": 0, "new_stories": 0, "merged": 0}
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=settings.cluster_window_hours)).isoformat()
    with connect() as conn:
        articles = conn.execute(
            "SELECT a.*, s.region AS source_region, s.weight AS source_weight FROM articles a "
            "JOIN sources s ON s.id = a.source_id "
            "WHERE a.status = 'extracted' AND a.id NOT IN (SELECT article_id FROM story_articles) "
            "ORDER BY a.published_at DESC"
        ).fetchall()
        stories = conn.execute(
            "SELECT * FROM stories WHERE created_at >= ? ORDER BY created_at DESC", (cutoff,)
        ).fetchall()
        story_tokens = {int(s["id"]): set(s["title_key"].split()) for s in stories}

    for article in articles:
        counters["processed"] += 1
        tokens = normalize_tokens(article["title"] or "")
        if len(tokens) < 2:
            continue
        best_id = None
        best_score = 0.0
        for story in stories:
            score = similarity(tokens, story_tokens.get(int(story["id"]), set()))
            if score > best_score:
                best_score = score
                best_id = int(story["id"])
        if best_id is not None and best_score >= settings.cluster_threshold:
            _attach(best_id, article)
            counters["merged"] += 1
            continue
        story_id = _create_story(article, tokens)
        stories = list(stories) + [
            {
                "id": story_id,
                "title_key": " ".join(sorted(tokens)),
                "created_at": now(),
                "primary_article_id": article["id"],
                "region": article["source_region"],
                "article_count": 1,
                "status": "new",
                "score": None,
                "score_reason": None,
                "headline_ru": None,
                "topic": None,
            }
        ]
        story_tokens[story_id] = tokens
        counters["new_stories"] += 1
    return counters


def _create_story(article, tokens: set[str]) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO stories (primary_article_id, title_key, region, article_count, status, created_at) "
            "VALUES (?, ?, ?, 1, 'new', ?)",
            (article["id"], " ".join(sorted(tokens)), article["source_region"], now()),
        )
        story_id = int(cur.lastrowid)
        conn.execute(
            "INSERT OR IGNORE INTO story_articles (story_id, article_id) VALUES (?, ?)",
            (story_id, article["id"]),
        )
    return story_id


def _attach(story_id: int, article) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO story_articles (story_id, article_id) VALUES (?, ?)",
            (story_id, article["id"]),
        )
        conn.execute(
            "UPDATE stories SET article_count = (SELECT COUNT(*) FROM story_articles WHERE story_id = ?) WHERE id = ?",
            (story_id, story_id),
        )
