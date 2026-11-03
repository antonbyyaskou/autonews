# Autonews

Pipeline for a Russian-language Telegram channel about cars: collects foreign
automotive news, filters it, drafts Russian posts, attaches media, and publishes
only after your approval.

Full design: [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md),
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
[docs/ROADMAP.md](docs/ROADMAP.md). Distribution phases and the G1/G2 runbook:
[docs/GROWTH.md](docs/GROWTH.md).

## Requirements

- macOS with Python 3.11
- An OpenCode Go subscription (default) or a DeepSeek API key
- A Telegram bot and a channel where the bot is an admin

## Install

```bash
cd autonews
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/autonews check
```

`autonews check` verifies the database and sends one real request to the model,
printing the billing source. Without `OPENCODE_API_KEY` it reads the key that
OpenCode already stores in `~/.local/share/opencode/auth.json`.

## Use from the terminal

```bash
.venv/bin/autonews run              # ingest, extract, cluster, score, draft
.venv/bin/autonews list             # last digest
.venv/bin/autonews show 3           # full draft, media and sources
.venv/bin/autonews post 3 --yes     # publish (bypasses the confirmation step)
.venv/bin/autonews status           # counters and LLM usage
```

Stages can be run separately: `ingest`, `extract`, `cluster`, `score`, `draft`.
Each accepts `--limit`.

## Use from Telegram

Fill `.env`:

```
TELEGRAM_BOT_TOKEN=123:abc
TELEGRAM_CHANNEL_ID=@your_test_channel
TELEGRAM_OPERATOR_ID=123456789
```

Create the bot with [@BotFather](https://t.me/BotFather), add it to the channel
as an administrator with post rights, and get your numeric id from
[@userinfobot](https://t.me/userinfobot). Then:

```bash
.venv/bin/autonews bot
```

Commands: `/run`, `/list`, `/show N`, `/edit N text`, `/skip N`, `/post N`,
`/status`, `/sources`. `/post` asks for a second confirmation that expires in
ten minutes.

## How a run works

1. `ingest` polls the RSS registry in `config/sources.yaml` and stores new items.
2. `extract` fetches each article, extracts the body and candidate media.
3. `cluster` merges coverage of the same event from different outlets.
4. `score` rates relevance and novelty and writes a Russian headline plus a reason.
5. `draft` writes the post, validates every number against the source text,
   downloads one hero image or video, and stores a candidate.

Nothing is published without `/post`.

## The accuracy gate

Auto news is mostly numbers, so numbers are treated as claims. Every number in
a draft (values of 100 or more, decimals, or numbers followed by a unit) must
exist in the source text after normalisation. If not, the draft is regenerated
once with the offending numbers listed, then rejected. The check is in
`src/autonews/pipeline/summarize.py` and is covered by `tests/test_attest.py`.

## Media

One hero image per post, or a direct video under 45 MB when the source provides
one. Files are downloaded to `data/media/` and the origin URL is stored next to
each candidate. Review each image before publishing; press photos are licensed
material.

## Configuration

| File | Purpose |
| --- | --- |
| `.env` | secrets and Telegram ids |
| `config/settings.yaml` | models, thresholds, limits |
| `config/sources.yaml` | RSS registry: region, language, weight, enabled |
| `config/style.md` | Russian style guide injected into the drafting prompt |

Model roles default to `glm-5.3-flash`, which is fast, produces clean JSON, and
is well within the Go allowance. Switch `model_draft` to `deepseek-v4.1-flash`
for higher quality at roughly three times the latency.

To leave OpenCode Go, set `LLM_PROVIDER=deepseek` and `DEEPSEEK_API_KEY`; no code
change is needed.

## Source health

```bash
.venv/bin/autonews sources            # registry state
.venv/bin/autonews sources --check    # fetch every enabled feed
```

A source is disabled automatically after three consecutive failures. Re-enable
it in `config/sources.yaml` by setting `enabled: true`.

## Tests

```bash
.venv/bin/pip install pytest
.venv/bin/python -m pytest -q
```
