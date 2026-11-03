from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from ..config import Settings
from ..db import connect
from ..llm import LLMClient, LLMError

SYSTEM = """Ты редактор русскоязычного Telegram-канала об автомобилях.
Твоя задача — оценить новость для канала, где акцент на новых технологиях и новых моделях.

Оценка 0-100:
- 80-100: премьера новой модели, принципиально новая технология, важный ценовой или рыночный факт
- 55-79: обновление модели, заметная технология, значимая новость индустрии
- 35-54: второстепенно, но по теме
- 0-34: не по теме (автоспорт, автострахование, криминал, общие советы, старые авто, лайфстайл)

Штрафуй: дайджесты, списки, мнения без фактов, перепечатки без новости, слухи без источника.

Верни строго JSON без пояснений:
{"score": 0-100, "relevant": true|false, "topic": "new_model|technology|market|business|other",
 "region": "us|china|europe|global",
 "reason": "до 120 символов, почему такая оценка",
 "headline_ru": "заголовок по-русски до 90 символов"}"""


def _story_context(conn, story) -> tuple[str, list[str], str]:
    rows = conn.execute(
        "SELECT a.title, a.summary, a.body, a.url, s.name, s.region FROM story_articles sa "
        "JOIN articles a ON a.id = sa.article_id JOIN sources s ON s.id = a.source_id "
        "WHERE sa.story_id = ? ORDER BY a.published_at DESC",
        (story["id"],),
    ).fetchall()
    parts: list[str] = []
    urls: list[str] = []
    regions: list[str] = []
    for row in rows:
        text = (row["body"] or row["summary"] or "").strip()
        parts.append(f"[{row['name']}] {row['title']}\n{text[:1200]}")
        urls.append(row["url"])
        regions.append(row["region"] or "global")
    region = max(set(regions), key=regions.count) if regions else "global"
    return "\n\n".join(parts)[:6000], urls, region


def score_stories(settings: Settings, limit: int | None = None) -> dict:
    limit = limit or settings.max_stories_per_score
    client = LLMClient(settings)
    counters = {"processed": 0, "kept": 0, "filtered": 0, "failed": 0}
    errors: list[str] = []
    with connect() as conn:
        stories = conn.execute(
            "SELECT * FROM stories WHERE status = 'new' ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        jobs = [(story, *_story_context(conn, story)) for story in stories]

    def work(job):
        story, context, urls, region = job
        last_error = ""
        for _ in range(2):
            try:
                data, completion = client.complete_json(
                    [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": f"Новость:\n\n{context}"},
                    ],
                    model=settings.model_score,
                    role="score",
                    max_tokens=1400,
                    temperature=0.1,
                )
                return story, data, completion, region, urls, None
            except LLMError as exc:
                last_error = str(exc)
        return story, None, None, region, urls, last_error

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(work, jobs))

    for story, data, completion, region, urls, error in results:
        counters["processed"] += 1
        if error or not data:
            counters["failed"] += 1
            errors.append(f"story {story['id']}: {error}")
            with connect() as conn:
                conn.execute("UPDATE stories SET status = 'failed' WHERE id = ?", (story["id"],))
            continue
        score = int(data.get("score") or 0)
        relevant = bool(data.get("relevant"))
        keep = relevant and score >= settings.score_threshold
        status = "scored" if keep else "filtered"
        with connect() as conn:
            conn.execute(
                "UPDATE stories SET score = ?, score_reason = ?, headline_ru = ?, topic = ?, region = ?, status = ? WHERE id = ?",
                (
                    score,
                    str(data.get("reason") or "")[:400],
                    str(data.get("headline_ru") or "")[:160],
                    str(data.get("topic") or "other"),
                    str(data.get("region") or region),
                    status,
                    story["id"],
                ),
            )
        counters["kept" if keep else "filtered"] += 1
    counters["errors"] = errors
    return counters


def latest_usage(settings: Settings) -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS calls, COALESCE(SUM(cost),0) AS cost, COALESCE(SUM(allowance),0) AS allowance "
            "FROM llm_usage WHERE created_at >= datetime('now','-30 day')"
        ).fetchone()
    return dict(row) if row else {}
