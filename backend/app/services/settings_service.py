from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Stored next to the backend package, in data/settings.json
_SETTINGS_FILE = Path(__file__).resolve().parents[2] / "data" / "settings.json"

_DEFAULTS: dict[str, Any] = {
    # LLM
    "llm_url":          "http://localhost:1234/v1",
    "llm_model":        "google/gemma-4-e4b",
    "llm_api_key":      "lm-studio",
    # Neo4j
    "neo4j_uri":        "bolt://localhost:7687",
    "neo4j_password":   "password",
    # Email
    "email":            "",
    "email_password":   "",
    "imap_server":      "",
    # Telegram
    "telegram_token":   "",
    "telegram_chat_id": "",
    # Explorer
    "explorer_interval":   30,  # minutes
    "search_prompt_hint":  "",  # consigne libre pour orienter le LLM lors de la recherche
    # AI API Keys
    "google_api_key":   "",
}


def load() -> dict[str, Any]:
    """Return persisted settings merged with defaults."""
    merged = dict(_DEFAULTS)
    if _SETTINGS_FILE.exists():
        try:
            saved = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
            merged = {**_DEFAULTS, **saved}
        except Exception:
            pass
    _sync_env(merged)
    return merged


def save(data: dict[str, Any]) -> dict[str, Any]:
    """Persist settings and return the merged result."""
    current = load()
    merged = {**current, **{k: v for k, v in data.items() if k in _DEFAULTS}}
    _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_FILE.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Reflect critical values in runtime env so agents pick them up immediately
    _sync_env(merged)
    return merged


def _sync_env(settings: dict[str, Any]) -> None:
    """Push saved values into os.environ so running agents see them instantly."""
    mapping = {
        "llm_url":          "MODEL_BASE_URL",
        "llm_model":        "MODEL",
        "llm_api_key":      "API_KEY",
        "neo4j_uri":        "NEO4J_URI",
        "neo4j_password":   "NEO4J_PASSWORD",
        "email":            "MAILER_EMAIL",
        "email_password":   "MAILER_PASSWORD",
        "imap_server":      "MAILER_IMAP_SERVER",
        "telegram_token":   "TELEGRAM_BOT_TOKEN",
        "telegram_chat_id": "TELEGRAM_CHAT_ID",
        "explorer_interval": "EXPLORER_INTERVAL",
        "google_api_key":   "GOOGLE_API_KEY",
    }
    for key, env_var in mapping.items():
        value = settings.get(key, "")
        if value:
            os.environ[env_var] = str(value)
