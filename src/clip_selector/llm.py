"""LLM call wrapper with Groq rate limiting and response caching."""
import hashlib
import time
from typing import List

from ..cache import cache_get, cache_set
from ..config import settings

GROQ_TPM_LIMIT = 12_000
_groq_token_log: List[tuple] = []  # (timestamp, token_count)


def _groq_rate_wait(estimated_tokens: int) -> None:
    now = time.monotonic()
    while _groq_token_log and now - _groq_token_log[0][0] > 60:
        _groq_token_log.pop(0)
    used = sum(t for _, t in _groq_token_log)
    if used + estimated_tokens > GROQ_TPM_LIMIT:
        oldest = _groq_token_log[0][0] if _groq_token_log else now
        wait = 60 - (now - oldest) + 1
        if wait > 0:
            print(f"   Groq rate limit: waiting {wait:.0f}s to stay under {GROQ_TPM_LIMIT} TPM...")
            time.sleep(wait)


def _groq_rate_record(tokens: int) -> None:
    _groq_token_log.append((time.monotonic(), tokens))


def _estimate_tokens(text: str) -> int:
    return len(text) // 3


def call_llm(transcript_text: str, system_prompt: str = "") -> str:
    """Call the configured LLM with caching. Returns raw text response."""
    cache_key = hashlib.sha256(
        f"{settings.llm_provider}:{system_prompt}:{transcript_text}".encode()
    ).hexdigest()[:16]
    cached = cache_get("llm", cache_key)
    if cached is not None:
        return cached

    if settings.llm_provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": transcript_text}],
        )
        result = "".join(b.text for b in response.content if b.type == "text").strip()

    elif settings.llm_provider == "groq":
        from groq import Groq
        estimated = _estimate_tokens(system_prompt + transcript_text) + 2000
        _groq_rate_wait(estimated)
        client = Groq(api_key=settings.groq_api_key)
        for attempt in range(3):
            try:
                response = client.chat.completions.create(
                    model=settings.groq_model,
                    max_tokens=2000,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": transcript_text},
                    ],
                )
                break
            except Exception as e:
                if "429" in str(e) or "rate" in str(e).lower():
                    wait = 30 * (attempt + 1)
                    print(f"   Groq rate limited, retrying in {wait}s (attempt {attempt + 1}/3)...")
                    time.sleep(wait)
                else:
                    raise
        else:
            raise RuntimeError("Groq rate limit: failed after 3 retries")
        actual = getattr(response, "usage", None)
        _groq_rate_record(actual.total_tokens if actual else estimated)
        result = response.choices[0].message.content.strip()

    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r}. Use 'anthropic' or 'groq'.")

    cache_set("llm", cache_key, result)
    return result
