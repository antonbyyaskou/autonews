# Autonews — Requirements

Russian-language Telegram channel about automotive news, with emphasis on new
technologies and new models. Curated by a human: the system collects and
prepares, the operator selects and approves, the system publishes.

## Decisions

| Area | Decision |
| --- | --- |
| Runtime | Local macOS machine, manual runs |
| Language | Python 3.11 |
| Storage | SQLite on disk |
| LLM access | OpenCode Go endpoint `https://opencode.ai/inference/go/openai/v1` |
| LLM fallback | DeepSeek direct (`https://api.deepseek.com/v1`), config switch |
| Review surface | Private Telegram bot chat, numbered digest |
| Publishing | Telegram Bot API, bot is channel admin |
| Web UI | Deferred to a later phase |
| Sources | RSS-first registry, foreign-language only |
| Regions | China, US, Europe |
| Media | Re-host press images, one hero image per post |
| Video | Direct `.mp4`/`.webm` under 45 MB when present, otherwise a link |
| Post length | 300–500 characters, hook first line |
| Post style | Neutral wire-service tone, hashtags, italic source line, no emoji |
| Deduplication | One candidate per event (cluster across outlets) |
| Accuracy | Every number must be attested in source text |

## Functional requirements

### FR-1 Source registry
Sources are declared in `config/sources.yaml` with region, language,
weight, and feed URL. Adding a source is a data change, not a code change.
The system validates a feed before it enters rotation.

### FR-2 Ingest
Poll enabled RSS feeds, store raw items, skip items already seen. Record
fetch time, HTTP status, and failure reason per source per run.

### FR-3 Extraction
For each new item, fetch the article HTML and extract the main body text,
publication timestamp, canonical URL, and candidate media URLs. Extraction
falls back to the RSS summary when the page is unavailable.

### FR-4 Deduplication and clustering
Items that describe the same event are grouped into one story. Grouping uses
normalised title tokens, entity overlap, and publication-time proximity.
One story yields at most one candidate post.

### FR-5 Relevance scoring
Each story receives a score for automotive relevance, novelty, and
technology/model focus. The default queue drops stories below the threshold.
Every story carries a reason string so the operator can audit the score.

### FR-6 Post generation
A story is rendered into a Russian post: 300–500 characters, hook first line,
2–4 facts, hashtags, italic source line. The original language is translated;
Russian-language source material is out of scope.

### FR-7 Number attestation
Every numeric claim in a generated post must appear in the source text,
allowing only unit and format normalisation. Unattested numbers cause the
post to be flagged, regenerated once, then rejected. This is a hard gate.

### FR-8 Media
One hero image per post, downloaded and stored locally. Direct video files
under 45 MB are attached instead of an image. Media source URL is recorded.

### FR-9 Review
The bot sends one digest message per run with numbered candidates: rank,
Russian headline, source, region, score. Commands:

| Command | Behaviour |
| --- | --- |
| `/run` | Execute a collection run now |
| `/list` | Resend the latest digest |
| `/show N` | Full draft, media preview, and source links |
| `/edit N <text>` | Replace draft text |
| `/skip N` | Reject candidate |
| `/post N` | Publish after explicit confirmation |
| `/status` | Counts, last run, failures |
| `/sources` | Source health table |

### FR-10 Publishing
Publishing requires an explicit confirmation. The system sends the hero media
with the post as caption, or the text alone when no media exists. Publish
records message id, timestamp, and channel. Re-publishing the same candidate
is blocked.

### FR-11 Traceability
Every published post stores its candidate, story, contributing source URLs,
model used, token usage, and the attestation report.

## Non-functional requirements

- Idempotent collection: re-running does not create duplicates.
- No secrets in the repository. `.env` is git-ignored.
- Every network call has a timeout and a bounded retry.
- The LLM layer is a single interface with two implementations.
- Runs complete on a charged laptop, offline-safe: a failed source never
  aborts the run.
- Cost visibility: each LLM call records tokens and allowance impact.

## Non-goals

- No autonomous publishing without approval.
- No paywalled site bypass, no login-gated scraping.
- No Russian-language sources, to avoid re-posting existing Russian media.
- No full-site crawling of arbitrary domains.
- No web UI in v1.
- No multi-user access control.

## Risks

| Risk | Mitigation |
| --- | --- |
| Go endpoint is intended for coding agents | Own user agent, stable session header, low volume, single-switch fallback to DeepSeek direct |
| Hallucinated specifications | Hard number-attestation gate before a draft is shown |
| Press-photo copyright | Source recorded per image, per-image rejection in review, official/CDN preference |
| Telegram caption limit 1024 chars | Post target is 300–500 characters |
| Bot API upload limit 50 MB | Video cap 45 MB, otherwise link |
| Feed rot | `/sources` health report, disabled source list |
| Duplicate events across outlets | Event clustering before scoring |
