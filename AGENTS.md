# AGENTS.md

Local Python 3.11 pipeline for a Russian-language Telegram auto-news channel:
RSS → extract → cluster → score → draft → human approval → publish. One SQLite
file (`data/autonews.db`), one media directory (`data/media/`), no server.

## Commands

```bash
.venv/bin/pip install -e .[dev]        # install with pytest
.venv/bin/python -m pytest -q          # tests
.venv/bin/autonews init                # create the database
.venv/bin/autonews check               # one live LLM call + DB check
.venv/bin/autonews run                 # full pipeline
.venv/bin/autonews run --stages ingest,extract
.venv/bin/autonews <stage> --limit N   # ingest|extract|cluster|score|draft
.venv/bin/autonews digest --limit 25   # build a review digest
.venv/bin/autonews list|show N|status|sources
.venv/bin/autonews sources --check     # fetch every enabled feed
.venv/bin/autonews bot                 # run the Telegram review bot
.venv/bin/python tools/build_site.py   # render the static site
.venv/bin/python -m http.server 8080 -d site/public  # preview it
```

The test suite uses a temporary SQLite database and fake Telegram objects; it
has no network or production access. Run it, fix failures caused by the change,
and rerun affected tests without asking for approval at each step.

## Layout

- `src/autonews/pipeline/` — one module per stage; every stage must stay runnable
  on its own through the CLI.
- `src/autonews/llm.py` — the only LLM entry point. Model roles are config, not
  code.
- `src/autonews/pipeline/summarize.py` — Russian generation and `attest()`, the
  number gate. Do not weaken or bypass it.
- `src/autonews/telegram/` — review bot and publishing. `bot.py` holds command
  handlers and confirmation state.
- `config/` — `settings.yaml` (limits, thresholds, models), `sources.yaml` (RSS
  registry), `style.md` (Russian tone guide), `site.yaml` (landing page),
  `.env` (secrets, gitignored).
- `site/` — `templates/` is source; `site/public/` is a build artifact and is
  gitignored. Edit templates and `config/site.yaml`, never `site/public/`.
- `tools/` — `build_site.py` (landing page), `make_icons.py`,
  `validate_icon.py`, `validate_palette.py` (brand asset checks).
- `assets/brand/` — icon sources and generated PNGs.
- `.github/workflows/pages.yml` — builds and deploys the site to GitHub Pages.
- `tests/` — pytest, no network; `test_site.py` covers the static site.

## Conventions

- Keep stage boundaries; a failure in one stage must not require rerunning all
  earlier stages.
- Generated posts are Russian, plain text, no emoji or markdown. The length gate
  is `post_min_chars`/`post_max_chars` in `config/settings.yaml`; `config/style.md`
  asks for 300–500 characters. Every number must exist in the source text;
  `attest()` enforces it.
- Prefer editing config over hardcoding values that already have a setting.
- Keep dependencies and test config in `pyproject.toml`; there is no separate
  requirements file. Site changes need `test_site.py` and a local build.
- Match existing style: small modules, dataclasses, explicit SQL, no framework.

## Boundaries

- Never publish to Telegram or change a real channel unless the user explicitly
  asks. `/post`, `autonews post`, and `setChatPhoto` are destructive actions.
- Pushing to `main` with changes under `site/`, `config/site.yaml`,
  `tools/build_site.py`, the icon, or the Pages workflow deploys GitHub Pages.
  Do not deploy or change `base_url`/`channel` without an explicit request.
- Never print, log, or commit secrets from `.env`; never commit `data/` or
  `site/public/`.
- Live feed and LLM calls are fine when the task needs them; use `--limit` for
  checks. Do not mass-refresh sources for an unrelated change.

## Docs

Read only the one that fits the change; none are required before every edit.

- Service boundaries and data flow: `docs/ARCHITECTURE.md`
- Requirements and acceptance criteria: `docs/REQUIREMENTS.md`
- Phases and growth track: `docs/ROADMAP.md`
- Distribution phases and the G1/G2 runbook: `docs/GROWTH.md`
- Channel tone and post rules: `config/style.md`

## Done

A change is complete when tests pass, the affected stage runs with a small
`--limit`, and no secrets or `data/` files are staged. Site changes also need
`test_site.py` and a local `tools/build_site.py` build. Continue through
implementation and verification before stopping. Stop only for a destructive
action or a real ambiguity.
