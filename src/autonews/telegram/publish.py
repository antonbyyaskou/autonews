from __future__ import annotations

from pathlib import Path

from telegram import Bot
from telegram.constants import ParseMode

from ..config import Settings
from ..db import connect, now
from ..pipeline.summarize import render_post


def candidate_sources(candidate_id: int) -> list[str]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT s.name FROM candidates c "
            "JOIN story_articles sa ON sa.story_id = c.story_id "
            "JOIN articles a ON a.id = sa.article_id JOIN sources s ON s.id = a.source_id "
            "WHERE c.id = ?",
            (candidate_id,),
        ).fetchall()
    return [row["name"] for row in rows]


def candidate_urls(candidate_id: int) -> list[str]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT a.url FROM candidates c "
            "JOIN story_articles sa ON sa.story_id = c.story_id "
            "JOIN articles a ON a.id = sa.article_id WHERE c.id = ?",
            (candidate_id,),
        ).fetchall()
    return [row["url"] for row in rows]


def caption_for(row) -> str:
    return render_post(row["body_ru"], row["hashtags"], candidate_sources(row["id"]), as_html=True)


def already_published(candidate_id: int) -> bool:
    with connect() as conn:
        row = conn.execute("SELECT 1 FROM publish_log WHERE candidate_id = ? LIMIT 1", (candidate_id,)).fetchone()
    return row is not None


async def publish(bot: Bot, settings: Settings, candidate_id: int) -> int:
    if already_published(candidate_id):
        raise RuntimeError("candidate already published")
    with connect() as conn:
        row = conn.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,)).fetchone()
    if not row:
        raise RuntimeError("candidate not found")
    channel = settings.telegram_channel_id
    if not channel:
        raise RuntimeError("TELEGRAM_CHANNEL_ID is not set")
    caption = caption_for(row)
    path = Path(row["media_path"]) if row["media_path"] else None

    if path and path.exists() and len(caption) <= 1024:
        with path.open("rb") as handle:
            if row["media_kind"] == "video":
                message = await bot.send_video(
                    chat_id=channel, video=handle, caption=caption, parse_mode=ParseMode.HTML
                )
            else:
                message = await bot.send_photo(
                    chat_id=channel, photo=handle, caption=caption, parse_mode=ParseMode.HTML
                )
    else:
        text = caption
        if len(text) <= 4096:
            message = await bot.send_message(chat_id=channel, text=text, parse_mode=ParseMode.HTML)
        else:
            message = await bot.send_message(chat_id=channel, text=text[:4000], parse_mode=ParseMode.HTML)

    with connect() as conn:
        conn.execute(
            "INSERT INTO publish_log (candidate_id, channel_id, message_id, published_at) VALUES (?, ?, ?, ?)",
            (candidate_id, str(channel), message.message_id, now()),
        )
        conn.execute("UPDATE candidates SET status = 'published' WHERE id = ?", (candidate_id,))
        conn.execute(
            "UPDATE stories SET status = 'published' WHERE id = (SELECT story_id FROM candidates WHERE id = ?)",
            (candidate_id,),
        )
    return message.message_id
