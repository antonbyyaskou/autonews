# Roadmap

Each phase ends in a runnable state. Phases are ordered so that the thing you
need next never depends on a later phase.

## Phase 0 — Setup and provider verification

Deliverables: project skeleton, dependency manifest, `.env.example`, SQLite
schema, LLM client, `autonews check` command.

Acceptance: `autonews check` proves the LLM answers in Russian and reports the
billing source and allowance impact; database initialises cleanly.

## Phase 1 — Ingest

Deliverables: source registry, RSS polling, article persistence, source health
tracking, `autonews sources` and `autonews ingest` commands.

Acceptance: two consecutive ingest runs add zero duplicate articles; a dead
feed is recorded as a failure without aborting the run; the source table shows
last status per feed.

## Phase 2 — Extraction and clustering

Deliverables: full-text extraction, canonical URLs, content hashing, title
normalisation, similarity grouping, `autonews extract` and `autonews cluster`.

Acceptance: two outlets covering one launch collapse into one story; unrelated
stories from the same outlet on the same day stay separate.

## Phase 3 — Scoring and drafting

Deliverables: relevance scoring with reasons, Russian post generation, number
attestation gate, hashtag selection, media download, `autonews draft`.

Acceptance: a run produces 20–40 candidates ranked by score; a deliberately
mangled spec number is caught by attestation and the candidate is rejected;
every draft is 300–500 characters with hashtags and a source line.

## Phase 4 — Review bot

Deliverables: digest message, `/list`, `/show`, `/edit`, `/skip`, `/status`,
`/sources`, pending-approval state in SQLite.

Acceptance: `/run` completes and delivers a readable digest; `/show N` returns
the draft with media and source links; bot restart preserves pending state.

## Phase 5 — Publishing

Deliverables: channel delivery, media or text post, publish log, duplicate
publish block, `/post N` with ten-minute confirmation.

Acceptance: an approved candidate appears in the channel with the hero image
and caption; the same candidate cannot publish twice; the publish log records
the message id.

## Phase 6 — Operations

Deliverables: `launchd` plist for optional scheduling, log rotation, database
backup, monthly cost report, `/sources` remediation hints.

Acceptance: a scheduled run completes unattended and a failure is visible in
`/status`.

## Phase 7 — Web UI (deferred)

Deliverables: local read-and-edit queue at `localhost:8000` with media swap,
bulk approval, and preview. Built only if bot review proves limiting.

## Definition of done for v1

You open the bot, send `/run`, receive a numbered list of candidate posts,
open one, see the draft and its image, press publish, and the post lands in the
channel. Every step is auditable in SQLite.

# Growth track

Separate from the build phases above: distribution work, ordered by expected
subscribers per hour of effort. Search priority is **Yandex first, Google
second** — the audience is Russian and Yandex indexes `t.me/s/` pages far more
reliably than Google does. Growth phases end in a measurable state, not a
runnable one.

## Priority map

| Rank | Lever | Cost | Phase |
| --- | --- | --- | --- |
| 1 | Public, findable, measured channel | 0 | G1 |
| 2 | Yandex indexation | 0 | G2 |
| 3 | Publish speed and volume | 0 | G3 |
| 4 | Forwardable formats | 0 | G4 |
| 5 | Mutual promotion | 0 | G5 |
| 6 | Dzen / VK distribution | 0 | G6 |
| 7 | Catalogue and paid placements | low | G7 |
| 8 | Google indexation | 0 | G8 |
| 9 | Telegram Ads | high | G9 |
| 10 | Retention loop | 0 | G10 |

## G1 — Foundation and measurement

Runbook: [GROWTH.md](GROWTH.md#g1--foundation-and-measurement).

Deliverables: channel public with a niche `@username`; title and description
carrying RU search keywords; pinned post stating the value and linking the
discussion group; discussion group linked so comments show; one unique invite
link per acquisition source, each mapped to a row in the tracking sheet;
channel listed in TGStat and Telemetr; baseline sheet with subscribers, views
per post, reposts per post, and 7/30-day retention (native stats unlock at 500
subscribers).

Acceptance: the channel is found in TGStat and Telemetr by «автоновости»;
three source invite links are live; baseline recorded.

## G2 — Yandex indexation

Runbook: [GROWTH.md](GROWTH.md#g2--yandex-indexation).

Priority 1. Google cannot be verified and indexes Telegram slowly; Yandex
indexes `t.me/s/` pages well and is the engine the audience uses.

Deliverables: static landing page in the repo (`site/`) with RU keyword copy,
links to `https://t.me/s/<username>`, `Organization`/`WebSite` JSON-LD,
`sitemap.xml`, `robots.txt`; deploy to GitHub Pages or an owned domain; verify
in Yandex Webmaster, submit the sitemap, enable quick indexing; confirm
`t.me/s/<username>` loads without login.

Acceptance: the landing page is indexed by Yandex within two weeks;
`site:t.me/<username>` returns posts; Webmaster shows impressions for at least
one target query.

## G3 — Publishing velocity

Deliverables: 5–10 posts per day at fixed slots; a breaking story published
within 30 minutes of the source; scheduling support in the pipeline where it is
missing; recorded delay between source publication and channel post.

Acceptance: over two weeks the median delay is under 60 minutes and the 90th
percentile under three hours; the daily volume target is met five days in
seven.

## G4 — Forwardable content

Deliverables: an auto-generated spec card per model launch (model, power,
range, price, market as one image); recurring formats; first-line variants
tested against reposts per post as the primary metric.

Acceptance: every model-launch post carries a card; reposts per post double
against the G1 baseline.

## G5 — Mutual promotion

Deliverables: partner sheet; same-size rule (±30%); three to five repost swaps
per week with a standard copy; a unique invite link per partner.

Acceptance: 20 partners and 40 swaps within eight weeks; partner-sourced
30-day retention at or above 50%.

## G6 — Dzen and VK distribution

Deliverables: RSS feed of channel posts imported into Dzen with a canonical
link back to each `t.me` post; teaser cross-posts into VK auto communities and
Drive2.

Acceptance: Dzen channel live at 10 posts per week with measurable referral
subscribers.

## G7 — Catalogue and paid placements

Deliverables: a test matrix of three placements on Telega.in, TGStat, or
Telemetr at 5–10k ₽ per month; cost per subscriber and 30-day retention per
placement.

Acceptance: cost per subscriber is known per placement; at least one placement
passes the retention gate; placements above 70% 30-day churn are cut.

## G8 — Google indexation

Priority 2, after Yandex.

Deliverables: Search Console verified on the landing page; sitemap submitted;
structured data validated; cross-links from X, VK, GitHub, and Habr; individual
post pages checked for indexing.

Acceptance: the landing page and `site:t.me/<username>` results are indexed by
Google; Search Console shows impressions.

## G9 — Telegram Ads

Deliverables: campaign with creatives and a conversion post, run only after
cost per subscriber and retention are known from G5–G7.

Acceptance: one campaign with cost per subscriber at or below the best
alternative channel and the retention gate passed.

## G10 — Retention loop

Ongoing, monthly.

Deliverables: weekly report, cohort retention by source, and a verdict for
every acquisition source (scale, hold, kill).

Acceptance: one report per month; no source without a verdict.

## Definition of done for growth

Ninety days after G1: the channel is indexed by Yandex and Google, publishes at
a stable cadence, and every subscriber source has a measured cost and a 30-day
retention number.
