# Growth runbook

Operational steps for the growth track in `docs/ROADMAP.md`. G1 and G2 are
implemented; G3–G10 are planned only.

| Phase | State |
| --- | --- |
| G1 Foundation and measurement | checklist below, no code |
| G2 Yandex indexation | `config/site.yaml`, `site/templates/`, `tools/build_site.py`, `.github/workflows/pages.yml` |
| G3–G10 | planned in `docs/ROADMAP.md` |

## G1 — Foundation and measurement

1. **Public channel.** Channel settings → Channel type → Public channel →
   set a username. It must match `channel` in `config/site.yaml`; the build
   strips a leading `@`.
2. **Searchable title and description.** Title up to 128 characters,
   description up to 255. Both are what Yandex and Google show. Keep the niche
   words in the first half: `Автоновости`, `новые модели`, `электромобили`.
3. **Pinned post.** Post and pin:

   > Autonews — новости автопрома Китая, США и Европы. Новые модели,
   > электромобили, характеристики, цены и сроки. Каждый пост со ссылкой на
   > первоисточник. Обсуждение — в комментариях.

4. **Comment group.** Create a group, then Channel settings → Discussion →
   link the group. Comments keep readers and give search engines more text.
5. **Attribution links.** Channel settings → Invite links → create one per
   acquisition source and name it after the source (`tgstat`, `dzen`,
   `partner-<name>`, `vk`). Public channels also receive joins through the
   username, so invite-link counts are a lower bound, not the total.
6. **Catalogues.** Claim the channel in TGStat and add it to Telemetr. These
   are the directories Russian users browse; the channel cannot be found in
   them before it is added.
7. **Tracking sheet.** One row per acquisition source:

   | Column | Meaning |
   | --- | --- |
   | `date` | first day of the source |
   | `source` | invite link name |
   | `cost` | spend in RUB, `0` for organic |
   | `subscribers` | joins from the link |
   | `retained_7d` | still subscribed after 7 days |
   | `retained_30d` | still subscribed after 30 days |
   | `verdict` | `scale`, `hold`, `kill` |

8. **Baseline.** Record subscribers, average views per post, average reposts
   per post, and ER. Native stats unlock at 500 subscribers; before that use
   TGStat.

Acceptance for G1: the channel is found in TGStat and Telemetr by
«автоновости»; three invite links are live; the baseline sheet has a first row.

## G2 — Yandex indexation

Yandex is first because it indexes `t.me/s/` pages reliably and is the engine
the Russian audience uses. Google is G8.

### 1. Configure the site

Edit `config/site.yaml`:

```yaml
base_url: https://your-domain.example   # no trailing slash
channel: your_channel                    # bare username, no @
title: "Автоновости — новые модели, электромобили и технологии"
description: "Новости автопрома Китая, США и Европы: новые модели, характеристики, цены и сроки."
```

`base_url` must be the final public URL: the canonical link and the sitemap
both use it. A wrong value splits indexing between two hosts. The build prints
a warning while the value still contains `.example`.

### 2. Build and preview

```bash
.venv/bin/python tools/build_site.py
.venv/bin/python -m http.server 8080 -d site/public
```

Check `http://localhost:8080/`, `/robots.txt`, `/sitemap.xml`. The generated
`site/public/` is a build artifact and is git-ignored.

### 3. Deploy

The repository is not a git repo yet. Once it is on GitHub:

```bash
git init
git add -A
git commit -m "Add landing page and deploy workflow"
gh repo create autonews --public --source=. --push
```

Then GitHub → Settings → Pages → Source: **GitHub Actions**. The workflow
`.github/workflows/pages.yml` builds and deploys `site/public` on every push
to `main` that touches the site, config, or icon.

Custom domain: GitHub → Settings → Pages → Custom domain, enable HTTPS, then
set `base_url` to that domain and push to rebuild.

### 4. Yandex Webmaster

1. `webmaster.yandex.ru` → Add site → enter the deployed `base_url` host.
2. Verify with the meta tag: copy the `yandex-verification` hash into
   `config/site.yaml` → `yandex_verification`, rebuild and redeploy. DNS TXT
   also works if you own the domain.
3. Indexing → Sitemap files → add `https://<host>/sitemap.xml`.
4. Indexing → Recrawl pages → request `/`.
5. Watch Indexing → Pages in search for the first appearance, usually 1–3
   weeks.

The channel itself cannot be submitted to Webmaster, because `t.me` is not
yours. Yandex discovers `t.me/s/<channel>` through links; the landing page
links it directly. Check progress in Yandex with `site:t.me/<channel>`.

### 5. Google

The `google_verification` field in `config/site.yaml` is ready, but Search
Console work belongs to G8, after Yandex shows impressions.

## Verification

```bash
.venv/bin/python -m pytest tests/test_site.py -q
.venv/bin/python tools/build_site.py
curl -s https://<host>/robots.txt
curl -s https://<host>/sitemap.xml | head
```

Check that the canonical, sitemap `loc`, and the deployed host are identical.

## What not to do

- Do not buy subscribers or use generic giveaways: they raise the count and
  destroy retention, which is the metric every later phase is judged on.
- Do not mirror full posts on the landing page. It is a hub that links to the
  channel; duplicated text competes with `t.me` pages instead of supporting
  them.
- Do not keyword-stuff the title or description. Yandex filters it and readers
  leave.
