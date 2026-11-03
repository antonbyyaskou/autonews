#!/usr/bin/env python3
"""Render the static landing page from config/site.yaml.

Run from the repository root:

    .venv/bin/python tools/build_site.py
    .venv/bin/python -m http.server 8080 -d site/public

The generated site is a build artifact; only templates and config are edited.
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
import sys
from datetime import date
from pathlib import Path
from string import Template

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "site.yaml"
TEMPLATES = ROOT / "site" / "templates"
ICON = ROOT / "assets" / "brand" / "icon_512.png"
OUT = ROOT / "site" / "public"

REQUIRED = ("base_url", "channel", "title", "description")


class BuildError(SystemExit):
    pass


def load_config(path: Path) -> dict:
    if not path.exists():
        raise BuildError(f"{path}: file not found")
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    missing = [key for key in REQUIRED if not str(config.get(key, "")).strip()]
    if missing:
        raise BuildError(f"{path}: missing {', '.join(missing)}")

    base_url = str(config["base_url"]).strip().rstrip("/")
    if not base_url.startswith(("https://", "http://")):
        raise BuildError(f"{path}: base_url must start with https://")

    channel = str(config["channel"]).strip().lstrip("@")
    if not channel or "/" in channel or " " in channel:
        raise BuildError(f"{path}: channel must be a bare username")

    config["base_url"] = base_url
    config["channel"] = channel
    return config


def verification_meta(config: dict) -> str:
    tags = []
    for name, key in (
        ("yandex-verification", "yandex_verification"),
        ("google-site-verification", "google_verification"),
    ):
        value = str(config.get(key) or "").strip()
        if value:
            tags.append(
                f'<meta name="{name}" content="{html.escape(value, quote=True)}">'
            )
    return "\n".join(tags)


def render(config: dict) -> dict[str, str]:
    channel = config["channel"]
    description = str(config["description"]).strip()
    values = {
        "base_url": config["base_url"],
        "channel": channel,
        "channel_url": f"https://t.me/{channel}",
        "preview_url": f"https://t.me/s/{channel}",
        "title": html.escape(str(config["title"]).strip(), quote=True),
        "description": html.escape(description, quote=True),
        "description_json": json.dumps(description, ensure_ascii=False),
        "verification_meta": verification_meta(config),
        "lastmod": date.today().isoformat(),
    }
    rendered = {}
    for template_path in sorted(TEMPLATES.iterdir()):
        if not template_path.is_file():
            continue
        output_name = template_path.name.removesuffix(".tmpl")
        rendered[output_name] = Template(
            template_path.read_text(encoding="utf-8")
        ).substitute(values)
    return rendered


def build(config_path: Path, out_dir: Path) -> list[Path]:
    config = load_config(config_path)
    if ".example" in config["base_url"]:
        print(
            "warning: base_url is still a placeholder; "
            "edit config/site.yaml before deploying",
            file=sys.stderr,
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, content in render(config).items():
        path = out_dir / name
        path.write_text(content, encoding="utf-8")
        written.append(path)

    if not ICON.exists():
        raise BuildError(f"{ICON}: icon not found")
    icon_path = out_dir / "icon.png"
    shutil.copyfile(ICON, icon_path)
    written.append(icon_path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    try:
        written = build(args.config, args.out)
    except BuildError as exc:
        print(exc, file=sys.stderr)
        return 1
    for path in written:
        print(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
