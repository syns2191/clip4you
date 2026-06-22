"""
Uses an LLM to read the timestamped transcript and pick the segments most
likely to work as standalone short-form clips.

Switch providers by setting LLM_PROVIDER=anthropic or LLM_PROVIDER=groq in .env.
"""
import hashlib
import json
import time
from dataclasses import dataclass
from typing import List

from .config import settings
from .cache import cache_get, cache_set
from .transcribe import Segment

GROQ_TPM_LIMIT = 12_000
_groq_token_log: List[tuple] = []  # (timestamp, token_count)


def _groq_rate_wait(estimated_tokens: int) -> None:
    """Wait if needed to stay under Groq's 12k tokens-per-minute limit."""
    now = time.monotonic()
    # Expire entries older than 60s
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

CHUNK_SECONDS = 20 * 60  # process the transcript in ~20 minute windows

SYSTEM_PROMPT = """You are an expert short-form video editor who has cut \
thousands of viral TikTok/YouTube Shorts/Reels clips from long-form gaming \
and commentary videos. Given a timestamped transcript window, identify the \
segments that would make the strongest standalone clips.

Each transcript line shows [start - end] in seconds. Use these exact \
timestamps for your clip boundaries — always start at the beginning of a \
sentence and end at the end of a sentence. Never cut mid-sentence.

A good clip:
- Has a clear hook in the first 1-3 seconds (a question, a bold claim, a \
shocking moment) so it doesn't need context from earlier in the video
- MUST be between {min_s} and {max_s} seconds long. This is a hard \
requirement. Do NOT return clips shorter than {min_s} seconds. Include \
enough surrounding sentences (setup before, reactions after) to reach \
at least {min_s} seconds.
- Has a self-contained beat: setup, escalation, payoff -- or a single \
strong emotional moment (funny, suspenseful, insightful, shocking)
- The last sentence should be a natural ending — a punchline, a reaction, \
a conclusion. Never cut off before the payoff lands.
- Does not rely on the viewer having watched anything before this timestamp

Return ONLY valid JSON, no markdown fences, no commentary. Schema:
{{
  "clips": [
    {{
      "start": <float seconds>,
      "end": <float seconds>,
      "title": "<short punchy title, max 8 words>",
      "hook_text": "<on-screen top-text hook, max 6 words>",
      "category": "<one of: funniest, suspenseful, best_hook, insightful, most_engaging>",
      "emoji": "<single emoji that fits the punchline moment, e.g. 😂 🔥 😱 💯 😎 💀 🤯>",
      "score": <integer 1-100, your confidence this goes viral>,
      "reason": "<one sentence why this works>"
    }}
  ]
}}

If nothing in this window is clip-worthy, return {{"clips": []}}.
""".format(min_s=settings.clip_min_seconds, max_s=settings.clip_max_seconds)


CATEGORY_EMOJI = {
    "funniest": "\U0001F602",
    "suspenseful": "\U0001F631",
    "best_hook": "\U0001F525",
    "insightful": "\U0001F4AF",
    "most_engaging": "\U0001F929",
}


@dataclass
class ClipCandidate:
    start: float
    end: float
    title: str
    hook_text: str
    category: str
    score: int
    reason: str
    emoji: str = ""

    def __post_init__(self):
        if not self.emoji:
            self.emoji = CATEGORY_EMOJI.get(self.category, "\U0001F525")


def _segments_to_text(segments: List[Segment]) -> str:
    return "\n".join(f"[{seg.start:.1f}s - {seg.end:.1f}s] {seg.text}" for seg in segments)


def _chunk_segments(segments: List[Segment]) -> List[List[Segment]]:
    if not segments:
        return []
    video_duration = segments[-1].end - segments[0].start
    # Don't split short videos — one LLM call is enough
    if video_duration <= CHUNK_SECONDS * 1.5:
        return [segments]
    chunks: List[List[Segment]] = []
    current: List[Segment] = []
    chunk_start = segments[0].start
    for seg in segments:
        if seg.start - chunk_start > CHUNK_SECONDS and current:
            chunks.append(current)
            current = []
            chunk_start = seg.start
        current.append(seg)
    if current:
        chunks.append(current)
    return chunks


def _estimate_tokens(text: str) -> int:
    return len(text) // 3


def _call_llm(transcript_text: str) -> str:
    cache_key = hashlib.sha256(
        f"{settings.llm_provider}:{SYSTEM_PROMPT}:{transcript_text}".encode()
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
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": transcript_text}],
        )
        result = "".join(b.text for b in response.content if b.type == "text").strip()

    elif settings.llm_provider == "groq":
        from groq import Groq
        estimated = _estimate_tokens(SYSTEM_PROMPT + transcript_text) + 2000
        _groq_rate_wait(estimated)

        client = Groq(api_key=settings.groq_api_key)
        for attempt in range(3):
            try:
                response = client.chat.completions.create(
                    model=settings.groq_model,
                    max_tokens=2000,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
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

        actual_tokens = getattr(response, "usage", None)
        if actual_tokens:
            _groq_rate_record(actual_tokens.total_tokens)
        else:
            _groq_rate_record(estimated)
        result = response.choices[0].message.content.strip()

    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r}. Use 'anthropic' or 'groq'.")

    cache_set("llm", cache_key, result)
    return result


def _snap_boundaries(
    candidate: ClipCandidate,
    segments: List[Segment],
) -> ClipCandidate:
    """Snap clip start/end to sentence (segment) boundaries so cuts land on
    natural speech pauses instead of mid-word."""
    if not segments:
        return candidate

    # Find the segment whose start is closest to candidate.start
    # Prefer snapping backward so the hook sentence is fully included
    best_start_seg = min(segments, key=lambda s: abs(s.start - candidate.start))
    # Find the segment whose end is closest to candidate.end
    # Prefer snapping forward so the punchline sentence is fully included
    best_end_seg = min(segments, key=lambda s: abs(s.end - candidate.end))

    snapped_start = best_start_seg.start
    snapped_end = best_end_seg.end

    # If snapping pushed start after end, fall back
    if snapped_start >= snapped_end:
        return candidate

    duration = snapped_end - snapped_start

    # If too short after snapping, expand by adding adjacent segments
    if duration < settings.clip_min_seconds:
        seg_starts = [s.start for s in segments]
        seg_ends = [s.end for s in segments]
        start_idx = seg_starts.index(snapped_start) if snapped_start in seg_starts else 0
        end_idx = seg_ends.index(snapped_end) if snapped_end in seg_ends else len(segments) - 1

        while (snapped_end - snapped_start) < settings.clip_min_seconds:
            expanded = False
            # Try extending end first (preserve the punchline/payoff)
            if end_idx + 1 < len(segments):
                end_idx += 1
                snapped_end = segments[end_idx].end
                expanded = True
            # Then try extending start (add more setup)
            if (snapped_end - snapped_start) < settings.clip_min_seconds and start_idx > 0:
                start_idx -= 1
                snapped_start = segments[start_idx].start
                expanded = True
            if not expanded:
                break

    # If too long, trim from the start (keep the ending/punchline)
    if (snapped_end - snapped_start) > settings.clip_max_seconds:
        seg_starts = [s.start for s in segments]
        for s_start in seg_starts:
            if s_start >= snapped_start and (snapped_end - s_start) <= settings.clip_max_seconds:
                snapped_start = s_start
                break

    # Add a small breath before the first word so the clip doesn't start abruptly
    snapped_start = max(0, snapped_start - 0.3)

    candidate.start = snapped_start
    candidate.end = snapped_end
    return candidate


def select_clips(segments: List[Segment], num_clips: int = 5, user_prompt: str = "") -> List[ClipCandidate]:
    all_candidates: List[ClipCandidate] = []

    for chunk in _chunk_segments(segments):
        transcript_text = _segments_to_text(chunk)
        if not transcript_text.strip():
            continue

        if user_prompt:
            transcript_text = (
                f"ADDITIONAL INSTRUCTIONS FROM THE USER:\n{user_prompt}\n\n"
                f"TRANSCRIPT:\n{transcript_text}"
            )

        raw = _call_llm(transcript_text)

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue

        for c in parsed.get("clips", []):
            try:
                candidate = ClipCandidate(**c)
            except TypeError:
                continue

            candidate = _snap_boundaries(candidate, chunk)

            duration = candidate.end - candidate.start
            if duration > settings.clip_max_seconds:
                continue
            if duration < settings.clip_min_seconds:
                continue
            all_candidates.append(candidate)

    all_candidates.sort(key=lambda c: c.score, reverse=True)
    return all_candidates[:num_clips]
