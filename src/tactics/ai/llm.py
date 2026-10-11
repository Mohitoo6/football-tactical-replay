"""Call a free-tier LLM through the OpenAI-compatible API (DECISIONS.md, D4, D5).

- Providers are read from .env and tried in order (two Gemini models, then Groq, then OpenRouter).
- Busy or rate-limited responses (429, 5xx, timeouts) are retried with a pause;
  other errors (bad key, unknown model) skip straight to the next provider.
- Each explanation is cached next to its clip, keyed by a hash of the prompt and
  the facts, so the same clip never costs a second request.
- If a check function finds items that are not in the facts, the model gets one
  chance to rewrite its answer without them (the first answer is kept in the record).
"""

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError, APITimeoutError, InternalServerError, OpenAI, RateLimitError

from tactics.ai.prompt import PROMPT_VERSION, SYSTEM_PROMPT, repair_message, user_message

ENV_PREFIXES = ("LLM", "FALLBACK1", "FALLBACK2", "FALLBACK3")
RETRYABLE = (RateLimitError, InternalServerError, APIConnectionError, APITimeoutError)
ATTEMPTS_PER_PROVIDER = 3
FIRST_PAUSE_S = 5  # then 10 s


@dataclass
class Provider:
    name: str
    base_url: str
    model: str
    api_key: str
    reasoning_effort: str | None = None


class AllProvidersFailed(RuntimeError):
    pass


def providers_from_env(env_file: str | Path = ".env") -> list[Provider]:
    """Providers configured in .env (see .env.example), in the order they should be tried."""
    load_dotenv(env_file)
    providers = []
    for prefix in ENV_PREFIXES:
        values = {field: os.environ.get(f"{prefix}_{field.upper()}") for field in ("base_url", "model", "api_key")}
        if all(values.values()):
            providers.append(Provider(prefix.lower(), **values,
                                      reasoning_effort=os.environ.get(f"{prefix}_REASONING_EFFORT") or None))
    return providers


def complete(system: str, user: str, providers: list[Provider], client_factory=OpenAI, sleep=time.sleep) -> tuple[str, Provider]:
    """Return the first non-empty answer and the provider that gave it."""
    errors = []
    for provider in providers:
        client = client_factory(api_key=provider.api_key, base_url=provider.base_url, max_retries=0, timeout=120)
        extra = {"reasoning_effort": provider.reasoning_effort} if provider.reasoning_effort else {}
        for attempt in range(ATTEMPTS_PER_PROVIDER):
            try:
                response = client.chat.completions.create(
                    model=provider.model,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    temperature=0.2,
                    max_tokens=2000,  # room for "thinking" tokens plus a ~180-word answer
                    **extra,
                )
            except RETRYABLE as error:
                errors.append(f"{provider.name}: {type(error).__name__}")
                if attempt < ATTEMPTS_PER_PROVIDER - 1:
                    sleep(FIRST_PAUSE_S * 2 ** attempt)
                continue
            except APIStatusError as error:  # e.g. 401 bad key, 404 unknown model: retrying will not help
                errors.append(f"{provider.name}: {type(error).__name__} {error.status_code}")
                break
            text = (response.choices[0].message.content or "").strip()
            if text:
                return text, provider
            errors.append(f"{provider.name}: empty answer")
            break
    raise AllProvidersFailed("; ".join(errors) or "no providers configured in .env")


def cache_key(system: str, user: str) -> str:
    """Changes whenever the prompt, its version or the facts change."""
    return hashlib.sha256(f"{PROMPT_VERSION}\n{system}\n{user}".encode()).hexdigest()


def explain(summary: dict, cache_path: Path, providers: list[Provider] | None = None, complete_fn=complete,
            check=None) -> dict:
    """Explanation for a summary: from the cache if it is still valid, otherwise from an LLM (then cached).

    `check(text) -> list of problems` (e.g. grounding); one repair attempt is made if it finds any.
    """
    user = user_message(summary)
    key = cache_key(SYSTEM_PROMPT, user)
    cache_path = Path(cache_path)
    if cache_path.exists():
        cached = json.loads(cache_path.read_text())
        # Reuse only if facts and prompt are unchanged and the cached answer still passes the check.
        if cached.get("cache_key") == key and not (check and check(cached["text"])):
            return {**cached, "from_cache": True}

    providers = providers if providers is not None else providers_from_env()
    text, provider = complete_fn(SYSTEM_PROMPT, user, providers)
    repair = None
    problems = check(text) if check else []
    if problems:
        new_text, new_provider = complete_fn(SYSTEM_PROMPT, repair_message(user, text, problems), providers)
        new_problems = check(new_text)
        if len(new_problems) < len(problems):  # keep the rewrite only if it is better
            repair = {"first_text": text, "first_model": provider.model, "first_problems": problems}
            text, provider = new_text, new_provider
    record = {
        "cache_key": key,
        "prompt_version": PROMPT_VERSION,
        "provider": provider.name,
        "model": provider.model,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "text": text,
        "repair": repair,
    }
    cache_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    return {**record, "from_cache": False}
