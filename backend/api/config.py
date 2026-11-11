"""Settings read from the environment, and paths inside backend/."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import httpx

VERSION = "1.4.0"
# backend/ — the Python project root (contains pyproject.toml, knowledge/, data/).
BACKEND_DIR = Path(__file__).resolve().parents[1]


def database_url() -> str:
    return os.getenv("DATABASE_URL", "")


def backup_directory() -> Path:
    value = os.getenv("HAEDAP_BACKUP_DIR")
    return Path(value).resolve() if value else BACKEND_DIR / "data/backups"


def allowed_hosts() -> set[str]:
    hosts = {"127.0.0.1", "localhost"}
    hosts.update(item.strip().lower() for item in os.getenv("HAEDAP_ALLOWED_HOSTS", "").split(",") if item.strip())
    return hosts


MINDLOGIC_GATEWAY_HOST = "factchat-cloud.mindlogic.ai"


@dataclass(frozen=True)
class LLMSettings:
    base_url: str
    model: str
    api_key: str = field(repr=False)
    response_format: str = "text"
    # Path appended to base_url; Mindlogic's documented gateway route ends with "/".
    completions_path: str = "/chat/completions"
    generation_timeout: int = 60
    max_tokens: int | None = None
    enable_thinking: bool | None = None


def llm_settings() -> LLMSettings | None:
    """Resolve the same settings for health and generation; never contact a model here."""
    base = (os.getenv("LLM_API_BASE_URL") or "").strip() or "https://api.openai.com/v1"
    model = (os.getenv("OPENAI_MODEL") or "").strip()
    output_format = (os.getenv("LLM_RESPONSE_FORMAT") or "").strip() or "text"
    if not model or output_format not in {"text", "json_object", "json_schema"}:
        return None
    if any(character.isspace() for character in base) or "?" in base or "#" in base:
        return None
    try:
        url = httpx.URL(base)
        if url.scheme not in {"http", "https"} or not url.host or url.userinfo:
            return None
    except (httpx.InvalidURL, ValueError):
        return None

    # Select credentials only after parsing the destination; paths and lookalike
    # hostnames must never cause a provider's secret to reach another server.
    hostname = url.host.lower().rstrip(".")
    completions_path = "/chat/completions"
    if hostname == "api.openai.com":
        key_name = "OPENAI_API_KEY"
    elif hostname == "dongguk.edu" or hostname.endswith(".dongguk.edu"):
        key_name = "DONGUK_AI_CHAT_API_KEY"
    elif hostname == MINDLOGIC_GATEWAY_HOST:
        # Dongguk AI Chat's API gateway is operated by Mindlogic (ADR 0014). Exact host only.
        key_name = "DONGUK_AI_CHAT_API_KEY"
        completions_path = "/chat/completions/"
    else:
        key_name = None
    key = (os.getenv(key_name) or "").strip() if key_name else ""
    if key_name and not key:
        return None
    try:
        timeout=int(os.getenv('LLM_GENERATION_TIMEOUT_SECONDS','').strip() or '60')
        maximum=os.getenv('LLM_MAX_TOKENS','').strip()
        maximum=int(maximum) if maximum else None
        thinking=os.getenv('LLM_ENABLE_THINKING','').strip().lower()
        if not 1<=timeout<=90 or maximum is not None and not 32<=maximum<=4096 or thinking not in ('','true','false'):
            return None
    except ValueError:return None
    return LLMSettings(str(url).rstrip("/"), model, key, output_format, completions_path,
                       timeout,maximum,None if not thinking else thinking=='true')


def ask_timeout_ms():
    settings=llm_settings()
    return max(32000,(settings.generation_timeout+35)*1000) if settings else 32000


def llm_configured() -> bool:
    return llm_settings() is not None
