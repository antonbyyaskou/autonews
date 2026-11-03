from __future__ import annotations

import json
import math
from pathlib import Path

from make_icons import ASPHALT, BG, LIME, V11_KEYLINE, V11_RIM, WHITE

PALETTE = {
    "graphite": (BG, "#0E1113", "tile body and lime keyline"),
    "offwhite": (WHITE, "#F2F4F3", "the letter A"),
    "lime": (LIME, "#C8FF2E", "bolt and crossbar"),
    "asphalt": (ASPHALT, "#5A7082", "perimeter ring"),
}
BACKGROUNDS = {
    "white": ((255, 255, 255), "#FFFFFF"),
    "light_page": ((247, 247, 247), "#F7F7F7"),
    "black": ((0, 0, 0), "#000000"),
    "telegram_dark": ((23, 33, 43), "#17212B"),
    "android_dark": ((18, 18, 18), "#121212"),
}

CVD_MATRICES = {
    "protanopia": (
        (0.152286, 1.052583, -0.204868),
        (0.114503, 0.786281, 0.099216),
        (-0.003882, -0.048116, 1.051998),
    ),
    "deuteranopia": (
        (0.367322, 0.860646, -0.227968),
        (0.280085, 0.672501, 0.047413),
        (-0.011820, 0.042940, 0.968881),
    ),
    "tritanopia": (
        (1.255528, -0.076749, -0.178779),
        (-0.078411, 0.930809, 0.147602),
        (0.004733, 0.691367, 0.303900),
    ),
}


def rgb(color) -> tuple[int, int, int]:
    return tuple(int(c) for c in color[:3])


def linear(channel: int) -> float:
    value = channel / 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def luminance(color) -> float:
    r, g, b = (linear(c) for c in rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(first, second) -> float:
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return round((high + 0.05) / (low + 0.05), 2)


def simulate(color, kind: str) -> tuple[int, int, int]:
    if kind == "normal":
        return rgb(color)
    source = [linear(c) for c in rgb(color)]
    matrix = CVD_MATRICES[kind]
    simulated = [
        max(0.0, min(1.0, sum(matrix[row][column] * source[column] for column in range(3))))
        for row in range(3)
    ]

    def encode(value: float) -> int:
        gamma = 12.92 * value if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055
        return round(gamma * 255)

    return tuple(encode(value) for value in simulated)


def lab(color) -> tuple[float, float, float]:
    r, g, b = (linear(c) for c in rgb(color))
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def pivot(value: float) -> float:
        return value ** (1 / 3) if value > 0.008856 else 7.787 * value + 16 / 116

    fx, fy, fz = pivot(x), pivot(y), pivot(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e(first, second) -> float:
    l1, a1, b1 = lab(first)
    l2, a2, b2 = lab(second)
    c1, c2 = math.hypot(a1, b1), math.hypot(a2, b2)
    mean_c = (c1 + c2) / 2
    g = 0.5 * (1 - math.sqrt(mean_c**7 / (mean_c**7 + 25**7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360
    h2p = math.degrees(math.atan2(b2, a2p)) % 360
    dl = l2 - l1
    dc = c2p - c1p
    if c1p * c2p == 0:
        dh = 0
    elif abs(h2p - h1p) <= 180:
        dh = h2p - h1p
    elif h2p - h1p > 180:
        dh = h2p - h1p - 360
    else:
        dh = h2p - h1p + 360
    dH = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dh / 2))
    mean_l = (l1 + l2) / 2
    mean_cp = (c1p + c2p) / 2
    mean_h = h1p + h2p if abs(h1p - h2p) <= 180 else (h1p + h2p + 360) / 2
    t = (
        1
        - 0.17 * math.cos(math.radians(mean_h - 30))
        + 0.24 * math.cos(math.radians(2 * mean_h))
        + 0.32 * math.cos(math.radians(3 * mean_h + 6))
        - 0.20 * math.cos(math.radians(4 * mean_h - 63))
    )
    d_theta = 30 * math.exp(-(((mean_h - 275) / 25) ** 2))
    rc = 2 * math.sqrt(mean_cp**7 / (mean_cp**7 + 25**7))
    sl = 1 + 0.015 * (mean_l - 50) ** 2 / math.sqrt(20 + (mean_l - 50) ** 2)
    sc = 1 + 0.045 * mean_cp
    sh = 1 + 0.015 * mean_cp * t
    rt = -math.sin(math.radians(2 * d_theta)) * rc
    return round(
        math.sqrt((dl / sl) ** 2 + (dc / sc) ** 2 + (dH / sh) ** 2 + rt * (dc / sc) * (dH / sh)),
        2,
    )


def load_icon_adjacency() -> dict:
    from validate_icon import inspect

    for candidate in ("assets/brand/icon_512.png", "assets/brand/icon_v11_512.png"):
        path = Path(candidate)
        if path.exists():
            return inspect(path).get("adjacency_512", {})
    return {}


def main() -> None:
    palette = {name: rgb(color) for name, (color, _, _) in PALETTE.items()}
    backgrounds = {name: rgb(color) for name, (color, _) in BACKGROUNDS.items()}

    contrast_matrix = {
        first: {second: contrast(palette[first], palette[second]) for second in palette}
        for first in palette
    }
    background_contrast = {
        color: {name: contrast(palette[color], shades) for name, shades in backgrounds.items()}
        for color in palette
    }
    cvd = {}
    for first in palette:
        for second in palette:
            if first >= second:
                continue
            cvd[f"{first}_vs_{second}"] = {
                kind: delta_e(simulate(palette[first], kind), simulate(palette[second], kind))
                for kind in ("normal", "protanopia", "deuteranopia", "tritanopia")
            }

    adjacency = load_icon_adjacency()
    checks = [
        {
            "name": "offwhite A on graphite",
            "value": contrast_matrix["offwhite"]["graphite"],
            "minimum": 4.5,
            "status": "pass" if contrast_matrix["offwhite"]["graphite"] >= 4.5 else "fail",
        },
        {
            "name": "lime mark on graphite",
            "value": contrast_matrix["lime"]["graphite"],
            "minimum": 4.5,
            "status": "pass" if contrast_matrix["lime"]["graphite"] >= 4.5 else "fail",
        },
        {
            "name": "asphalt ring on light page",
            "value": background_contrast["asphalt"]["light_page"],
            "minimum": 3.0,
            "status": "pass" if background_contrast["asphalt"]["light_page"] >= 3.0 else "fail",
        },
        {
            "name": "asphalt ring on Telegram dark",
            "value": background_contrast["asphalt"]["telegram_dark"],
            "minimum": 3.0,
            "status": "pass" if background_contrast["asphalt"]["telegram_dark"] >= 3.0 else "fail",
        },
        {
            "name": "asphalt ring on graphite",
            "value": contrast_matrix["asphalt"]["graphite"],
            "minimum": 3.0,
            "status": "pass" if contrast_matrix["asphalt"]["graphite"] >= 3.0 else "fail",
        },
        {
            "name": "offwhite never touches lime",
            "value": adjacency.get("lime_white", 0),
            "maximum": 0,
            "status": "pass" if adjacency.get("lime_white", 0) == 0 else "fail",
        },
        {
            "name": "lime never touches asphalt ring",
            "value": adjacency.get("lime_asphalt", 0),
            "maximum": 0,
            "status": "pass" if adjacency.get("lime_asphalt", 0) == 0 else "fail",
        },
        {
            "name": "offwhite never touches asphalt ring",
            "value": adjacency.get("white_asphalt", 0),
            "maximum": 0,
            "status": "pass" if adjacency.get("white_asphalt", 0) == 0 else "fail",
        },
    ]

    report = {
        "palette": {
            name: {"hex": hex_value, "role": role, "luminance": round(luminance(color), 4)}
            for name, (color, hex_value, role) in PALETTE.items()
        },
        "contrast": contrast_matrix,
        "background_contrast": background_contrast,
        "cvd_delta_e": cvd,
        "checks": checks,
        "icon_v11_adjacency": adjacency,
        "notes": [
            "offwhite vs lime is 1.07:1 and is forbidden as a direct pair.",
            f"v11 separates every lime edge from offwhite with a {V11_KEYLINE} px graphite keyline.",
            f"The {V11_RIM} px asphalt ring keeps the circular edge above 3:1 on light and dark surfaces.",
        ],
    }
    output = Path("assets/brand/palette.json")
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print("| check | value | limit | status |")
    print("| --- | --- | --- | --- |")
    for check in checks:
        limit = check.get("minimum", check.get("maximum"))
        print(f"| {check['name']} | {check['value']} | {limit} | {check['status']} |")
    print()
    print("contrast:", {name: contrast_matrix[name] for name in ("offwhite", "lime", "asphalt")})
    print("wrote", output)


if __name__ == "__main__":
    main()
