"""Voice shortcuts, mood settings, and silence detection."""
import re

DEFAULT_VOICE = "en-US-ChristopherNeural"

ELEVENLABS_VOICES = {
    "el-thomas":  "GBv7mTt0atIp3Br8iCZE",
    "el-william": "bIHbv24MWmeRgasZH58o",
    "syns":       "NbYHfMmZyvMxflOseaw2",
    "syns-warmer":"KZrGqGwAGzDxoN8xtKVl",
}

POPULAR_VOICES = {
    # Dramatic / Tension
    "dramatic":    "en-US-ChristopherNeural",
    "tension":     "en-US-EricNeural",
    "intense":     "en-US-RogerNeural",
    "dark":        "en-GB-ThomasNeural",
    # Warm / Storytelling
    "storyteller": "en-US-AndrewNeural",
    "warm":        "en-US-BrianNeural",
    "caring":      "en-US-AvaNeural",
    "friendly":    "en-US-JennyNeural",
    "cheerful":    "en-US-EmmaNeural",
    # News / Documentary
    "news":        "en-US-AriaNeural",
    "documentary": "en-US-ChristopherNeural",
    "narrator":    "en-US-GuyNeural",
    # TikTok / Social
    "tiktok":      "en-US-GuyNeural",
    "viral":       "en-US-RogerNeural",
    "cute":        "en-US-AnaNeural",
    # Indonesian
    "male-id":     "id-ID-ArdiNeural",
    "female-id":   "id-ID-GadisNeural",
    "deep-id":     "id-ID-ArdiNeural",
    # British
    "male-uk":     "en-GB-RyanNeural",
    "female-uk":   "en-GB-SoniaNeural",
    # Australian
    "male-au":     "en-AU-WilliamMultilingualNeural",
    "female-au":   "en-AU-NatashaNeural",
    # Legacy
    "male-en":     "en-US-ChristopherNeural",
    "female-en":   "en-US-JennyNeural",
}

MOOD_VOICE_SETTINGS = {
    "dramatic":    {"voice": "en-US-ChristopherNeural", "pitch": "-10Hz", "rate": "-25%"},
    "tension":     {"voice": "en-US-EricNeural",        "pitch": "-5Hz",  "rate": "-20%"},
    "intense":     {"voice": "en-US-RogerNeural",       "pitch": "+5Hz",  "rate": "-5%"},
    "dark":        {"voice": "en-GB-ThomasNeural",      "pitch": "-15Hz", "rate": "-30%"},
    "warm":        {"voice": "en-US-BrianNeural",       "pitch": "+0Hz",  "rate": "-25%"},
    "caring":      {"voice": "en-US-AvaNeural",         "pitch": "+5Hz",  "rate": "-25%"},
    "storyteller": {"voice": "en-US-AndrewNeural",      "pitch": "+0Hz",  "rate": "-20%"},
    "friendly":    {"voice": "en-US-JennyNeural",       "pitch": "+5Hz",  "rate": "-15%"},
    "cheerful":    {"voice": "en-US-EmmaNeural",        "pitch": "+10Hz", "rate": "-10%"},
    "sad":         {"voice": "en-US-AvaNeural",         "pitch": "-10Hz", "rate": "-35%"},
    "calm":        {"voice": "en-US-BrianNeural",       "pitch": "-5Hz",  "rate": "-30%"},
    "excited":     {"voice": "en-US-RogerNeural",       "pitch": "+10Hz", "rate": "+5%"},
    "angry":       {"voice": "en-US-RogerNeural",       "pitch": "+5Hz",  "rate": "+5%"},
    "whisper":     {"voice": "en-US-BrianNeural",       "pitch": "-5Hz",  "rate": "-35%"},
    "slow":        {"voice": "en-US-BrianNeural",       "pitch": "-5Hz",  "rate": "-40%"},
    "fast":        {"voice": "en-US-BrianNeural",       "pitch": "+5Hz",  "rate": "+10%"},
    "tiktok":      {"voice": "en-US-GuyNeural",         "pitch": "+5Hz",  "rate": "-5%"},
    "viral":       {"voice": "en-US-RogerNeural",       "pitch": "+5Hz",  "rate": "-5%"},
    "cute":        {"voice": "en-US-AnaNeural",         "pitch": "+15Hz", "rate": "-10%"},
    "news":        {"voice": "en-US-AriaNeural",        "pitch": "+0Hz",  "rate": "-10%"},
    "documentary": {"voice": "en-US-ChristopherNeural", "pitch": "-5Hz",  "rate": "-15%"},
    "narrator":    {"voice": "en-US-GuyNeural",         "pitch": "-5Hz",  "rate": "-15%"},
    # Indonesian
    "deep-id":     {"voice": "id-ID-ArdiNeural",        "pitch": "-15Hz", "rate": "-25%"},
    "dramatic-id": {"voice": "id-ID-ArdiNeural",        "pitch": "-10Hz", "rate": "-20%"},
    "calm-id":     {"voice": "id-ID-ArdiNeural",        "pitch": "-5Hz",  "rate": "-30%"},
    "news-id":     {"voice": "id-ID-ArdiNeural",        "pitch": "+0Hz",  "rate": "-10%"},
    "warm-id":     {"voice": "id-ID-GadisNeural",       "pitch": "+0Hz",  "rate": "-20%"},
    "syns-warm":   {"voice": "syns",                    "pitch": "+0Hz",  "rate": "-20%"},
}

_SILENCE_PATTERNS = [
    r"^\[.*\]$",
    r"^—\s*silence\s*—$",
    r"^-+\s*silence\s*-+$",
    r"^\[silent\]",
    r"^\[no\s*voice\]",
    r"^\[no\s*narration\]",
    r"^\[music\s*only\]",
    r"^\[sfx\s*only\]",
    r"^\.\.\.$",
]


def is_silent_scene(text: str) -> bool:
    """Return True if this narration line should produce no TTS audio."""
    cleaned = text.strip()
    if not cleaned:
        return True
    for pattern in _SILENCE_PATTERNS:
        if re.match(pattern, cleaned, re.IGNORECASE):
            return True
    bracketed = re.findall(r"\[.*?\]", cleaned)
    remaining = re.sub(r"\[.*?\]", "", cleaned).strip()
    remaining = re.sub(r"[—–\-\s]+", " ", remaining).strip()
    remaining = re.sub(r"\b(silence|silent|fade\s*out|fade\s*in|pause|intro|outro|end)\b", "", remaining, flags=re.IGNORECASE).strip()
    remaining = re.sub(r"[—–\-\s]+", "", remaining)
    return bool(bracketed and not remaining)


def resolve_elevenlabs_voice(voice: str) -> str | None:
    """Return ElevenLabs voice ID if voice is an EL voice, else None."""
    if voice.startswith("el:"):
        return voice[3:]
    return ELEVENLABS_VOICES.get(voice)
