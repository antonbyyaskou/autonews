# Channel icon

Approved variant: **v11 — white «А», bold lime bolt fused into the crossbar,
graphite keyline, asphalt perimeter ring.**

`v11` keeps the v10 mark and fixes the two palette problems found by the
`app-icon-optimization` audit:

1. **Off-white touched lime.** The lime bar and bolt sat directly on the white A
   at `1.07:1`, so their edges vanished in grayscale. A 24 px graphite keyline
   now separates every lime edge from the white A. Measured direct lime↔white
   pixel adjacencies at 512 px: `0` (v10 had `525`).
2. **The graphite tile disappeared on dark surfaces.** Graphite is `1.16:1`
   against Telegram's dark chat background, so the circle had no visible edge.
   A 36 px asphalt ring sits at the perimeter and measures `4.81:1` on a light
   page and `3.16:1` on Telegram dark. The square corners stay graphite.

## Palette

| Role | Hex | Use | Luminance |
| --- | --- | --- | --- |
| Graphite | `#0E1113` | tile body, keyline | 0.005 |
| Off-white | `#F2F4F3` | the letter А | 0.901 |
| Electric lime | `#C8FF2E` | bolt and crossbar only | 0.840 |
| Asphalt | `#5A7082` | perimeter ring | 0.154 |

Contrast:

| Pair | Ratio | Rule |
| --- | --- | --- |
| Off-white on graphite | `17.15:1` | pass |
| Lime on graphite | `16.06:1` | pass |
| Asphalt on light page | `4.81:1` | pass, ≥3 |
| Asphalt on Telegram dark | `3.16:1` | pass, ≥3 |
| Asphalt on graphite | `3.68:1` | pass, ≥3 |
| Off-white on lime | `1.07:1` | forbidden; never adjacent |

The forbidden off-white/lime pair still exists in the palette, so the geometry
must keep it apart. `tools/validate_palette.py` asserts that the rendered v11 has
zero off-white↔lime, lime↔asphalt and off-white↔asphalt adjacencies.

## Files

| File | Purpose |
| --- | --- |
| `icon_512.png` | the asset uploaded to Telegram (512×512, opaque RGBA) |
| `icon_512.jpg` | JPEG fallback, quality 92 |
| `icon.svg` | vector source of truth, 1024×1024 viewBox |
| `preview_sheet.png` | every variant at 192 square/circle, 96, 48 and 32 px |
| `preview_dark.png` | v11 at 192–32 px on Telegram dark `#17212B` |
| `validation.json` | per-variant geometry and small-size report, all sizes 512–32 px |
| `palette.json` | contrast matrix, CVD deltas, adjacency checks |
| `icon_v*.svg`, `icon_v*_512.png` | all explored variants, kept for reference |

## Design rules

- Symbol only. No text, no wordmark — the icon is read at 32–48 px in chat lists.
- Keep the mark inside the inscribed circle with at least 18% margin. The current
  mark sits at `0.807` of the half-width; v4's ring at `0.912` was rejected as too tight.
- The crossbar must always be present. Without it the mark reads as Cyrillic «Л»
  (see v7), which is the wrong first letter for a Russian audience.
- The bolt must fuse into the crossbar, not float above it. A floating bolt
  fragments into two lime components around 40–64 px (v9) and loses the mark at
  32 px. v11 reaches the bar's bottom edge and measures one component at every size.
- Lime must never touch off-white. A `24 px` graphite keyline separates them; the
  palette validator fails the build if that gap closes.
- Do not introduce gradients or shadows. They turn to mud when downscaled.
- Keep the `36 px` asphalt ring. Without it the graphite tile has no edge on dark
  chat themes; with it the circle clears 3:1 on both light and dark surfaces.

## Audit

Scored against the `app-icon-optimization` rubric:

| Criterion | Score | Note |
| --- | --- | --- |
| Clarity at 60×60 px | 9/10 | One mark, one connected lime shape, no text |
| Color contrast | 9/10 | All rendered adjacencies and the perimeter pass; off-white/lime remains a palette-level hazard guarded by geometry |
| Category differentiation | 8/10 | Monogram + bolt + machined ring is distinct from generic car-photo icons |
| Simplicity | 8/10 | Two mark elements plus a background ring; describable in three words |
| Brand alignment | 9/10 | Graphite/off-white/lime retained; asphalt is a neutral edge role |
| **Overall** | **43/50** | Approved |

Measured at 60 px: `229` lime px, `1` lime component, edge density `44.79`.
At 32 px: `57` lime px, `1` lime component, edge density `56.33`. The higher edge
density than v10 is the perimeter ring, not mark noise.

## Regenerate

```bash
.venv/bin/python tools/make_icons.py       # writes all variants and the sheet
.venv/bin/python tools/validate_icon.py    # writes validation.json and prints the table
.venv/bin/python tools/validate_palette.py # writes palette.json and prints the checks
```

After changing geometry, re-copy the approved variant:

```bash
cp assets/brand/icon_v11.svg assets/brand/icon.svg
cp assets/brand/icon_v11_512.png assets/brand/icon_512.png
```

Then regenerate the JPEG fallback:

```bash
.venv/bin/python - <<'PY'
from PIL import Image
Image.open("assets/brand/icon_512.png").convert("RGB").save(
    "assets/brand/icon_512.jpg", quality=92, optimize=True
)
PY
```

## Apply to the channel

The bot has `can_change_info`, so it can set the photo itself:

```bash
.venv/bin/python - <<'PY'
import httpx
tok=[l.split("=",1)[1].strip() for l in open(".env") if l.startswith("TELEGRAM_BOT_TOKEN=")][0]
with open("assets/brand/icon_512.png","rb") as fh:
    r=httpx.post(f"https://api.telegram.org/bot{tok}/setChatPhoto",
                 data={"chat_id":"@autonews_test"},
                 files={"photo":("icon_512.png",fh,"image/png")},
                 headers={"User-Agent":"autonews/0.1"}, timeout=60)
print(r.json())
PY
```

The bot's own avatar cannot be set through the Bot API; use BotFather `/setuserpic`
with the same file so the DM and the channel match.
