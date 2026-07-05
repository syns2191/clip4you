"""
Text-to-speech narration using Microsoft Edge TTS or ElevenLabs.
Set ELEVENLABS_API_KEY env var and pass voice="el:<voice_id>" to use ElevenLabs.
"""
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional, List

from .render import FFMPEG

TTS_CACHE_DIR = os.path.join("cache", "tts")

DEFAULT_VOICE = "en-US-ChristopherNeural"

# ElevenLabs voice IDs — pass as "el:<voice_id>" or use shortcuts below
ELEVENLABS_VOICES = {
    "el-rachel":    "21m00Tcm4TlvDq8ikWAM",   # warm female
    "el-adam":      "pNInz6obpgDQGcFmaJgB",   # deep male, narration
    "el-clyde":     "2EiwWnXFnvU5JabPnv8n",   # confident male
    "el-domi":      "AZnzlk1XvdvUeBnXmlld",   # strong female
    "el-dave":      "CYw3kZ02Hs0563khs1Fj",   # british male
    "el-fin":       "D38z5RcWu1voky8WS1ja",   # soft male
    "el-bella":     "EXAVITQu4vr4xnSDxMaL",   # soft female
    "el-callum":    "N2lVS1w4EtoT3dr4eOWO",   # male, intense
    "el-charlie":   "IKne3meq5aSn9XLyUdCD",   # casual male, au
    "el-charlotte": "XB0fDUnXU5powFXDhCwa",   # female, seductive
    "el-daniel":    "onwK4e9ZLuTAKqWW03F9",   # british male, authoritative
    "el-ethan":     "g5CIjZEefAph4nQFvHAz",   # soft male
    "el-freya":     "jsCqWAovK2LkecY7zXl4",   # female, american
    "el-gigi":      "jBpfuIE2acCO8z3wKNLl",   # female, childlike
    "el-giovanni":  "zcAOhNBS3c14rBihAFp1",   # male, italian accent
    "el-glinda":    "z9fAnlkpzviPz146aGWa",   # female, theatrical
    "el-grace":     "oWAxZDx7w5VEj9dCyTzz",   # southern female
    "el-harry":     "SOYHLrjzK2X1ezoPC6cr",   # male, anxious
    "el-james":     "ZQe5CZNOzWyzPSCn5a3c",   # british male, calm
    "el-jeremy":    "bVMeCyTHy58xNoL34h3p",   # male, american
    "el-jessie":    "t0jbNlBVZ17f02VDIeMI",   # male, old
    "el-joseph":    "Zlb1dXrM653N07WRdFW3",   # british male
    "el-josh":      "TxGEqnHWrfWFTfGW9XjX",   # deep male
    "el-liam":      "TX3LPaxmHKxFdv7VOQHJ",   # male, neutral
    "el-lily":      "pFZP5JQG7iQjIQuC4Bku",   # british female
    "el-matilda":   "XrExE9yKIg1WjnnlVkGX",   # female, warm
    "el-michael":   "flq6f7yk4E4fJM5XTYuZ",   # old male
    "el-mimi":      "zrHiDhphv9ZnVXBqCLjz",   # female, childlike
    "el-nicole":    "piTKgcLEGmPE4e6mEKli",   # female, whisper
    "el-patrick":   "ODq5zmih8GrVes37Dizd",   # male, shouting
    "el-paul":      "5Q0t7uMcjvnagumLfvZi",   # male, news
    "el-sam":       "yoZ06aMxZJJ28mfd3POQ",   # male, raspy
    "el-sarah":     "EXAVITQu4vr4xnSDxMaL",   # female, soft
    "el-serena":    "pMsXgVXv3BLzUgSXRplE",   # female, pleasant
    "el-thomas":    "GBv7mTt0atIp3Br8iCZE",   # male, calm
    "el-william":   "bIHbv24MWmeRgasZH58o",   # male, old british
    "syns": "NbYHfMmZyvMxflOseaw2",
}

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
    "male-id":      "id-ID-ArdiNeural",
    "female-id":    "id-ID-GadisNeural",
    "deep-id":      "id-ID-ArdiNeural",    # ArdiNeural pitched down — deep/dramatic bahasa

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

    # ── Indonesian moods ──────────────────────────────────────────────────
    "deep-id":    {"voice": "id-ID-ArdiNeural",        "pitch": "-15Hz", "rate": "-25%"},
    "dramatic-id":{"voice": "id-ID-ArdiNeural",        "pitch": "-10Hz", "rate": "-20%"},
    "calm-id":    {"voice": "id-ID-ArdiNeural",        "pitch": "-5Hz",  "rate": "-30%"},
    "news-id":    {"voice": "id-ID-ArdiNeural",        "pitch": "+0Hz",  "rate": "-10%"},
    "warm-id":    {"voice": "id-ID-GadisNeural",       "pitch": "+0Hz",  "rate": "-20%"},
    "syns-warm":    {"voice": "syns",        "pitch": "+0Hz",  "rate": "-20%"},
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


def _generate_elevenlabs_tts(text: str, output_path: str, voice_id: str, stability: float = 0.5, similarity_boost: float = 0.75) -> list:
    """Generate TTS using ElevenLabs API. Returns empty timings list (ElevenLabs doesn't provide word timings)."""
    import httpx

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise ValueError("ELEVENLABS_API_KEY environment variable not set")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity_boost,
        },
    }

    response = httpx.post(url, headers=headers, json=payload, timeout=60)
    if response.status_code != 200:
        raise RuntimeError(f"ElevenLabs API error {response.status_code}: {response.text}")

    with open(output_path, "wb") as f:
        f.write(response.content)

    return []


def _tts_cache_key(text: str, voice: str, rate: str, pitch: str) -> str:
    payload = json.dumps({"text": text, "voice": voice, "rate": rate, "pitch": pitch}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _cache_hit(key: str) -> Optional[str]:
    """Return path to cached audio if it exists, else None."""
    path = os.path.join(TTS_CACHE_DIR, f"{key}.mp3")
    return path if os.path.exists(path) else None


def _cache_store(key: str, audio_path: str) -> None:
    os.makedirs(TTS_CACHE_DIR, exist_ok=True)
    shutil.copy2(audio_path, os.path.join(TTS_CACHE_DIR, f"{key}.mp3"))


def _load_timings_cache(key: str) -> Optional[list]:
    path = os.path.join(TTS_CACHE_DIR, f"{key}.json")
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
        return [SentenceTiming(**d) for d in data]
    return None


def _store_timings_cache(key: str, timings: list) -> None:
    os.makedirs(TTS_CACHE_DIR, exist_ok=True)
    path = os.path.join(TTS_CACHE_DIR, f"{key}.json")
    with open(path, "w") as f:
        json.dump([{"text": t.text, "start": t.start, "duration": t.duration} for t in timings], f)


def _resolve_elevenlabs_voice(voice: str) -> Optional[str]:
    """Return ElevenLabs voice ID if voice is an ElevenLabs voice, else None."""
    if voice.startswith("el:"):
        return voice[3:]
    if voice in ELEVENLABS_VOICES:
        return ELEVENLABS_VOICES[voice]
    return None


def generate_narration(
    text: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    rate: str = "-10%",
    pitch: str = "+0Hz",
    mood: str = "",
    use_cache: bool = False,
) -> tuple:
    """Generate TTS audio from text with voice, rate, and pitch control.
    Returns (output_path, list[SentenceTiming]).
    Use voice="el:<voice_id>" or voice="el-rachel" etc. to use ElevenLabs.
    If mood is set, it overrides rate/pitch with mood-specific settings.
    If use_cache=True, identical (text, voice, rate, pitch) hits are served from cache/tts/."""
    if is_silent_scene(text):
        generate_silence(output_path, 2.0)
        return output_path, []

    if mood and mood in MOOD_VOICE_SETTINGS:
        settings = MOOD_VOICE_SETTINGS[mood]
        rate = settings["rate"]
        pitch = settings["pitch"]

    if use_cache:
        key = _tts_cache_key(text, voice, rate, pitch)
        cached = _cache_hit(key)
        if cached:
            shutil.copy2(cached, output_path)
            timings = _load_timings_cache(key) or []
            return output_path, timings

    el_voice_id = _resolve_elevenlabs_voice(voice)
    if el_voice_id:
        timings = _generate_elevenlabs_tts(text, output_path, el_voice_id)
    else:
        timings = asyncio.run(_generate_tts(text, output_path, voice, rate=rate, pitch=pitch))

    if use_cache:
        _cache_store(key, output_path)
        _store_timings_cache(key, timings)

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
    print("\nEdge TTS voice shortcuts:")
    print("-" * 40)
    for key, voice in POPULAR_VOICES.items():
        print(f"  {key:14s} -> {voice}")
    print("\nOr use any full Edge TTS voice name (e.g. 'en-US-AriaNeural')")
    print("Run 'edge-tts --list-voices' for all available voices.")
    print("\nElevenLabs voice shortcuts (requires ELEVENLABS_API_KEY):")
    print("-" * 40)
    for key, voice_id in ELEVENLABS_VOICES.items():
        print(f"  {key:14s} -> {voice_id}")
    print("\nOr use 'el:<voice_id>' for any ElevenLabs voice ID.")
