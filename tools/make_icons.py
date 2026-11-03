from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

S = 1024
BG = (14, 17, 19, 255)
WHITE = (242, 244, 243, 255)
LIME = (200, 255, 46, 255)
ASPHALT = (90, 112, 130, 255)
OUT = Path("assets/brand")

APEX = (512, 236)
LEFT_BASE = (286, 806)
RIGHT_BASE = (738, 806)
STROKE = 118
BAR = (320, 620, 704, 700)
COUNTER = (430, 330, 610, 600)
RING_RADIUS = 466
RING_WIDTH = 22

BOLT_BAR_WIDE = [(300, 620), (520, 584), (520, 544), (732, 652), (520, 760), (520, 720), (300, 700)]
BOLT_BAR_SHORT = [(344, 626), (516, 596), (516, 558), (700, 652), (516, 746), (516, 708), (344, 692)]

BOLT_UNIT = [
    (0.52, 0.00),
    (0.10, 0.56),
    (0.44, 0.56),
    (0.28, 1.00),
    (0.92, 0.42),
    (0.56, 0.42),
    (0.72, 0.00),
]

V10_SCALE = 1.06
V10_BOLT_BOX = (388, 292, 664, 700)
V11_KEYLINE = 24
V11_RIM = 36


def bolt_points(box):
    x0, y0, x1, y1 = box
    return [(x0 + u * (x1 - x0), y0 + v * (y1 - y0)) for u, v in BOLT_UNIT]


def scale_point(point, scale: float = V10_SCALE):
    return (512 + (point[0] - 512) * scale, 512 + (point[1] - 512) * scale)


def scale_box(box, scale: float = V10_SCALE):
    x0, y0 = scale_point((box[0], box[1]), scale)
    x1, y1 = scale_point((box[2], box[3]), scale)
    return (x0, y0, x1, y1)


def expand_box(box, amount: float):
    return (box[0] - amount, box[1] - amount, box[2] + amount, box[3] + amount)


APEX10 = scale_point(APEX)
LEFT_BASE10 = scale_point(LEFT_BASE)
RIGHT_BASE10 = scale_point(RIGHT_BASE)
STROKE10 = STROKE * V10_SCALE
BAR10 = scale_box(BAR)
BOLT10 = scale_box(V10_BOLT_BOX)


def base_canvas() -> Image.Image:
    img = Image.new("RGBA", (S, S), BG)
    return img


def draw_a(draw, color):
    draw.line([LEFT_BASE, APEX, RIGHT_BASE], fill=color, width=STROKE, joint="curve")


def draw_bar(draw, color):
    draw.rectangle(BAR, fill=color)


def draw_bolt(draw, color, box):
    draw.polygon(bolt_points(box), fill=color)


def draw_ring(draw, color):
    d = RING_RADIUS
    draw.ellipse((S // 2 - d, S // 2 - d, S // 2 + d, S // 2 + d), outline=color, width=RING_WIDTH)


def _rounded(point):
    return (round(point[0]), round(point[1]))


def draw_a10(draw, color):
    draw.line(
        [_rounded(LEFT_BASE10), _rounded(APEX10), _rounded(RIGHT_BASE10)],
        fill=color,
        width=round(STROKE10),
        joint="curve",
    )


def draw_bar10(draw, color):
    draw.rectangle(_rounded((BAR10[0], BAR10[1])) + _rounded((BAR10[2], BAR10[3])), fill=color)


def draw_rect(draw, box, color):
    draw.rectangle(_rounded((box[0], box[1])) + _rounded((box[2], box[3])), fill=color)


def draw_v11(draw):
    draw.ellipse((0, 0, S - 1, S - 1), fill=ASPHALT)
    r = S // 2 - V11_RIM
    draw.ellipse((S // 2 - r, S // 2 - r, S // 2 + r, S // 2 + r), fill=BG)
    draw_a10(draw, WHITE)
    draw_rect(draw, expand_box(BAR10, V11_KEYLINE), BG)
    draw.polygon(bolt_points(expand_box(BOLT10, V11_KEYLINE)), fill=BG)
    draw_bar10(draw, LIME)
    draw_bolt(draw, LIME, BOLT10)


VARIANTS = {
    "v1": ("A + bar + bolt", lambda d: (draw_a(d, WHITE), draw_bar(d, LIME), draw_bolt(d, LIME, COUNTER))),
    "v2": ("A + bar", lambda d: (draw_a(d, WHITE), draw_bar(d, LIME))),
    "v3": ("lime A + bolt", lambda d: (draw_a(d, LIME), draw_bolt(d, WHITE, COUNTER))),
    "v4": ("A + bar + ring", lambda d: (draw_a(d, WHITE), draw_ring(d, LIME), draw_bar(d, LIME))),
    "v5": ("A + wide bolt bar", lambda d: (draw_a(d, WHITE), d.polygon(BOLT_BAR_WIDE, fill=LIME))),
    "v6": ("A + short bolt bar", lambda d: (draw_a(d, WHITE), d.polygon(BOLT_BAR_SHORT, fill=LIME))),
    "v7": ("A + tall lime bolt", lambda d: (draw_a(d, WHITE), draw_bolt(d, LIME, (408, 320, 616, 724)))),
    "v8": ("A + bar + overlapping bolt", lambda d: (draw_a(d, WHITE), draw_bar(d, LIME), draw_bolt(d, LIME, (430, 296, 620, 700)))),
    "v9": ("A + bar + bold bolt", lambda d: (draw_a(d, WHITE), draw_bar(d, LIME), draw_bolt(d, LIME, (392, 300, 652, 640)))),
    "v10": ("A + connected bolt bar", lambda d: (draw_a10(d, WHITE), draw_bar10(d, LIME), draw_bolt(d, LIME, BOLT10))),
    "v11": ("approved: keyline + asphalt ring", draw_v11),
}


def circle_mask(img: Image.Image, size: int) -> Image.Image:
    scaled = img.resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    mask = mask.resize((size, size), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(scaled, (0, 0), mask)
    return out


def svg(variant: str) -> str:
    def line(a, b, color, width=STROKE):
        a, b = _rounded(a), _rounded(b)
        return (
            f'<line x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}" stroke="{color}" '
            f'stroke-width="{round(width)}" stroke-linecap="square"/>'
        )

    def rect(box, color):
        return (
            f'<rect x="{round(box[0])}" y="{round(box[1])}" '
            f'width="{round(box[2]-box[0])}" height="{round(box[3]-box[1])}" fill="{color}"/>'
        )

    def polygon(box, color):
        pts = " ".join(f"{x:.0f},{y:.0f}" for x, y in bolt_points(box))
        return f'<polygon points="{pts}" fill="{color}"/>'

    a_white = line(LEFT_BASE, APEX, "#F2F4F3") + line(APEX, RIGHT_BASE, "#F2F4F3")
    a_white10 = line(LEFT_BASE10, APEX10, "#F2F4F3", STROKE10) + line(
        APEX10, RIGHT_BASE10, "#F2F4F3", STROKE10
    )
    bar10 = rect(BAR10, "#C8FF2E")
    keyline_bar = rect(expand_box(BAR10, V11_KEYLINE), "#0E1113")
    keyline_bolt = polygon(expand_box(BOLT10, V11_KEYLINE), "#0E1113")
    bolt10 = polygon(BOLT10, "#C8FF2E")
    a_lime = line(LEFT_BASE, APEX, "#C8FF2E") + line(APEX, RIGHT_BASE, "#C8FF2E")
    bar = f'<rect x="{BAR[0]}" y="{BAR[1]}" width="{BAR[2]-BAR[0]}" height="{BAR[3]-BAR[1]}" fill="#C8FF2E"/>'
    points = " ".join(f"{x:.0f},{y:.0f}" for x, y in bolt_points(COUNTER))
    wide = " ".join(f"{x},{y}" for x, y in BOLT_BAR_WIDE)
    short = " ".join(f"{x},{y}" for x, y in BOLT_BAR_SHORT)
    bolt_lime = f'<polygon points="{points}" fill="#C8FF2E"/>'
    bolt_white = f'<polygon points="{points}" fill="#F2F4F3"/>'
    ring = (
        f'<circle cx="512" cy="512" r="{RING_RADIUS}" fill="none" stroke="#C8FF2E" stroke-width="{RING_WIDTH}"/>'
    )
    body = {
        "v1": a_white + bar + bolt_lime,
        "v2": a_white + bar,
        "v3": a_lime + bolt_white,
        "v4": a_white + ring + bar,
        "v5": a_white + f'<polygon points="{wide}" fill="#C8FF2E"/>',
        "v6": a_white + f'<polygon points="{short}" fill="#C8FF2E"/>',
        "v7": a_white + '<polygon points="{}" fill="#C8FF2E"/>'.format(
            " ".join(f"{x:.0f},{y:.0f}" for x, y in bolt_points((408, 320, 616, 724)))
        ),
        "v8": a_white + bar + '<polygon points="{}" fill="#C8FF2E"/>'.format(
            " ".join(f"{x:.0f},{y:.0f}" for x, y in bolt_points((430, 296, 620, 700)))
        ),
        "v9": a_white + bar + '<polygon points="{}" fill="#C8FF2E"/>'.format(
            " ".join(f"{x:.0f},{y:.0f}" for x, y in bolt_points((392, 300, 652, 640)))
        ),
        "v10": a_white10 + bar10 + bolt10,
        "v11": a_white10 + keyline_bar + keyline_bolt + bar10 + bolt10,
    }[variant]
    r = 512 - V11_RIM
    background = {
        "v11": (
            '<rect width="1024" height="1024" fill="#0E1113"/>'
            '<circle cx="512" cy="512" r="512" fill="#5A7082"/>'
            f'<circle cx="512" cy="512" r="{r}" fill="#0E1113"/>'
        )
    }.get(variant, '<circle cx="512" cy="512" r="512" fill="#0E1113"/>')
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">'
        f"{background}{body}</svg>"
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    masters: dict[str, Image.Image] = {}
    for name, (label, draw) in VARIANTS.items():
        img = base_canvas()
        draw(ImageDraw.Draw(img))
        masters[name] = img
        img.resize((512, 512), Image.LANCZOS).save(OUT / f"icon_{name}_512.png")
        (OUT / f"icon_{name}.svg").write_text(svg(name))
        print(f"{name}: {label}")

    row_h = 208
    pad = 20
    cells = [("square", 192), ("circle", 192), ("circle", 96), ("circle", 48), ("circle", 32)]
    width = pad + sum(size for _, size in cells) + pad * len(cells)
    height = pad + row_h * len(VARIANTS)
    sheet = Image.new("RGBA", (width, height), (247, 247, 247, 255))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 17)
    except Exception:
        font = ImageFont.load_default()

    for row, (name, (label, _)) in enumerate(VARIANTS.items()):
        y = pad + row * row_h
        draw.text((pad, y - 2), f"{name}  {label}", fill=(30, 30, 30), font=font)
        x = pad
        img = masters[name]
        for kind, size in cells:
            tile = img.resize((size, size), Image.LANCZOS) if kind == "square" else circle_mask(img, size)
            sheet.paste(tile, (x, y + 24), tile)
            x += size + pad

    out = OUT / "preview_sheet.png"
    sheet.save(out)
    print("wrote", out)

    dark_cells = [("square", 192), ("circle", 192), ("circle", 96), ("circle", 60), ("circle", 48), ("circle", 32)]
    dark_width = pad + sum(size for _, size in dark_cells) + pad * len(dark_cells)
    dark_sheet = Image.new("RGBA", (dark_width, pad + row_h), (23, 33, 43, 255))
    dark_draw = ImageDraw.Draw(dark_sheet)
    dark_draw.text((pad, pad - 2), "v11 approved on Telegram dark (#17212B)", fill=(242, 244, 243), font=font)
    x = pad
    for kind, size in dark_cells:
        tile = (
            masters["v11"].resize((size, size), Image.LANCZOS)
            if kind == "square"
            else circle_mask(masters["v11"], size)
        )
        dark_sheet.paste(tile, (x, pad + 24), tile)
        x += size + pad
    dark_out = OUT / "preview_dark.png"
    dark_sheet.save(dark_out)
    print("wrote", dark_out)


if __name__ == "__main__":
    main()
