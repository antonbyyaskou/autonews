from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from ..config import Settings, load_settings
from ..db import connect, now
from ..digest import candidate_at, create_digest, digest_text, latest_digest, split_message
from ..pipeline import run_pipeline
from ..pipeline.summarize import render_post
from .publish import candidate_sources, candidate_urls, publish


def _allowed(settings: Settings, update: Update) -> bool:
    if not settings.telegram_operator_id:
        return True
    user = update.effective_user
    return bool(user and user.id == settings.telegram_operator_id)


async def _guard(update: Update, settings: Settings) -> bool:
    if _allowed(settings, update):
        return True
    if update.effective_message:
        await update.effective_message.reply_text("Нет доступа.")
    return False


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    if not await _guard(update, settings):
        return
    await update.message.reply_text(
        "Autonews готов.\n\n"
        "/run — собрать новости\n"
        "/list — последний список\n"
        "/show N — черновик\n"
        "/post N — опубликовать\n"
        "/skip N — отклонить\n"
        "/edit N текст — заменить текст\n"
        "/status — состояние\n"
        "/sources — источники"
    )


async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    if not await _guard(update, settings):
        return
    await update.message.reply_text("Собираю новости. Это займёт несколько минут.")
    try:
        results = await asyncio.to_thread(run_pipeline, settings)
    except Exception as exc:
        await update.message.reply_text(f"Ошибка: {exc}")
        return
    summary = " · ".join(
        f"{stage}: " + ", ".join(f"{k}={v}" for k, v in data.items() if isinstance(v, int) and v)
        for stage, data in results.items()
        if any(isinstance(v, int) and v for v in data.values())
    )
    await update.message.reply_text(f"Готово.\n{summary}"[:4000])
    await _send_digest(context.bot, update.effective_chat.id, settings)


async def _send_digest(bot: Bot, chat_id: int, settings: Settings) -> None:
    created = create_digest(limit=25)
    if not created:
        await bot.send_message(chat_id=chat_id, text="Новых кандидатов нет.")
        return
    digest_id, text = created
    parts = split_message(text)
    with connect() as conn:
        for part in parts:
            message = await bot.send_message(chat_id=chat_id, text=part)
        conn.execute("UPDATE digests SET message_id = ? WHERE id = ?", (message.message_id, digest_id))


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    if not await _guard(update, settings):
        return
    digest_id = latest_digest()
    if digest_id is None:
        await update.message.reply_text("Список пуст. Отправьте /run.")
        return
    for part in split_message(digest_text(digest_id)):
        await update.message.reply_text(part)


async def cmd_show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    if not await _guard(update, settings):
        return
    position = _arg_int(context)
    if position is None:
        await update.message.reply_text("Формат: /show 3")
        return
    row = candidate_at(latest_digest() or 0, position)
    if not row:
        await update.message.reply_text("Нет такого номера.")
        return
    text = render_post(row["body_ru"], row["hashtags"], candidate_sources(row["id"]), as_html=False)
    urls = candidate_urls(row["id"])
    footer = "\n\n" + "\n".join(urls[:3]) if urls else ""
    path = Path(row["media_path"]) if row["media_path"] else None
    if path and path.exists():
        with path.open("rb") as handle:
            if row["media_kind"] == "video":
                await update.message.reply_video(video=handle, caption=text[:1024])
            else:
                await update.message.reply_photo(photo=handle, caption=text[:1024])
        if len(text) > 1024 or footer:
            await update.message.reply_text((text[1024:] if len(text) > 1024 else "") + footer)
    else:
        for part in split_message(text + footer, limit=4000):
            await update.message.reply_text(part)


async def cmd_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    if not await _guard(update, settings):
        return
    if not context.args or not context.args[0].isdigit() or len(context.args) < 2:
        await update.message.reply_text("Формат: /edit 3 новый текст поста")
        return
    position = int(context.args[0])
    row = candidate_at(latest_digest() or 0, position)
    if not row:
        await update.message.reply_text("Нет такого номера.")
        return
    new_body = " ".join(context.args[1:]).strip()
    if len(new_body) < 40:
        await update.message.reply_text("Слишком короткий текст.")
        return
    with connect() as conn:
        conn.execute("UPDATE candidates SET body_ru = ?, status = 'edited' WHERE id = ?", (new_body, row["id"]))
    await update.message.reply_text(f"Кандидат #{position} обновлён.")


async def cmd_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    if not await _guard(update, settings):
        return
    position = _arg_int(context)
    if position is None:
        await update.message.reply_text("Формат: /skip 3")
        return
    row = candidate_at(latest_digest() or 0, position)
    if not row:
        await update.message.reply_text("Нет такого номера.")
        return
    with connect() as conn:
        conn.execute("UPDATE candidates SET status = 'skipped' WHERE id = ?", (row["id"],))
    await update.message.reply_text(f"Кандидат #{position} отклонён.")


async def cmd_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    if not await _guard(update, settings):
        return
    position = _arg_int(context)
    if position is None:
        await update.message.reply_text("Формат: /post 3")
        return
    row = candidate_at(latest_digest() or 0, position)
    if not row:
        await update.message.reply_text("Нет такого номера.")
        return
    if row["status"] == "published":
        await update.message.reply_text("Этот пост уже опубликован.")
        return
    token = uuid.uuid4().hex[:16]
    expires = (datetime.now(timezone.utc) + timedelta(seconds=settings.confirm_ttl_seconds)).isoformat(
        timespec="seconds"
    )
    with connect() as conn:
        conn.execute("DELETE FROM pending WHERE candidate_id = ?", (row["id"],))
        conn.execute(
            "INSERT INTO pending (token, candidate_id, expires_at) VALUES (?, ?, ?)",
            (token, row["id"], expires),
        )
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Опубликовать в канал", callback_data=f"pub:{token}")],
            [InlineKeyboardButton("Отмена", callback_data=f"cancel:{token}")],
        ]
    )
    await update.message.reply_text(
        f"Публикую кандидата #{position} в {settings.telegram_channel_id}.\nПодтвердите в течение "
        f"{settings.confirm_ttl_seconds // 60} минут.",
        reply_markup=keyboard,
    )


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    query = update.callback_query
    if not _allowed(settings, update):
        await query.answer("Нет доступа")
        return
    await query.answer()
    data = query.data or ""
    action, _, token = data.partition(":")
    with connect() as conn:
        pending = conn.execute("SELECT * FROM pending WHERE token = ?", (token,)).fetchone()
    if not pending:
        await query.edit_message_text("Подтверждение истекло или уже использовано.")
        return
    if action == "cancel":
        with connect() as conn:
            conn.execute("DELETE FROM pending WHERE token = ?", (token,))
        await query.edit_message_text("Отменено.")
        return
    expires = pending["expires_at"]
    if datetime.fromisoformat(expires) < datetime.now(timezone.utc):
        with connect() as conn:
            conn.execute("DELETE FROM pending WHERE token = ?", (token,))
        await query.edit_message_text("Подтверждение истекло.")
        return
    with connect() as conn:
        conn.execute("DELETE FROM pending WHERE token = ?", (token,))
    try:
        message_id = await publish(context.bot, settings, int(pending["candidate_id"]))
    except Exception as exc:
        await query.edit_message_text(f"Ошибка публикации: {exc}")
        return
    await query.edit_message_text(f"Опубликовано. message_id={message_id}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    if not await _guard(update, settings):
        return
    with connect() as conn:
        articles = conn.execute("SELECT COUNT(*) AS n FROM articles").fetchone()["n"]
        stories = conn.execute("SELECT COUNT(*) AS n FROM stories").fetchone()["n"]
        drafts = conn.execute("SELECT COUNT(*) AS n FROM candidates WHERE status = 'drafted'").fetchone()["n"]
        published = conn.execute("SELECT COUNT(*) AS n FROM publish_log").fetchone()["n"]
        usage = conn.execute(
            "SELECT COUNT(*) AS calls, COALESCE(SUM(allowance),0) AS allowance FROM llm_usage "
            "WHERE created_at >= datetime('now','-30 day')"
        ).fetchone()
        last = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        disabled = conn.execute("SELECT COUNT(*) AS n FROM sources WHERE enabled = 0").fetchone()["n"]
    lines = [
        f"Статьи: {articles}",
        f"Сюжеты: {stories}",
        f"Черновики: {drafts}",
        f"Опубликовано: {published}",
        f"Источники отключены: {disabled}",
        f"LLM за 30 дней: {usage['calls']} вызовов, allowance ${usage['allowance']:.4f}",
    ]
    if last:
        lines.append(f"Последний запуск: {last['stage']} в {last['started_at']} → {last['finished_at'] or 'идёт'}")
    await update.message.reply_text("\n".join(lines))


async def cmd_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data["settings"]
    if not await _guard(update, settings):
        return
    with connect() as conn:
        rows = conn.execute(
            "SELECT name, region, enabled, last_status, consecutive_failures FROM sources ORDER BY enabled DESC, name"
        ).fetchall()
    lines = [f"{'ON ' if r['enabled'] else 'OFF'} {r['name']} [{r['region']}] {r['last_status'] or '—'}" for r in rows]
    await update.message.reply_text("\n".join(lines)[:4000])


def _arg_int(context: ContextTypes.DEFAULT_TYPE) -> int | None:
    if not context.args:
        return None
    try:
        return int(context.args[0])
    except ValueError:
        return None


def main() -> None:
    settings = load_settings()
    if not settings.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set in .env")
    app = Application.builder().token(settings.telegram_bot_token).build()
    app.bot_data["settings"] = settings
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("run", cmd_run))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("show", cmd_show))
    app.add_handler(CommandHandler("edit", cmd_edit))
    app.add_handler(CommandHandler("skip", cmd_skip))
    app.add_handler(CommandHandler("post", cmd_post))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("sources", cmd_sources))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.run_polling(allowed_updates=Update.ALL_TYPES)
