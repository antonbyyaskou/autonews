from __future__ import annotations

import html
import json
import re
from pathlib import Path

from ..config import MEDIA_DIR, Settings, load_style
from ..db import connect, now
from ..llm import LLMClient, LLMError
from ..media import choose as choose_media

NUM_RE = re.compile(r"(?<![\w.,])(\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)(?![\w])")
UNIT_HINTS = (
    "км", "кВт", "квт", "л.с", "лс", "сек", "мин", "%", "мм", "см", "кг", "нм", "вт",
    "вольт", "ампер", "дюйм", "млн", "млрд", "тыс", "$", "€", "₽", "руб", "доллар", "евро",
    "km", "kw", "hp", "mph", "sec", "mm", "kg", "nm", "kwh", "в", "ач", "ч", "л", "год",
)
EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\u2B00-\u2BFF\uFE0F]"
)

SYSTEM_RULES = """Правила:
1. Пиши по-русски, нейтральным информационным тоном, без восторгов и восклицаний.
2. Первая строка — короткий цепляющий заголовок без точки в конце.
3. Далее 2-4 факта: что это, ключевые характеристики, сроки и рынок.
4. Объём всего поста 300-500 символов.
5. Каждое число (мощность, запас хода, цена, разгон, размеры) обязано быть в исходном тексте.
   Если числа нет в источнике — не пиши его.
6. Не добавляй свои оценки, прогнозы и неподтверждённые слухи.
7. Без эмодзи, без markdown, без ссылок внутри текста.
8. Не пиши строку "Источник" и хештеги — они добавляются автоматически.
9. Сохраняй осторожность источника: если там "reportedly", ", по сообщениям, ",
   "according to reports", "слухи" — пиши "по данным источников" или убери факт.
   Не превращай неподтверждённое в утверждение.

Верни строго JSON:
{"post": "текст поста", "headline_ru": "заголовок до 90 символов",
 "hashtags": ["#тег", "#тег"], "numbers": [{"value": "как в посте", "quote": "точная цитата из источника"}]}"""


def parse_number(raw: str) -> float | None:
    s = raw.replace(" ", "").replace("\u00a0", "").replace("\u202f", "")
    if not s:
        return None
    try:
        if "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        elif "," in s:
            parts = s.split(",")
            if len(parts[-1]) == 3 and 1 <= len(parts[0]) <= 3:
                s = s.replace(",", "")
            else:
                s = s.replace(",", ".")
        elif "." in s:
            parts = s.split(".")
            if len(parts[-1]) == 3 and 1 <= len(parts[0]) <= 3 and len(parts) == 2:
                s = s.replace(".", "")
        return float(s)
    except ValueError:
        return None


def numbers_in(text: str) -> list[tuple[str, float]]:
    found: list[tuple[str, float]] = []
    for match in NUM_RE.finditer(text or ""):
        raw = match.group(1)
        value = parse_number(raw)
        if value is None:
            continue
        found.append((raw, value))
    return found


def _is_spec(post: str, match_start: int, raw: str, value: float) -> bool:
    if value >= 100 or any(ch in raw for ch in ",."):
        return True
    tail = post[match_start + len(raw) : match_start + len(raw) + 12].lower()
    return any(unit in tail for unit in UNIT_HINTS)


def attest(post: str, source_text: str) -> dict:
    source_values = [value for _, value in numbers_in(source_text)]
    missing: list[str] = []
    checked = 0
    for match in NUM_RE.finditer(post):
        raw = match.group(1)
        value = parse_number(raw)
        if value is None or not _is_spec(post, match.start(1), raw, value):
            continue
        checked += 1
        if not any(abs(value - candidate) <= max(1e-6, abs(value) * 1e-6) for candidate in source_values):
            missing.append(raw)
    return {"checked": checked, "missing": missing, "ok": not missing}


def _context(conn, story) -> tuple[str, list[str], list[str]]:
    rows = conn.execute(
        "SELECT a.title, a.body, a.summary, a.published_at, a.media_urls, s.name FROM story_articles sa "
        "JOIN articles a ON a.id = sa.article_id JOIN sources s ON s.id = a.source_id "
        "WHERE sa.story_id = ? ORDER BY a.published_at DESC",
        (story["id"],),
    ).fetchall()
    parts: list[str] = []
    sources: list[str] = []
    media: list[str] = []
    for row in rows:
        text = (row["body"] or row["summary"] or "").strip()
        parts.append(f"{row['title']}\n{text}")
        if row["name"] not in sources:
            sources.append(row["name"])
        for url in json.loads(row["media_urls"] or "[]"):
            if url not in media:
                media.append(url)
    return "\n\n".join(parts)[:9000], sources, media


ANGLICISM_RE = [
    (re.compile(r"\breportedly\b", re.I), ", по сообщениям, "),
    (re.compile(r"\baccording to reports\b", re.I), ", по сообщениям, "),
    (re.compile(r"\bsources say\b", re.I), ", по сообщениям, "),
    (re.compile(r"\breports suggest\b", re.I), ", по сообщениям, "),
]


def normalize_post(text: str) -> str:
    text = text or ""
    for pattern, replacement in ANGLICISM_RE:
        text = pattern.sub(replacement, text)
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r",\s*,", ",", text)
    text = EMOJI_RE.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip().strip('"').strip()


def normalize_hashtags(value) -> list[str]:
    if isinstance(value, str):
        items = re.split(r"[\s,]+", value)
    else:
        items = list(value or [])
    tags: list[str] = []
    for item in items:
        raw = str(item).strip().lstrip("#").lower()
        words = [w for w in re.split(r"[\s\-_]+", raw) if w]
        tag = "_".join(words)
        tag = re.sub(r"[^0-9a-zа-яё_]", "", tag).strip("_")
        if not tag or len(tag) > 28 or tag.isdigit():
            continue
        if f"#{tag}" not in tags:
            tags.append(f"#{tag}")
    return tags[:4]


def render_post(body: str, hashtags: str, sources: list[str], as_html: bool = True) -> str:
    tags = hashtags or ""
    source = ", ".join(sources[:2])
    if as_html:
        parts = [html.escape(body.strip())]
        if source:
            parts.append(f"<i>Источник: {html.escape(source)}</i>")
        if tags:
            parts.append(html.escape(tags))
        return "\n\n".join(parts)
    parts = [body.strip()]
    if source:
        parts.append(f"Источник: {source}")
    if tags:
        parts.append(tags)
    return "\n\n".join(parts)


def draft_candidates(settings: Settings, limit: int | None = None) -> dict:
    limit = limit or settings.max_drafts_per_run
    client = LLMClient(settings)
    style = load_style()
    counters = {"processed": 0, "drafted": 0, "rejected": 0, "failed": 0, "no_media": 0}
    errors: list[str] = []
    with connect() as conn:
        stories = conn.execute(
            "SELECT * FROM stories WHERE status = 'scored' AND id NOT IN "
            "(SELECT story_id FROM candidates) ORDER BY score DESC LIMIT ?",
            (limit,),
        ).fetchall()
    for story in stories:
        counters["processed"] += 1
        with connect() as conn:
            context, sources, media_urls = _context(conn, story)
        if len(context) < 400:
            counters["rejected"] += 1
            _set_story(story["id"], "rejected")
            continue
        retry_note: str | None = None
        result = None
        report = {"ok": False, "missing": [], "checked": 0}
        for attempt in range(3):
            try:
                result = _generate(client, settings, style, story, context, retry_note=retry_note)
            except (LLMError, ValueError) as exc:
                message = str(exc)
                if "outside" in message:
                    retry_note = (
                        "Предыдущий текст неверной длины. Сократи пост примерно до 420 символов, "
                        "оставив заголовок и 2-3 главных факта. Верни тот же JSON."
                    )
                else:
                    retry_note = f"Предыдущий ответ не принят: {message}. Верни корректный JSON по правилам."
                result = None
                if attempt == 2:
                    counters["failed"] += 1
                    errors.append(f"story {story['id']}: {exc}")
                continue
            report = attest(result["post"], context)
            if report["ok"]:
                break
            retry_note = (
                "Предыдущий вариант отклонён: следующие числа отсутствуют в исходном тексте: "
                + ", ".join(report["missing"])
                + ". Убери их или замени только на числа, которые есть в тексте."
            )
        if result is None:
            _set_story(story["id"], "failed")
            continue
        if not report["ok"]:
            counters["rejected"] += 1
            errors.append(f"story {story['id']}: unattested numbers {report['missing']}")
            _set_story(story["id"], "rejected")
            continue

        with connect() as conn:
            cur = conn.execute(
                "INSERT INTO candidates (story_id, headline_ru, body_ru, hashtags, attestation, model, token_usage, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'drafted', ?)",
                (
                    story["id"],
                    result["headline"],
                    result["post"],
                    " ".join(result["hashtags"]),
                    json.dumps(report, ensure_ascii=False),
                    result["model"],
                    json.dumps(result["usage"]),
                    now(),
                ),
            )
            candidate_id = int(cur.lastrowid)

        path, media_url, media_error = choose_media(media_urls, settings, MEDIA_DIR / f"candidate_{candidate_id}")
        kind = None
        if path:
            kind = "video" if path.suffix in (".mp4", ".webm") else "image"
        else:
            counters["no_media"] += 1
        with connect() as conn:
            conn.execute(
                "UPDATE candidates SET media_path = ?, media_kind = ?, media_source_url = ? WHERE id = ?",
                (str(path) if path else None, kind, media_url, candidate_id),
            )
        _set_story(story["id"], "drafted")
        counters["drafted"] += 1
    counters["errors"] = errors
    return counters


def _generate(
    client: LLMClient, settings: Settings, style: str, story, context: str, retry_note: str | None = None
):
    user = f"{style}\n\nИсходная новость:\n\n{context}"
    if retry_note:
        user += f"\n\n{retry_note}"
    messages = [
        {"role": "system", "content": SYSTEM_RULES},
        {"role": "user", "content": user},
    ]
    data, completion = client.complete_json(
        messages, model=settings.model_draft, role="draft", max_tokens=1400, temperature=0.4
    )
    post = normalize_post(str(data.get("post") or ""))
    headline = normalize_post(str(data.get("headline_ru") or story["headline_ru"] or ""))[:120]
    if not post:
        raise LLMError("empty post")
    if len(post) > settings.post_max_chars:
        post = shrink(post, settings.post_max_chars)
    if not (settings.post_min_chars <= len(post) <= settings.post_max_chars):
        raise LLMError(f"length {len(post)} outside {settings.post_min_chars}-{settings.post_max_chars}")
    return {
        "post": post,
        "headline": headline,
        "hashtags": normalize_hashtags(data.get("hashtags")),
        "model": completion.model,
        "usage": completion.as_usage(),
    }


def shrink(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for mark in (". ", "! ", "? ", "\n"):
        index = cut.rfind(mark)
        if index >= 120:
            return cut[: index + 1].strip()
    index = cut.rfind(" ")
    return (cut[:index] if index > 0 else cut).strip()


def _set_story(story_id: int, status: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE stories SET status = ? WHERE id = ?", (status, story_id))
