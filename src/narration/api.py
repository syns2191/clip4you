"""High-level narration API: generate, mix, and list voices."""
import shutil
import subprocess

from ..render import FFMPEG
from .voices import DEFAULT_VOICE, POPULAR_VOICES, ELEVENLABS_VOICES, MOOD_VOICE_SETTINGS, is_silent_scene, resolve_elevenlabs_voice
from .cache import _cache_key, cache_hit, cache_store, load_timings, store_timings
from .tts import generate_edge_tts, generate_elevenlabs_tts, generate_silence


def generate_narration(
    text: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    rate: str = "-10%",
    pitch: str = "+0Hz",
    mood: str = "",
    use_cache: bool = False,
) -> tuple:
    """Generate TTS audio from text. Returns (output_path, list[SentenceTiming]).

    Use voice="el:<voice_id>" or a shortcut like "el-thomas" for ElevenLabs.
    mood overrides rate/pitch with preset settings when set.
    use_cache=True serves identical requests from cache/tts/.
    """
    if is_silent_scene(text):
        generate_silence(output_path, 2.0)
        return output_path, []

    if mood and mood in MOOD_VOICE_SETTINGS:
        settings = MOOD_VOICE_SETTINGS[mood]
        rate = settings["rate"]
        pitch = settings["pitch"]

    if use_cache:
        key = _cache_key(text, voice, rate, pitch)
        cached = cache_hit(key)
        if cached:
            shutil.copy2(cached, output_path)
            timings = load_timings(key) or []
            return output_path, timings

    el_voice_id = resolve_elevenlabs_voice(voice)
    if el_voice_id:
        timings = generate_elevenlabs_tts(text, output_path, el_voice_id)
    else:
        timings = generate_edge_tts(text, output_path, voice, rate=rate, pitch=pitch)

    if use_cache:
        cache_store(key, output_path)
        store_timings(key, timings)

    return output_path, timings


def mix_narration(
    input_path: str,
    narration_path: str,
    output_path: str,
    original_volume: float = 0.3,
    narration_volume: float = 1.0,
    delay: float = 0.5,
) -> None:
    """Mix narration audio into video, ducking the original audio."""
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
    """Print available Edge TTS and ElevenLabs voice shortcuts."""
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
