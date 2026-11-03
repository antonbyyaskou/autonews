# Architecture

## Shape

A single local process, invoked by CLI or by the Telegram bot, writing to one
SQLite file and one media directory. No server, no queue, no daemon.

```
RSS feeds ──► ingest ──► extract ──► cluster ──► score ──► summarize ──► review ──► publish
                 │           │           │          │           │            │
                 └───────────┴───────────┴──────────┴───────────┴────────────┘
                                        SQLite + media/
```

Each arrow is a separate pipeline stage with its own CLI subcommand, so a run
can be resumed at any stage and failures are local to one stage.

## Data model

```
sources        id, name, url, region, lang, weight, enabled, last_status,
               last_checked_at, consecutive_failures
articles       id, source_id, url, canonical_url, title, summary, body,
               lang, published_at, fetched_at, content_hash, media_urls,
               status
stories        id, primary_article_id, title_key, created_at, article_count,
               region, score, score_reason, status
story_articles story_id, article_id
candidates     id, story_id, headline_ru, body_ru, hashtags, media_path,
               media_kind, media_source_url, attestation, model,
               token_usage, status, created_at
publlog        id, candidate_id, channel_id, message_id, published_at
runs           id, started_at, finished_at, stage, counters, errors
```

Status values: `new`, `extracted`, `clustered`, `scored`, `drafted`,
`approved`, `published`, `skipped`, `rejected`, `failed`.

## Modules

```
src/autonews/
  config.py      settings from .env + YAML, paths
  db.py          schema creation, connection, migrations
  models.py      dataclasses for rows
  llm.py         LLMClient protocol, GoClient, DeepSeekClient, usage ledger
  media.py       media discovery, download, validation, storage
  pipeline/
    ingest.py    RSS polling and article persistence
    extract.py   full-text and metadata extraction
    cluster.py   title normalisation, similarity, event grouping
    score.py     relevance and novelty scoring
    summarize.py Russian generation, number attestation, hashtags
  telegram/
    bot.py       command handling, digest rendering, confirmation state
    publish.py   media upload and channel delivery
  cli.py         argument parsing and stage dispatch
```

## LLM layer

One protocol:

```
complete(messages, *, model, max_tokens, temperature, json_mode) -> Completion
```

`Completion` carries text, model, prompt tokens, completion tokens, cost, and
allowance impact. Two clients implement the protocol: `GoClient` against
`https://opencode.ai/inference/go/openai/v1` and `DeepSeekClient` against
`https://api.deepseek.com/v1`. Selection is `LLM_PROVIDER=go|deepseek`.

Model roles are configuration, not code:

| Role | Default model | Purpose |
| --- | --- | --- |
| `score` | `glm-5.3-flash` | relevance, novelty, region classification |
| `draft` | `glm-5.3-flash` | Russian post generation |
| `verify` | `deepseek-v4.1-flash` | reserved for a second-pass number check |

`deepseek-v4.1-flash` emits roughly 1,300 reasoning tokens per request, so it
needs a 2,500-token budget and about 13 seconds. `glm-5.3-flash` answers in
3 seconds with clean JSON and is the default. Both are covered by the Go
allowance.

Go requires `User-Agent` and `x-opencode-session`. Both are set from config.
The session id is stable per installation so prompt caching can work.

## Number attestation

The generator returns structured output: the post text plus a list of numeric
claims, each with the literal source substring it came from. A validator strips
formatting from both the post and the source body, then checks that every
number in the post exists in the source body within an allowed normalisation
set (decimal separators, thousands separators, unit forms). Failures produce a
report; the draft is regenerated once with the report attached; a second
failure marks the candidate `rejected` and it never reaches review.

## Media policy

Discovery order: RSS media enclosure, `og:image`, first large image in the
article body, source CDN pattern. Accepted: `jpg`, `png`, `webp` for images;
`mp4`, `webm` for video. Rejected: `gif`, tracking pixels under 200 px,
playlist files. Downloads capped at 45 MB and 8 s connect / 30 s read. Each
file stored as `media/<candidate_id>.<ext>` with the origin URL in the row.

## Review protocol

The digest is one message. Each line is `#N · headline · source · score`.
Candidate detail is a separate message with the draft, the media, and the
attestation summary. `Publish` requires a second confirmation tap that expires
after ten minutes. Confirmation state lives in SQLite, so a bot restart does
not lose pending approvals.

## Failure model

A source failure increments `consecutive_failures`; three in a row disables
the source and reports it in `/status`. An extraction failure keeps the
article with RSS summary text and marks it degraded. LLM failures retry twice
with exponential backoff, then mark the story `failed` without aborting the
run. The run record always closes, even on exception.

## Cost model

The Go plan gives DeepSeek V4.1 Flash a monthly allowance far beyond this
workload. Each call's `opencode.allowance` is recorded, and `/status` reports
monthly usage, so a change in provider policy is visible immediately.
