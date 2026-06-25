"""
Text-to-speech narration using Microsoft Edge TTS.
Free, high-quality, many voices/languages, no API key needed.
"""
import asyncio
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Optional, List

from .render import FFMPEG

DEFAULT_VOICE = "en-US-ChristopherNeural"

POPULAR_VOICES = {
    # ── Dramatic / Tension ────────────────────────────────────────────────
    "dramatic": "en-US-ChristopherNeural",       # deep, authoritative — thriller/drama
    "tension": "en-US-EricNeural",               # rational, serious — suspense/mystery
    "intense": "en-US-RogerNeural",              # lively, high energy — action/urgent
    "dark": "en-GB-ThomasNeural",                # deep British — horror/dark stories

    # ── Warm / Human / Storytelling ───────────────────────────────────────
    "storyteller": "en-US-AndrewNeural",         # warm, confident — natural storytelling
    "warm": "en-US-BrianNeural",                 # approachable, casual — human/relatable
    "caring": "en-US-AvaNeural",                 # expressive, caring — emotional stories
    "friendly": "en-US-JennyNeural",             # friendly, considerate — everyday content
    "cheerful": "en-US-EmmaNeural",              # cheerful, clear — upbeat/positive

    # ── News / Documentary ────────────────────────────────────────────────
    "news": "en-US-AriaNeural",                  # positive, confident — news/facts
    "documentary": "en-US-ChristopherNeural",    # reliable, authority — documentaries
    "narrator": "en-US-GuyNeural",               # passion — cinematic/epic narration

    # ── TikTok / Social ───────────────────────────────────────────────────
    "tiktok": "en-US-GuyNeural",                 # passion, punchy — short-form viral
    "viral": "en-US-RogerNeural",                # lively — energetic shorts
    "cute": "en-US-AnaNeural",                   # cute cartoon — fun/quirky content

    # ── Indonesian ────────────────────────────────────────────────────────
    "male-id": "id-ID-ArdiNeural",
    "female-id": "id-ID-GadisNeural",

    # ── British ───────────────────────────────────────────────────────────
    "male-uk": "en-GB-RyanNeural",
    "female-uk": "en-GB-SoniaNeural",

    # ── Australian ────────────────────────────────────────────────────────
    "male-au": "en-AU-WilliamMultilingualNeural",
    "female-au": "en-AU-NatashaNeural",

    # ── Legacy shortcuts ──────────────────────────────────────────────────
    "male-en": "en-US-ChristopherNeural",
    "female-en": "en-US-JennyNeural",
}

# Mood → voice + pitch + rate adjustments for real intonation change
# pitch shifts the tone (deeper/higher), rate shifts speed
MOOD_VOICE_SETTINGS = {
    "dramatic":   {"voice": "en-US-ChristopherNeural", "pitch": "-10Hz", "rate": "-25%"},
    "tension":    {"voice": "en-US-EricNeural",        "pitch": "-5Hz",  "rate": "-20%"},
    "intense":    {"voice": "en-US-RogerNeural",       "pitch": "+5Hz",  "rate": "-5%"},
    "dark":       {"voice": "en-GB-ThomasNeural",      "pitch": "-15Hz", "rate": "-30%"},
    "warm":       {"voice": "en-US-BrianNeural",       "pitch": "+0Hz",  "rate": "-25%"},
    "caring":     {"voice": "en-US-AvaNeural",         "pitch": "+5Hz",  "rate": "-25%"},
    "storyteller": {"voice": "en-US-AndrewNeural",     "pitch": "+0Hz",  "rate": "-20%"},
    "friendly":   {"voice": "en-US-JennyNeural",       "pitch": "+5Hz",  "rate": "-15%"},
    "cheerful":   {"voice": "en-US-EmmaNeural",        "pitch": "+10Hz", "rate": "-10%"},
    "sad":        {"voice": "en-US-AvaNeural",         "pitch": "-10Hz", "rate": "-35%"},
    "calm":       {"voice": "en-US-BrianNeural",       "pitch": "-5Hz",  "rate": "-30%"},
    "excited":    {"voice": "en-US-RogerNeural",       "pitch": "+10Hz", "rate": "+5%"},
    "angry":      {"voice": "en-US-RogerNeural",       "pitch": "+5Hz",  "rate": "+5%"},
    "whisper":    {"voice": "en-US-BrianNeural",       "pitch": "-5Hz",  "rate": "-35%"},
    "slow":       {"voice": "en-US-BrianNeural",       "pitch": "-5Hz",  "rate": "-40%"},
    "fast":       {"voice": "en-US-BrianNeural",       "pitch": "+5Hz",  "rate": "+10%"},
    "tiktok":     {"voice": "en-US-GuyNeural",         "pitch": "+5Hz",  "rate": "-5%"},
    "viral":      {"voice": "en-US-RogerNeural",       "pitch": "+5Hz",  "rate": "-5%"},
    "cute":       {"voice": "en-US-AnaNeural",         "pitch": "+15Hz", "rate": "-10%"},
    "news":       {"voice": "en-US-AriaNeural",        "pitch": "+0Hz",  "rate": "-10%"},
    "documentary": {"voice": "en-US-ChristopherNeural","pitch": "-5Hz",  "rate": "-15%"},
    "narrator":   {"voice": "en-US-GuyNeural",         "pitch": "-5Hz",  "rate": "-15%"},
}

# Patterns that indicate a silent/non-spoken scene
SILENCE_PATTERNS = [
    r"^\[.*\]$",                    # [INTRO], [SILENCE], [PAUSE], [END]
    r"^—\s*silence\s*—$",          # — silence —
    r"^-+\s*silence\s*-+$",        # --- silence ---
    r"^\[silent\]",                 # [silent]
    r"^\[no\s*voice\]",            # [no voice]
    r"^\[no\s*narration\]",        # [no narration]
    r"^\[music\s*only\]",          # [music only]
    r"^\[sfx\s*only\]",            # [sfx only]
    r"^\.\.\.$",                    # ...
]


def is_silent_scene(text: str) -> bool:
    """Check if a narration line should be silent (no TTS)."""
    cleaned = text.strip()
    if not cleaned:
        return True
    for pattern in SILENCE_PATTERNS:
        if re.match(pattern, cleaned, re.IGNORECASE):
            return True
    # Check for text that's mostly stage directions: [INTRO] — silence —
    bracketed = re.findall(r"\[.*?\]", cleaned)
    remaining = re.sub(r"\[.*?\]", "", cleaned).strip()
    # Remove dashes, em-dashes, "silence", and whitespace
    remaining = re.sub(r"[—–\-\s]+", " ", remaining).strip()
    remaining = re.sub(r"\b(silence|silent|fade\s*out|fade\s*in|pause|intro|outro|end)\b", "", remaining, flags=re.IGNORECASE).strip()
    remaining = re.sub(r"[—–\-\s]+", "", remaining)
    if bracketed and not remaining:
        return True
    return False


def generate_silence(output_path: str, duration: float) -> str:
    """Generate a silent audio file of given duration."""
    cmd = [
        FFMPEG, "-y",
        "-f", "lavfi", "-i", f"anullsrc=r=24000:cl=mono",
        "-t", str(duration),
        "-c:a", "libmp3lame", "-b:a", "32k",
        output_path,
    ]
    subprocess.run(cmd, capture_output=True, text=True)
    return output_path


@dataclass
class SentenceTiming:
    text: str
    start: float
    duration: float


async def _generate_tts(text: str, output_path: str, voice: str, rate: str = "-10%", pitch: str = "+0Hz") -> list:
    import edge_tts
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    timings = []
    audio_chunks = []

    async for event in communicate.stream():
        if event["type"] == "audio":
            audio_chunks.append(event["data"])
        elif event["type"] == "SentenceBoundary":
            timings.append(SentenceTiming(
                text=event["text"],
                start=event["offset"] / 10_000_000,
                duration=event["duration"] / 10_000_000,
            ))

    with open(output_path, "wb") as f:
        for chunk in audio_chunks:
            f.write(chunk)

    return timings


def generate_narration(
    text: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    rate: str = "-10%",
    pitch: str = "+0Hz",
    mood: str = "",
) -> tuple:
    """Generate TTS audio from text with voice, rate, and pitch control.
    Returns (output_path, list[SentenceTiming]).
    If mood is set, it overrides voice/rate/pitch with mood-specific settings."""
    if is_silent_scene(text):
        generate_silence(output_path, 2.0)
        return output_path, []

    if mood and mood in MOOD_VOICE_SETTINGS:
        settings = MOOD_VOICE_SETTINGS[mood]
        voice = settings["voice"]
        rate = settings["rate"]
        pitch = settings["pitch"]

    timings = asyncio.run(_generate_tts(text, output_path, voice, rate=rate, pitch=pitch))
    return output_path, timings


def mix_narration(
    input_path: str,
    narration_path: str,
    output_path: str,
    original_volume: float = 0.3,
    narration_volume: float = 1.0,
    delay: float = 0.5,
) -> None:
    """Mix narration audio into video, lowering original audio."""
    filter_complex = (
        f"[0:a]volume={original_volume}[orig];"
        f"[1:a]volume={narration_volume},adelay={int(delay * 1000)}|{int(delay * 1000)}[narr];"
        f"[orig][narr]amix=inputs=2:duration=first:normalize=0"
    )
    cmd = [
        FFMPEG, "-y",
        "-i", input_path,
        "-i", narration_path,
        "-filter_complex", filter_complex,
        "-c:v", "copy",
        "-shortest",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg narration mix failed:\n{result.stderr[-2000:]}")


def list_voices() -> None:
    """Print available voice shortcuts."""
    print("\nAvailable voice shortcuts:")
    print("-" * 40)
    for key, voice in POPULAR_VOICES.items():
        print(f"  {key:12s} -> {voice}")
    print("\nOr use any full voice name (e.g. 'en-US-AriaNeural')")
    print("Run 'edge-tts --list-voices' for all available voices.")
