from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import httpx

from .config import Settings

IMAGE_EXT = {"jpg": "image", "jpeg": "image", "png": "image", "webp": "image"}
VIDEO_EXT = {"mp4": "video", "webm": "video"}


def kind_from_url(url: str) -> str | None:
    ext = urlparse(url).path.rsplit(".", 1)[-1].lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    return None


def _sniff(head: bytes) -> str | None:
    if head[:2] == b"\xff\xd8":
        return "image"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "image"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image"
    if head[4:8] == b"ftyp":
        return "video"
    if head[:4] == b"\x1aE\xdf\xa3":
        return "video"
    return None


def download(url: str, settings: Settings, dest_stem: Path) -> tuple[Path | None, str | None]:
    try:
        with httpx.Client(
            timeout=httpx.Timeout(30.0, connect=8.0),
            headers={"User-Agent": settings.fetch_user_agent},
            follow_redirects=True,
        ) as client:
            with client.stream("GET", url) as resp:
                if resp.status_code >= 400:
                    return None, f"HTTP {resp.status_code}"
                head = b""
                chunks: list[bytes] = []
                total = 0
                for chunk in resp.iter_bytes(65536):
                    if not head:
                        head = chunk[:16]
                    total += len(chunk)
                    if total > settings.media_max_bytes:
                        return None, "too large"
                    chunks.append(chunk)
        payload = b"".join(chunks)
        kind = _sniff(payload[:16])
        if not kind:
            return None, "unsupported media"
        ext = "jpg" if kind == "image" and payload[:2] == b"\xff\xd8" else None
        if kind == "image":
            ext = "png" if payload[:8] == b"\x89PNG\r\n\x1a\n" else ("webp" if payload[:4] == b"RIFF" else "jpg")
        else:
            ext = "mp4" if payload[4:8] == b"ftyp" else "webm"
        dest = dest_stem.with_suffix("." + ext)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload)
        return dest, None
    except Exception as exc:
        return None, str(exc)[:160]


def choose(media_urls: list[str], settings: Settings, dest_stem: Path) -> tuple[Path | None, str | None, str | None]:
    videos = [u for u in media_urls if kind_from_url(u) == "video"]
    images = [u for u in media_urls if kind_from_url(u) == "image"]
    ordered = videos[:3] + images[:6]
    if not ordered:
        ordered = media_urls[:6]
    for url in ordered:
        path, error = download(url, settings, dest_stem)
        if path:
            return path, url, None
    return None, None, "no media downloaded"
