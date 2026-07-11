"""TTS narration module — Edge TTS, ElevenLabs, caching, and audio mixing."""
from .voices import (
    DEFAULT_VOICE,
    ELEVENLABS_VOICES,
    POPULAR_VOICES,
    MOOD_VOICE_SETTINGS,
    is_silent_scene,
    resolve_elevenlabs_voice,
)
from .cache import (
    SentenceTiming,
    TTS_CACHE_DIR,
    _cache_key,
    cache_hit,
    cache_store,
    load_timings,
    store_timings,
)
from .tts import (
    generate_edge_tts,
    generate_elevenlabs_tts,
    generate_silence,
)
from .api import (
    generate_narration,
    mix_narration,
    list_voices,
)

__all__ = [
    "DEFAULT_VOICE",
    "ELEVENLABS_VOICES",
    "POPULAR_VOICES",
    "MOOD_VOICE_SETTINGS",
    "is_silent_scene",
    "resolve_elevenlabs_voice",
    "SentenceTiming",
    "TTS_CACHE_DIR",
    "_cache_key",
    "cache_hit",
    "cache_store",
    "load_timings",
    "store_timings",
    "generate_edge_tts",
    "generate_elevenlabs_tts",
    "generate_silence",
    "generate_narration",
    "mix_narration",
    "list_voices",
]
