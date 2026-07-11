"""TTS backends: Edge TTS (Microsoft) and ElevenLabs."""
import asyncio
import os
import subprocess

from ..render import FFMPEG
from .cache import SentenceTiming


# ── Edge TTS ──────────────────────────────────────────────────────────────────

async def _edge_tts_stream(text: str, voice: str, rate: str, pitch: str) -> tuple:
    import edge_tts
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    timings, chunks = [], []
    async for event in communicate.stream():
        if event["type"] == "audio":
            chunks.append(event["data"])
        elif event["type"] == "SentenceBoundary":
            timings.append(SentenceTiming(
                text=event["text"],
                start=event["offset"] / 10_000_000,
                duration=event["duration"] / 10_000_000,
            ))
    return chunks, timings


def generate_edge_tts(text: str, output_path: str, voice: str, rate: str, pitch: str) -> list:
    """Generate audio via Edge TTS. Returns list of SentenceTiming."""
    chunks, timings = asyncio.run(_edge_tts_stream(text, voice, rate, pitch))
    with open(output_path, "wb") as f:
        for chunk in chunks:
            f.write(chunk)
    return timings


# ── ElevenLabs ────────────────────────────────────────────────────────────────

def generate_elevenlabs_tts(text: str, output_path: str, voice_id: str) -> list:
    """Generate audio via ElevenLabs API. Returns empty list (no word timings)."""
    import httpx
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise ValueError("ELEVENLABS_API_KEY environment variable not set")

    response = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
        json={
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.6, "similarity_boost": 0.75, "speed": 0.97, "style_aggregation": "25%"},
        },
        timeout=60,
    )
    if response.status_code != 200:
        raise RuntimeError(f"ElevenLabs API error {response.status_code}: {response.text}")
    with open(output_path, "wb") as f:
        f.write(response.content)
    return []


# ── Silence ───────────────────────────────────────────────────────────────────

def generate_silence(output_path: str, duration: float) -> str:
    """Generate a silent MP3 of the given duration."""
    cmd = [
        FFMPEG, "-y",
        "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
        "-t", str(duration),
        "-c:a", "libmp3lame", "-b:a", "32k",
        output_path,
    ]
    subprocess.run(cmd, capture_output=True, text=True)
    return output_path
