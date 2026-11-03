from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "build_site.py"
CONFIG = ROOT / "config" / "site.yaml"


def run_build(tmp_path: Path, config_path: Path | None = None) -> Path:
    out = tmp_path / "public"
    command = [sys.executable, str(SCRIPT), "--out", str(out)]
    if config_path is not None:
        command += ["--config", str(config_path)]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return out


def test_build_outputs_required_files(tmp_path):
    out = run_build(tmp_path)
    for name in ("index.html", "robots.txt", "sitemap.xml", "icon.png"):
        assert (out / name).is_file()


def test_landing_page_links_and_canonical(tmp_path):
    out = run_build(tmp_path)
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    base = str(config["base_url"]).rstrip("/")
    channel = str(config["channel"]).lstrip("@")

    page = (out / "index.html").read_text(encoding="utf-8")
    assert f'<link rel="canonical" href="{base}/">' in page
    assert f"https://t.me/{channel}" in page
    assert f"https://t.me/s/{channel}" in page

    sitemap = (out / "sitemap.xml").read_text(encoding="utf-8")
    assert f"<loc>{base}/</loc>" in sitemap

    robots = (out / "robots.txt").read_text(encoding="utf-8")
    assert f"Sitemap: {base}/sitemap.xml" in robots


def test_json_ld_is_valid(tmp_path):
    out = run_build(tmp_path)
    page = (out / "index.html").read_text(encoding="utf-8")
    match = re.search(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>', page, re.S
    )
    assert match
    data = json.loads(match.group(1))
    assert [node["@type"] for node in data["@graph"]] == ["WebSite", "Organization"]


def test_normalizes_base_url_and_channel(tmp_path):
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    config["base_url"] = "https://example.org/autonews/"
    config["channel"] = "@some_channel"
    path = tmp_path / "site.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")

    out = run_build(tmp_path, path)
    page = (out / "index.html").read_text(encoding="utf-8")
    assert '<link rel="canonical" href="https://example.org/autonews/">' in page
    assert "https://t.me/some_channel" in page
    assert "t.me/@some_channel" not in page


def test_rejects_missing_config(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--config",
            str(tmp_path / "missing.yaml"),
            "--out",
            str(tmp_path / "public"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "not found" in result.stderr
