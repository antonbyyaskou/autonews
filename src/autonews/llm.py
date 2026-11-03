from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .config import Settings
from .db import connect, now


@dataclass
class Completion:
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost: float
    allowance: float
    billing_source: str

    def as_usage(self) -> dict:
        return {
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost": self.cost,
            "allowance": self.allowance,
            "billing_source": self.billing_source,
        }


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base = settings.llm_base.rstrip("/")
        self.key = settings.llm_key
        if not self.key:
            raise LLMError("No LLM API key configured. Set OPENCODE_API_KEY or DEEPSEEK_API_KEY.")
        headers = {
            "Authorization": f"Bearer {self.key}",
            "User-Agent": settings.user_agent,
            "Content-Type": "application/json",
        }
        if settings.llm_provider == "go":
            headers["x-opencode-session"] = settings.session_id
        self.headers = headers

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        role: str = "generic",
        max_tokens: int = 1200,
        temperature: float = 0.3,
        json_mode: bool = False,
    ) -> Completion:
        model = model or self.settings.model_draft
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        last_error: Exception | None = None
        for attempt in range(self.settings.http_retries + 1):
            try:
                with httpx.Client(timeout=self.settings.http_timeout) as client:
                    resp = client.post(f"{self.base}/chat/completions", json=payload, headers=self.headers)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                if resp.status_code >= 400:
                    raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                data = resp.json()
                choice = (data.get("choices") or [{}])[0]
                text = (choice.get("message") or {}).get("content") or ""
                usage = data.get("usage") or {}
                opencode = usage.get("opencode") or {}
                completion = Completion(
                    text=text.strip(),
                    model=model,
                    prompt_tokens=int(usage.get("prompt_tokens") or 0),
                    completion_tokens=int(usage.get("completion_tokens") or 0),
                    cost=float(usage.get("cost") or 0),
                    allowance=float(opencode.get("allowance") or 0),
                    billing_source=str(opencode.get("billing_source") or self.settings.llm_provider),
                )
                self._record(role, completion)
                return completion
            except (httpx.HTTPError, LLMError, ValueError) as exc:
                last_error = exc
                if attempt < self.settings.http_retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
        raise LLMError(f"LLM request failed: {last_error}")

    def complete_json(self, messages: list[dict[str, str]], **kwargs: Any) -> tuple[dict, Completion]:
        completion = self.complete(messages, json_mode=True, **kwargs)
        text = completion.text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
            text = re.sub(r"\s*```$", "", text).strip()
        if not text:
            raise LLMError("empty completion")
        try:
            return json.loads(text), completion
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start : end + 1]), completion
                except json.JSONDecodeError:
                    pass
            raise LLMError(f"Model did not return JSON: {text[:200]}")

    def _record(self, role: str, completion: Completion) -> None:
        with connect() as conn:
            conn.execute(
                "INSERT INTO llm_usage (created_at, role, model, prompt_tokens, completion_tokens, cost, allowance, billing_source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    now(),
                    role,
                    completion.model,
                    completion.prompt_tokens,
                    completion.completion_tokens,
                    completion.cost,
                    completion.allowance,
                    completion.billing_source,
                ),
            )
