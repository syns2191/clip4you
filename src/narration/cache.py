"""TTS audio and timing cache backed by the local filesystem."""
import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from typing import Optional

TTS_CACHE_DIR = os.path.join("cache", "tts")


@dataclass
class SentenceTiming:
    text: str
    start: float
    duration: float


def _cache_key(text: str, voice: str, rate: str, pitch: str) -> str:
    payload = json.dumps({"text": text, "voice": voice, "rate": rate, "pitch": pitch}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def cache_hit(key: str) -> Optional[str]:
    path = os.path.join(TTS_CACHE_DIR, f"{key}.mp3")
    return path if os.path.exists(path) else None


def cache_store(key: str, audio_path: str) -> None:
    os.makedirs(TTS_CACHE_DIR, exist_ok=True)
    shutil.copy2(audio_path, os.path.join(TTS_CACHE_DIR, f"{key}.mp3"))


def load_timings(key: str) -> Optional[list]:
    path = os.path.join(TTS_CACHE_DIR, f"{key}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return [SentenceTiming(**d) for d in json.load(f)]


def store_timings(key: str, timings: list) -> None:
    os.makedirs(TTS_CACHE_DIR, exist_ok=True)
    with open(os.path.join(TTS_CACHE_DIR, f"{key}.json"), "w") as f:
        json.dump([{"text": t.text, "start": t.start, "duration": t.duration} for t in timings], f)
