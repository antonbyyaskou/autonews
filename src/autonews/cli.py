from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx

from .config import Settings, load_settings
from .db import connect, init_db
from .digest import create_digest, digest_text, latest_candidate_at, latest_digest, split_message
from .llm import LLMClient, LLMError
from .pipeline import run_pipeline, run_stage
from .pipeline.summarize import render_post
from .telegram.publish import candidate_sources, candidate_urls


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def cmd_init(args, settings: Settings) -> None:
    init_db()
    print("database ready")


def cmd_check(args, settings: Settings) -> None:
    init_db()
    print(f"provider: {settings.llm_provider}")
    print(f"base: {settings.llm_base}")
    print(f"key: {'set' if settings.llm_key else 'missing'}")
    try:
        client = LLMClient(settings)
        completion = client.complete(
            [{"role": "user", "content": "Переведи на русский: BYD launched a new electric sedan."}],
            model=settings.model_draft,
            role="check",
            max_tokens=120,
        )
        print(f"model: {completion.model}")
        print(f"reply: {completion.text}")
        print(f"billing_source: {completion.billing_source}")
        print(f"cost: {completion.cost}")
        print(f"allowance: {completion.allowance}")
        print("llm: ok")
    except LLMError as exc:
        print(f"llm: FAILED — {exc}")
        sys.exit(1)
    with connect() as conn:
        counts = {
            table: conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            for table in ("sources", "articles", "stories", "candidates", "publish_log")
        }
    _print(counts)


def cmd_sources(args, settings: Settings) -> None:
    from .pipeline.ingest import sync_sources

    total = sync_sources()
    print(f"registry loaded: {total}")
    with connect() as conn:
        rows = conn.execute(
            "SELECT name, region, enabled, last_status, consecutive_failures, url FROM sources "
            "WHERE enabled = 1 OR ? = 0 ORDER BY enabled DESC, name",
            (1 if args.check else 0,),
        ).fetchall()
    if not args.check:
        for row in rows:
            state = "ON " if row["enabled"] else "OFF"
            print(f"{state} {row['name']:<22} {row['region']:<6} {row['last_status'] or '—'}")
        return
    with httpx.Client(timeout=20, headers={"User-Agent": settings.user_agent}, follow_redirects=True) as client:
        for row in rows:
            try:
                resp = client.get(row["url"])
                print(f"{resp.status_code:>3} {row['name']:<22} {row['url']}")
            except Exception as exc:
                print(f"ERR {row['name']:<22} {exc}")


def cmd_stage(stage: str):
    def run(args, settings: Settings) -> None:
        init_db()
        if args.limit:
            counters = run_stage(settings, stage, limit=args.limit)
        else:
            counters = run_stage(settings, stage)
        _print(counters)

    return run


def cmd_run(args, settings: Settings) -> None:
    init_db()
    stages = args.stages.split(",") if args.stages else None
    results = run_pipeline(settings, stages)
    _print(results)
    created = create_digest()
    if created:
        digest_id, text = created
        print(f"\n=== digest {digest_id} ({len(text)} chars) ===\n")
        print(text)
    else:
        print("\nno new candidates")


def cmd_digest(args, settings: Settings) -> None:
    created = create_digest(limit=args.limit)
    if not created:
        print("no new candidates")
        return
    digest_id, text = created
    print(f"digest {digest_id}\n")
    print(text)


def cmd_list(args, settings: Settings) -> None:
    digest_id = latest_digest()
    if digest_id is None:
        print("no digest yet")
        return
    print(digest_text(digest_id))


def cmd_show(args, settings: Settings) -> None:
    row = latest_candidate_at(args.position)
    if not row:
        print("no candidate at that position")
        return
    text = render_post(row["body_ru"], row["hashtags"], candidate_sources(row["id"]), as_html=False)
    print(f"# {row['headline_ru']}")
    print(f"status: {row['status']}  score: {row['score']}  candidate_id: {row['id']}")
    print(f"media: {row['media_path'] or 'none'}")
    print(f"attestation: {row['attestation']}")
    print("\n" + text)
    urls = candidate_urls(row["id"])
    if urls:
        print("\nsources:")
        for url in urls[:5]:
            print(f"  {url}")


def cmd_post(args, settings: Settings) -> None:
    from telegram import Bot

    from .telegram.publish import publish

    row = latest_candidate_at(args.position)
    if not row:
        print("no candidate at that position")
        return
    if not args.yes:
        print(f"would publish candidate {row['id']} to {settings.telegram_channel_id}. Re-run with --yes.")
        return
    if not settings.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set")

    async def go() -> int:
        bot = Bot(settings.telegram_bot_token)
        return await publish(bot, settings, int(row["id"]))

    try:
        message_id = asyncio.run(go())
    except Exception as exc:
        print(f"publish failed: {exc}")
        return
    print(f"published message_id={message_id}")


def cmd_bot(args, settings: Settings) -> None:
    from .telegram.bot import main as bot_main

    bot_main()


def cmd_status(args, settings: Settings) -> None:
    with connect() as conn:
        counts = {
            table: conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
            for table in ("sources", "articles", "stories", "candidates", "publish_log")
        }
        by_status = {
            row["status"]: row["n"]
            for row in conn.execute("SELECT status, COUNT(*) AS n FROM candidates GROUP BY status").fetchall()
        }
        usage = conn.execute(
            "SELECT COUNT(*) AS calls, COALESCE(SUM(cost),0) AS cost, COALESCE(SUM(allowance),0) AS allowance "
            "FROM llm_usage WHERE created_at >= datetime('now','-30 day')"
        ).fetchone()
        last = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    _print({"counts": counts, "candidates": by_status, "llm_30d": dict(usage)})
    if last:
        print(f"last run: {last['stage']} started {last['started_at']} finished {last['finished_at']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autonews", description="Automotive news pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create database").set_defaults(func=cmd_init)
    sub.add_parser("check", help="verify llm and database").set_defaults(func=cmd_check)

    p_sources = sub.add_parser("sources", help="list or check sources")
    p_sources.add_argument("--check", action="store_true", help="fetch each feed")
    p_sources.set_defaults(func=cmd_sources)

    for stage in ("ingest", "extract", "cluster", "score", "draft"):
        p = sub.add_parser(stage, help=f"run {stage} stage")
        p.add_argument("--limit", type=int, default=None)
        p.set_defaults(func=cmd_stage(stage))

    p_run = sub.add_parser("run", help="run the full pipeline")
    p_run.add_argument("--stages", default=None, help="comma separated subset")
    p_run.set_defaults(func=cmd_run)

    p_digest = sub.add_parser("digest", help="create a digest from new drafts")
    p_digest.add_argument("--limit", type=int, default=25)
    p_digest.set_defaults(func=cmd_digest)

    sub.add_parser("list", help="print last digest").set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="print candidate draft")
    p_show.add_argument("position", type=int)
    p_show.set_defaults(func=cmd_show)

    p_post = sub.add_parser("post", help="publish candidate to channel")
    p_post.add_argument("position", type=int)
    p_post.add_argument("--yes", action="store_true")
    p_post.set_defaults(func=cmd_post)

    sub.add_parser("bot", help="run telegram review bot").set_defaults(func=cmd_bot)
    sub.add_parser("status", help="show counters").set_defaults(func=cmd_status)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    settings = load_settings()
    args.func(args, settings)


if __name__ == "__main__":
    main()
