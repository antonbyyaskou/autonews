from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
MEDIA_DIR = DATA_DIR / "media"
DB_PATH = DATA_DIR / "autonews.db"
OPENCODE_AUTH = Path.home() / ".local" / "share" / "opencode" / "auth.json"


def load_dotenv(path: Path = PROJECT_ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _opencode_key() -> str:
    env = os.environ.get("OPENCODE_API_KEY", "").strip()
    if env:
        return env
    try:
        import json

        data = json.loads(OPENCODE_AUTH.read_text())
        for provider in ("opencode", "opencode-go"):
            entry = data.get(provider) or {}
            if entry.get("key"):
                return str(entry["key"])
    except Exception:
        pass
    return ""


@dataclass
class Settings:
    telegram_bot_token: str = field(default="", repr=False)
    telegram_channel_id: str = ""
    telegram_operator_id: int = 0
    llm_provider: str = "go"
    llm_base_go: str = "https://opencode.ai/inference/go/openai/v1"
    llm_base_deepseek: str = "https://api.deepseek.com/v1"
    llm_key_go: str = field(default="", repr=False)
    llm_key_deepseek: str = field(default="", repr=False)
    user_agent: str = "autonews/0.1"
    fetch_user_agent: str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    session_id: str = "autonews-local"
    model_score: str = "deepseek-v4.1-flash"
    model_draft: str = "deepseek-v4.1-flash"
    model_verify: str = "deepseek-v4.1-flash"
    http_timeout: float = 25.0
    http_retries: int = 2
    max_articles_per_extract: int = 60
    max_stories_per_score: int = 80
    max_drafts_per_run: int = 40
    score_threshold: int = 45
    cluster_window_hours: int = 72
    cluster_threshold: float = 0.42
    media_max_bytes: int = 45 * 1024 * 1024
    post_min_chars: int = 280
    post_max_chars: int = 600
    confirm_ttl_seconds: int = 600

    @property
    def llm_base(self) -> str:
        return self.llm_base_deepseek if self.llm_provider == "deepseek" else self.llm_base_go

    @property
    def llm_key(self) -> str:
        return self.llm_key_deepseek if self.llm_provider == "deepseek" else self.llm_key_go


def _yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def load_settings() -> Settings:
    load_dotenv()
    raw = _yaml(CONFIG_DIR / "settings.yaml")
    s = Settings()
    for key, value in raw.items():
        if hasattr(s, key) and not key.startswith("_"):
            setattr(s, key, value)
    s.llm_provider = os.environ.get("LLM_PROVIDER", s.llm_provider).lower()
    s.llm_key_go = _opencode_key()
    s.llm_key_deepseek = os.environ.get("DEEPSEEK_API_KEY", s.llm_key_deepseek)
    s.telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", s.telegram_bot_token)
    s.telegram_channel_id = os.environ.get("TELEGRAM_CHANNEL_ID", s.telegram_channel_id)
    op_id = os.environ.get("TELEGRAM_OPERATOR_ID")
    if op_id:
        s.telegram_operator_id = int(op_id)
    s.user_agent = os.environ.get("AUTONEWS_USER_AGENT", s.user_agent)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    return s


def load_sources() -> list[dict]:
    data = _yaml(CONFIG_DIR / "sources.yaml")
    return data.get("sources", [])


def load_style() -> str:
    path = CONFIG_DIR / "style.md"
    return path.read_text() if path.exists() else ""
