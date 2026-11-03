from __future__ import annotations

import json
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

BG = (14, 17, 19)
WHITE = (242, 244, 243)
LIME = (200, 255, 46)
ASPHALT = (90, 112, 130)
LIGHT_PAGE = (247, 247, 247)
DARK_TG = (23, 33, 43)
SIZES = [512, 128, 64, 60, 48, 40, 32]


def relative_luminance(rgb) -> float:
    def channel(c: int) -> float:
        v = c / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    la, lb = relative_luminance(a), relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return round((hi + 0.05) / (lo + 0.05), 2)


def classify(r, g, b) -> str:
    if g > 180 and r > 110 and b < 130 and (g - b) > 80:
        return "lime"
    if r > 200 and g > 200 and b > 190:
        return "white"
    if (
        60 <= r <= 150
        and 80 <= g <= 160
        and 100 <= b <= 180
        and b - r >= 25
        and g - r >= 10
        and b - g >= 8
    ):
        return "asphalt"
    if max(r, g, b) < 70:
        return "bg"
    return "other"


def adjacencies(pixels, size: int) -> dict:
    counts = {"lime_white": 0, "lime_asphalt": 0, "white_asphalt": 0}
    for y in range(size):
        for x in range(size):
            current = pixels[y][x]
            if current not in ("lime", "white"):
                continue
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if not (0 <= nx < size and 0 <= ny < size):
                    continue
                neighbor = pixels[ny][nx]
                if current == "lime" and neighbor == "white":
                    counts["lime_white"] += 1
                elif current == "lime" and neighbor == "asphalt":
                    counts["lime_asphalt"] += 1
                elif current == "white" and neighbor == "asphalt":
                    counts["white_asphalt"] += 1
    return counts


def lime_components(pixels, size: int) -> int:
    seen = [[False] * size for _ in range(size)]
    mask = [[pixels[y][x] == "lime" for x in range(size)] for y in range(size)]
    count = 0
    for y in range(size):
        for x in range(size):
            if not mask[y][x] or seen[y][x]:
                continue
            queue = deque([(x, y)])
            seen[y][x] = True
            area = 0
            while queue:
                cx, cy = queue.popleft()
                area += 1
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if 0 <= nx < size and 0 <= ny < size and mask[ny][nx] and not seen[ny][nx]:
                        seen[ny][nx] = True
                        queue.append((nx, ny))
            if area >= 2:
                count += 1
    return count


def inspect(path: Path) -> dict:
    img = Image.open(path).convert("RGB")
    report: dict = {
        "file": path.name,
        "size": list(img.size),
        "bytes": path.stat().st_size,
        "alpha": Image.open(path).mode,
    }
    draw = ImageDraw.Draw(img)
    bbox = None
    max_radius = 0.0
    for y in range(0, 512, 2):
        for x in range(0, 512, 2):
            if classify(*img.getpixel((x, y))) in ("white", "lime"):
                bbox = (x, y, x, y) if bbox is None else (
                    min(bbox[0], x), min(bbox[1], y), max(bbox[2], x), max(bbox[3], y)
                )
                max_radius = max(max_radius, ((x - 256) ** 2 + (y - 256) ** 2) ** 0.5)
    report["mark_bbox"] = bbox
    report["safe_area_ratio"] = round(max_radius / 256, 3)

    sizes = {}
    for size in SIZES:
        tile = img.resize((size, size), Image.LANCZOS)
        px = [[classify(*tile.getpixel((x, y))) for x in range(size)] for y in range(size)]
        flat = [c for row in px for c in row]
        total = size * size
        sizes[size] = {
            "white_pct": round(100 * flat.count("white") / total, 1),
            "lime_pct": round(100 * flat.count("lime") / total, 1),
            "asphalt_pct": round(100 * flat.count("asphalt") / total, 1),
            "lime_px": flat.count("lime"),
            "lime_components": lime_components(px, size),
            "edge_density": round(
                sum(tile.convert("L").filter(ImageFilter.FIND_EDGES).getdata()) / total, 2
            ),
        }
        if size == 512:
            report["adjacency_512"] = adjacencies(px, size)
    report["sizes"] = sizes
    report["contrast"] = {
        "white_on_bg": contrast(WHITE, BG),
        "lime_on_bg": contrast(LIME, BG),
        "white_on_lime": contrast(WHITE, LIME),
        "asphalt_on_bg": contrast(ASPHALT, BG),
        "asphalt_on_light": contrast(ASPHALT, LIGHT_PAGE),
        "asphalt_on_dark": contrast(ASPHALT, DARK_TG),
        "graphite_on_light": contrast(BG, LIGHT_PAGE),
        "graphite_on_dark": contrast(BG, DARK_TG),
    }
    return report


def main() -> None:
    base = Path("assets/brand")
    reports = [inspect(p) for p in sorted(base.glob("icon_v*_512.png"))]
    (base / "validation.json").write_text(json.dumps(reports, indent=2, ensure_ascii=False))

    print("| variant | safe area | 512 lime px | 48px lime px | 32px lime px | 32px comps | 32px edge |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for r in reports:
        s = r["sizes"]
        print(
            f"| {r['file'].split('_')[1]} | {r['safe_area_ratio']} | {s[512]['lime_px']} | "
            f"{s[48]['lime_px']} | {s[32]['lime_px']} | {s[32]['lime_components']} | {s[32]['edge_density']} |"
        )
    print()
    print("contrast:", reports[0]["contrast"])


if __name__ == "__main__":
    main()
