from __future__ import annotations

import asyncio

import pytest

import autonews.db as db
from autonews.config import load_settings
from autonews.telegram import bot as botmod

OPERATOR = 6336529005


class FakeSent:
    message_id = 999


class FakeMessage:
    def __init__(self):
        self.texts: list[str] = []
        self.photos: list[str] = []
        self.videos: list[str] = []

    async def reply_text(self, text, **kwargs):
        self.texts.append(text)
        return FakeSent()

    async def reply_photo(self, photo=None, caption=None, **kwargs):
        self.photos.append(caption or "")
        return FakeSent()

    async def reply_video(self, video=None, caption=None, **kwargs):
        self.videos.append(caption or "")
        return FakeSent()


class FakeUser:
    def __init__(self, uid: int):
        self.id = uid


class FakeChat:
    id = 1


class FakeQuery:
    def __init__(self, data: str):
        self.data = data
        self.edits: list[str] = []

    async def answer(self):
        return None

    async def edit_message_text(self, text, **kwargs):
        self.edits.append(text)


class FakeUpdate:
    def __init__(self, user_id: int = OPERATOR, callback: FakeQuery | None = None):
        self.effective_user = FakeUser(user_id)
        self.effective_chat = FakeChat()
        self.message = FakeMessage()
        self.effective_message = self.message
        self.callback_query = callback


class FakeBot:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append(("message", text))
        return FakeSent()

    async def send_photo(self, chat_id, photo=None, caption=None, **kwargs):
        self.sent.append(("photo", caption or ""))
        return FakeSent()

    async def send_video(self, chat_id, video=None, caption=None, **kwargs):
        self.sent.append(("video", caption or ""))
        return FakeSent()


class FakeApplication:
    def __init__(self, settings):
        self.bot_data = {"settings": settings}


class FakeContext:
    def __init__(self, bot: FakeBot, settings, args: list[str] | None = None):
        self.bot = bot
        self.args = args or []
        self.application = FakeApplication(settings)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db.DB_PATH = tmp_path / "test.db"
    db.init_db()
    image = tmp_path / "img.jpg"
    image.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO sources (name,url,region,lang,weight,enabled) VALUES ('Autoblog','http://feed','us','en',1,1)"
        )
        conn.execute(
            "INSERT INTO articles (source_id,url,canonical_url,title,summary,body,lang,published_at,"
            "fetched_at,content_hash,media_urls,status) VALUES "
            "(1,'http://a','http://a','Audi Q9','s','512 segments 0.1 mm','en','2026-11-01','2026-11-01','h1','[]','extracted')"
        )
        conn.execute(
            "INSERT INTO stories (primary_article_id,title_key,region,article_count,score,score_reason,"
            "headline_ru,topic,status,created_at) VALUES "
            "(1,'audi q9','us',1,86,'r','Audi Q9','new_model','drafted','2026-11-01')"
        )
        conn.execute("INSERT INTO story_articles (story_id,article_id) VALUES (1,1)")
        for title, body in (
            ("Audi Q9: изогнутые OLED", "Audi Q9 стал первой моделью с изогнутыми OLED-фонарями. " * 4),
            ("BYD Sealion 08: 1000 км", "BYD представила Sealion 08 с запасом хода 1000 км по CLTC. " * 4),
        ):
            conn.execute(
                "INSERT INTO candidates (story_id,headline_ru,body_ru,hashtags,media_path,media_kind,"
                "media_source_url,attestation,model,token_usage,status,created_at) VALUES "
                "(1,?,?,'#audi #q9',?,'image','http://img','{\"ok\":true}','glm-5.3-flash','{}','drafted','2026-11-01')",
                (title, body, str(image)),
            )
    settings = load_settings()
    settings.telegram_operator_id = OPERATOR
    settings.telegram_channel_id = "@autonews_test"
    bot = FakeBot()
    return settings, bot, FakeContext(bot, settings)


def test_start_and_access_guard(env):
    settings, bot, context = env
    update = FakeUpdate()
    asyncio.run(botmod.cmd_start(update, context))
    assert "Autonews готов" in update.message.texts[-1]

    denied = FakeUpdate(user_id=42)
    asyncio.run(botmod.cmd_start(denied, context))
    assert denied.message.texts[-1] == "Нет доступа."


def test_run_creates_digest(env, monkeypatch):
    settings, bot, context = env
    monkeypatch.setattr(
        botmod, "run_pipeline", lambda settings: {"ingest": {"new_articles": 5, "errors": []}}
    )
    update = FakeUpdate()
    asyncio.run(botmod.cmd_run(update, context))
    assert "Собираю новости" in update.message.texts[0]
    assert any(kind == "message" and "Новые кандидаты" in text for kind, text in bot.sent)
    digest = [text for kind, text in bot.sent if "Новые кандидаты" in text][0]
    assert "1. [86]" in digest and "2. [86]" in digest


def test_list_and_show(env, monkeypatch):
    settings, bot, context = env
    monkeypatch.setattr(botmod, "run_pipeline", lambda settings: {"ingest": {}})
    asyncio.run(botmod.cmd_run(FakeUpdate(), context))

    listing = FakeUpdate()
    asyncio.run(botmod.cmd_list(listing, context))
    assert any("Новые кандидаты" in text for text in listing.message.texts)

    shown = FakeUpdate()
    asyncio.run(botmod.cmd_show(shown, FakeContext(bot, settings, ["1"])))
    assert shown.message.photos and "Audi Q9" in shown.message.photos[0]

    missing = FakeUpdate()
    asyncio.run(botmod.cmd_show(missing, FakeContext(bot, settings, ["99"])))
    assert missing.message.texts[-1] == "Нет такого номера."


def test_edit_and_skip(env, monkeypatch):
    settings, bot, context = env
    monkeypatch.setattr(botmod, "run_pipeline", lambda settings: {"ingest": {}})
    asyncio.run(botmod.cmd_run(FakeUpdate(), context))

    update = FakeUpdate()
    asyncio.run(botmod.cmd_edit(update, FakeContext(bot, settings, ["2", "Полностью новый", "текст", "поста", "для", "проверки", "редактора"])))
    assert "обновлён" in update.message.texts[-1]
    with db.connect() as conn:
        body = conn.execute("SELECT body_ru FROM candidates WHERE id = 2").fetchone()["body_ru"]
    assert body == "Полностью новый текст поста для проверки редактора"

    skipped = FakeUpdate()
    asyncio.run(botmod.cmd_skip(skipped, FakeContext(bot, settings, ["2"])))
    assert "отклонён" in skipped.message.texts[-1]
    with db.connect() as conn:
        assert conn.execute("SELECT status FROM candidates WHERE id = 2").fetchone()["status"] == "skipped"


def test_post_confirm_publish(env, monkeypatch):
    settings, bot, context = env
    monkeypatch.setattr(botmod, "run_pipeline", lambda settings: {"ingest": {}})
    asyncio.run(botmod.cmd_run(FakeUpdate(), context))

    ask = FakeUpdate()
    asyncio.run(botmod.cmd_post(ask, FakeContext(bot, settings, ["1"])))
    assert "Подтвердите" in ask.message.texts[-1]
    with db.connect() as conn:
        token = conn.execute("SELECT token FROM pending").fetchone()["token"]

    query = FakeQuery(f"pub:{token}")
    confirm = FakeUpdate(callback=query)
    asyncio.run(botmod.on_callback(confirm, context))
    assert "Опубликовано. message_id=999" in query.edits[-1]
    assert any(kind == "photo" and "Audi Q9" in caption for kind, caption in bot.sent)
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM publish_log").fetchone()["n"] == 1
        assert conn.execute("SELECT status FROM candidates WHERE id = 1").fetchone()["status"] == "published"

    again = FakeUpdate()
    asyncio.run(botmod.cmd_post(again, FakeContext(bot, settings, ["1"])))
    assert "уже опубликован" in again.message.texts[-1]


def test_cancel_confirmation(env, monkeypatch):
    settings, bot, context = env
    monkeypatch.setattr(botmod, "run_pipeline", lambda settings: {"ingest": {}})
    asyncio.run(botmod.cmd_run(FakeUpdate(), context))

    ask = FakeUpdate()
    asyncio.run(botmod.cmd_post(ask, FakeContext(bot, settings, ["2"])))
    with db.connect() as conn:
        token = conn.execute("SELECT token FROM pending").fetchone()["token"]

    query = FakeQuery(f"cancel:{token}")
    asyncio.run(botmod.on_callback(FakeUpdate(callback=query), context))
    assert query.edits[-1] == "Отменено."
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM publish_log").fetchone()["n"] == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM pending").fetchone()["n"] == 0


def test_status_and_sources(env):
    settings, bot, context = env
    status = FakeUpdate()
    asyncio.run(botmod.cmd_status(status, context))
    text = status.message.texts[-1]
    assert "Статьи: 1" in text and "Черновики: 2" in text

    sources = FakeUpdate()
    asyncio.run(botmod.cmd_sources(sources, context))
    assert "Autoblog" in sources.message.texts[-1]
