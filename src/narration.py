"""
Text-to-speech narration using Microsoft Edge TTS.
Free, high-quality, many voices/languages, no API key needed.
"""
import asyncio
import os
import subprocess
from typing import Optional

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


async def _generate_tts(text: str, output_path: str, voice: str, rate: str = "-10%") -> None:
    import edge_tts
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(output_path)


def generate_narration(text: str, output_path: str, voice: str = DEFAULT_VOICE, rate: str = "-10%") -> str:
    """Generate TTS audio from text. Rate controls speed: '-20%' = slower, '+0%' = normal."""
    asyncio.run(_generate_tts(text, output_path, voice, rate=rate))
    return output_path


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
