from __future__ import annotations

import json
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup

from ..config import Settings
from ..db import connect


def extract(settings: Settings, limit: int | None = None) -> dict:
    limit = limit or settings.max_articles_per_extract
    counters = {"processed": 0, "ok": 0, "degraded": 0, "failed": 0}
    errors: list[str] = []
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM (SELECT a.*, ROW_NUMBER() OVER "
            "(PARTITION BY a.source_id ORDER BY a.published_at DESC) AS rn "
            "FROM articles a WHERE a.status = 'new') "
            "WHERE rn <= 6 ORDER BY published_at IS NULL, published_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    for row in rows:
        counters["processed"] += 1
        try:
            result = _fetch_and_extract(settings, row)
            with connect() as conn:
                conn.execute(
                    "UPDATE articles SET body = ?, title = ?, canonical_url = COALESCE(?, canonical_url), "
                    "published_at = COALESCE(?, published_at), media_urls = ?, status = ? WHERE id = ?",
                    (
                        result["body"],
                        result["title"],
                        result["canonical_url"],
                        result["published_at"],
                        json.dumps(result["media_urls"]),
                        result["status"],
                        row["id"],
                    ),
                )
            if result["status"] == "extracted":
                counters["ok"] += 1
            else:
                counters["degraded"] += 1
        except Exception as exc:
            counters["failed"] += 1
            errors.append(f"{row['url']}: {exc}")
            with connect() as conn:
                conn.execute(
                    "UPDATE articles SET body = COALESCE(body, summary), status = 'extracted' WHERE id = ?",
                    (row["id"],),
                )
    counters["errors"] = errors
    return counters


def _fetch_and_extract(settings: Settings, row) -> dict:
    with httpx.Client(
        timeout=settings.http_timeout,
        headers={"User-Agent": settings.fetch_user_agent},
        follow_redirects=True,
    ) as client:
        resp = client.get(row["url"])
    resp.raise_for_status()
    html = resp.text
    final_url = str(resp.url)

    body = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=True,
        favor_precision=True,
        url=final_url,
    ) or ""
    meta = trafilatura.extract_metadata(html, default_url=final_url)

    soup = BeautifulSoup(html, "html.parser")
    canonical = _canonical(soup, final_url)
    title = (getattr(meta, "title", None) or row["title"] or "").strip()
    published = getattr(meta, "date", None) or row["published_at"]
    media = _media_urls(soup, json.loads(row["media_urls"] or "[]"), final_url)

    body = body.strip()
    status = "extracted"
    if len(body) < 300:
        fallback = _clean_text(row["summary"] or "")
        if len(fallback) > len(body):
            body = fallback
        status = "extracted"
    if len(body) < 200:
        status = "degraded"
    return {
        "body": body,
        "title": title,
        "canonical_url": canonical,
        "published_at": published,
        "media_urls": media,
        "status": status,
    }


def _canonical(soup: BeautifulSoup, base: str) -> str:
    link = soup.find("link", rel=lambda v: v and "canonical" in v)
    if link and link.get("href"):
        return urljoin(base, link["href"])
    return base


def _media_urls(soup: BeautifulSoup, from_feed: list[str], base: str) -> list[str]:
    urls: list[str] = list(from_feed)
    for prop in ("og:image", "og:image:url", "twitter:image"):
        tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
        if tag and tag.get("content"):
            urls.append(tag["content"])
    for img in soup.find_all("img", limit=40):
        src = img.get("src") or img.get("data-src") or img.get("data-original")
        if not src:
            continue
        width = str(img.get("width") or "")
        if width.isdigit() and int(width) < 500:
            continue
        if any(token in src.lower() for token in ("logo", "icon", "avatar", "sprite", "placeholder")):
            continue
        urls.append(src)
    resolved: list[str] = []
    for url in urls:
        absolute = urljoin(base, url)
        if urlparse(absolute).scheme not in ("http", "https"):
            continue
        if absolute not in resolved:
            resolved.append(absolute)
    return resolved[:12]


def _clean_text(html: str) -> str:
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
