"""Core clip selection logic — category detection, boundary snapping, LLM orchestration."""
import json
from typing import List, Optional

from ..config import settings
from ..transcribe import Segment, AudioEnergy, analyze_audio_energy
from .llm import call_llm
from .models import ClipCandidate
from .presets import VIDEO_CATEGORIES, AUTO_DETECT_PROMPT, CATEGORY_PROMPT_TEMPLATE, GENERIC_PROMPT, BASE_RULES
from .transcript import segments_to_text, chunk_segments


def _build_system_prompt(video_category: str) -> str:
    cat = VIDEO_CATEGORIES.get(video_category)
    if cat and cat.get("prompt"):
        body = cat["prompt"].format(base_rules=BASE_RULES)
    else:
        body = GENERIC_PROMPT.format(base_rules=BASE_RULES)
    return CATEGORY_PROMPT_TEMPLATE.format(category_prompt=body)


def _auto_detect_category(segments: List[Segment]) -> str:
    excerpt = segments_to_text(segments[:30])
    categories = [k for k in VIDEO_CATEGORIES if k != "auto"]
    prompt = AUTO_DETECT_PROMPT.format(categories=", ".join(categories), excerpt=excerpt[:2000])
    raw = call_llm(prompt, system_prompt="You classify video content into categories. Return ONLY the category name.")
    detected = raw.strip().lower().replace('"', '').replace("'", "")
    return next((c for c in categories if c in detected), "auto")


def _snap_boundaries(candidate: ClipCandidate, segments: List[Segment]) -> ClipCandidate:
    """Snap clip start/end to segment boundaries so cuts land on natural speech pauses."""
    if not segments:
        return candidate

    best_start = min(segments, key=lambda s: abs(s.start - candidate.start)).start
    best_end = min(segments, key=lambda s: abs(s.end - candidate.end)).end

    if best_start >= best_end:
        return candidate

    seg_starts = [s.start for s in segments]
    seg_ends = [s.end for s in segments]

    # Expand if too short
    if best_end - best_start < settings.clip_min_seconds:
        start_idx = seg_starts.index(best_start) if best_start in seg_starts else 0
        end_idx = seg_ends.index(best_end) if best_end in seg_ends else len(segments) - 1
        while best_end - best_start < settings.clip_min_seconds:
            expanded = False
            if end_idx + 1 < len(segments):
                end_idx += 1
                best_end = segments[end_idx].end
                expanded = True
            if best_end - best_start < settings.clip_min_seconds and start_idx > 0:
                start_idx -= 1
                best_start = segments[start_idx].start
                expanded = True
            if not expanded:
                break

    # Trim if too long
    hard_max = settings.clip_max_seconds + 15
    if best_end - best_start > hard_max:
        for s_start in seg_starts:
            if s_start >= best_start and best_end - s_start <= hard_max:
                best_start = s_start
                break

    candidate.start = max(0, best_start - 0.3)  # small breath before first word
    candidate.end = best_end
    return candidate


def select_clips(
    segments: List[Segment],
    num_clips: int = 5,
    user_prompt: str = "",
    video_category: str = "auto",
    video_path: Optional[str] = None,
) -> List[ClipCandidate]:
    """Analyse transcript and return the top clip candidates ranked by score."""
    if video_category == "auto":
        detected = _auto_detect_category(segments)
        if detected != "auto":
            video_category = detected
            print(f"   Auto-detected video category: {video_category}")
        else:
            print("   Could not detect category, using generic mode")

    energy: Optional[List[AudioEnergy]] = None
    if video_path:
        print("   Analyzing audio energy...")
        energy = analyze_audio_energy(video_path)
        if energy:
            print(f"   Found {sum(1 for e in energy if e.is_spike)} energy spikes, "
                  f"{sum(1 for e in energy if e.energy_level == 'peak')} peak moments")
        else:
            print("   No audio energy data (silent or very short)")

    system_prompt = _build_system_prompt(video_category)
    hard_min = max(15, settings.clip_min_seconds - 15)
    hard_max = settings.clip_max_seconds + 15
    all_candidates: List[ClipCandidate] = []

    for chunk in chunk_segments(segments):
        chunk_energy = None
        if energy and chunk:
            chunk_energy = [e for e in energy if chunk[0].start <= e.time <= chunk[-1].end]

        transcript_text = segments_to_text(chunk, energy=chunk_energy)
        if not transcript_text.strip():
            continue

        if user_prompt:
            transcript_text = f"ADDITIONAL INSTRUCTIONS FROM THE USER:\n{user_prompt}\n\nTRANSCRIPT:\n{transcript_text}"

        raw = call_llm(transcript_text, system_prompt=system_prompt)

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue

        for c in parsed.get("clips", []):
            try:
                candidate = _snap_boundaries(ClipCandidate(**c), chunk)
            except TypeError:
                continue
            duration = candidate.end - candidate.start
            if hard_min <= duration <= hard_max:
                all_candidates.append(candidate)

    all_candidates.sort(key=lambda c: c.score, reverse=True)
    return all_candidates[:num_clips]
