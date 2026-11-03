from __future__ import annotations

import calendar
import hashlib
import json
from datetime import datetime, timezone

import feedparser
import httpx

from ..config import Settings, load_sources
from ..db import connect, now


def _iso(entry) -> str | None:
    for attr in ("published_parsed", "updated_parsed"):
        value = getattr(entry, attr, None)
        if value:
            return datetime.fromtimestamp(calendar.timegm(value), tz=timezone.utc).isoformat(timespec="seconds")
    return None


def _media(entry) -> list[str]:
    urls: list[str] = []
    for item in entry.get("media_content") or []:
        if isinstance(item, dict) and item.get("url"):
            urls.append(item["url"])
    for item in entry.get("media_thumbnail") or []:
        if isinstance(item, dict) and item.get("url"):
            urls.append(item["url"])
    for link in entry.get("links") or []:
        if link.get("rel") == "enclosure" and link.get("href"):
            urls.append(link["href"])
    for item in entry.get("enclosures") or []:
        if isinstance(item, dict) and item.get("href"):
            urls.append(item["href"])
    seen: list[str] = []
    for url in urls:
        if url not in seen:
            seen.append(url)
    return seen


def sync_sources() -> int:
    sources = load_sources()
    with connect() as conn:
        for src in sources:
            conn.execute(
                "INSERT INTO sources (name, url, region, lang, weight, enabled) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET url = excluded.url, region = excluded.region, "
                "lang = excluded.lang, weight = excluded.weight, enabled = excluded.enabled",
                (
                    src["name"],
                    src["url"],
                    src.get("region", "global"),
                    src.get("lang", "en"),
                    float(src.get("weight", 1.0)),
                    1 if src.get("enabled", True) else 0,
                ),
            )
        names = [src["name"] for src in sources]
        if names:
            placeholders = ",".join("?" for _ in names)
            conn.execute(
                f"UPDATE sources SET enabled = 0 WHERE name NOT IN ({placeholders})", names
            )
    return len(sources)


def ingest(settings: Settings, limit_per_feed: int = 40) -> dict:
    sync_sources()
    counters = {"feeds": 0, "ok": 0, "failed": 0, "new_articles": 0, "skipped": 0}
    errors: list[str] = []
    with connect() as conn:
        feeds = conn.execute("SELECT * FROM sources WHERE enabled = 1 ORDER BY weight DESC").fetchall()
    for feed in feeds:
        counters["feeds"] += 1
        try:
            with httpx.Client(
                timeout=settings.http_timeout,
                headers={"User-Agent": settings.fetch_user_agent},
                follow_redirects=True,
            ) as client:
                resp = client.get(feed["url"])
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)
            if parsed.bozo and not parsed.entries:
                raise ValueError(f"unparseable feed: {parsed.get('bozo_exception')}")
            added = _store_entries(feed, parsed.entries[:limit_per_feed])
            counters["new_articles"] += added
            counters["skipped"] += max(0, len(parsed.entries[:limit_per_feed]) - added)
            counters["ok"] += 1
            _mark_source(feed["id"], "ok", None)
        except Exception as exc:
            counters["failed"] += 1
            errors.append(f"{feed['name']}: {exc}")
            _mark_source(feed["id"], "failed", str(exc))
    counters["errors"] = errors
    return counters


def _store_entries(feed, entries) -> int:
    added = 0
    with connect() as conn:
        for entry in entries:
            url = (entry.get("link") or "").strip()
            title = (entry.get("title") or "").strip()
            if not url or not title:
                continue
            content_hash = hashlib.sha256(url.encode()).hexdigest()
            try:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO articles "
                    "(source_id, url, canonical_url, title, summary, lang, published_at, fetched_at, content_hash, media_urls) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        feed["id"],
                        url,
                        url,
                        title,
                        (entry.get("summary") or "").strip()[:2000],
                        feed["lang"],
                        _iso(entry),
                        now(),
                        content_hash,
                        json.dumps(_media(entry)),
                    ),
                )
                if cur.rowcount:
                    added += 1
            except Exception as exc:
                if "UNIQUE" not in str(exc):
                    raise
    return added


def _mark_source(source_id: int, status: str, error: str | None) -> None:
    with connect() as conn:
        if status == "ok":
            conn.execute(
                "UPDATE sources SET last_status = ?, last_checked_at = ?, consecutive_failures = 0 WHERE id = ?",
                (status, now(), source_id),
            )
        else:
            conn.execute(
                "UPDATE sources SET last_status = ?, last_checked_at = ?, consecutive_failures = consecutive_failures + 1 WHERE id = ?",
                (f"{status}: {error[:160]}" if error else status, now(), source_id),
            )
        row = conn.execute("SELECT consecutive_failures FROM sources WHERE id = ?", (source_id,)).fetchone()
        if row and row[0] >= 3:
            conn.execute("UPDATE sources SET enabled = 0 WHERE id = ?", (source_id,))
