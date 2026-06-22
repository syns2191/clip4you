"""
Create a short video from a narration script.
AI splits the script into scenes, finds matching visuals (YouTube clips + Pexels images),
generates TTS voiceover, and stitches everything into one video.
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional

from .config import settings
from .render import FFMPEG, reframe_vertical
from .narration import generate_narration, POPULAR_VOICES
from .imagegen import generate_scene_image

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")

# Resolve yt-dlp path (may be in venv)
YT_DLP = shutil.which("yt-dlp") or os.path.join(os.path.dirname(sys.executable), "yt-dlp")


MOOD_PRESETS = {
    "dramatic":   {"voice": "dramatic",    "rate": "-25%"},
    "tension":    {"voice": "tension",     "rate": "-20%"},
    "intense":    {"voice": "intense",     "rate": "-10%"},
    "dark":       {"voice": "dark",        "rate": "-30%"},
    "warm":       {"voice": "warm",        "rate": "-25%"},
    "caring":     {"voice": "caring",      "rate": "-25%"},
    "storyteller": {"voice": "storyteller", "rate": "-20%"},
    "friendly":   {"voice": "friendly",    "rate": "-15%"},
    "cheerful":   {"voice": "cheerful",    "rate": "-10%"},
    "news":       {"voice": "news",        "rate": "-10%"},
    "documentary": {"voice": "documentary", "rate": "-15%"},
    "narrator":   {"voice": "narrator",    "rate": "-15%"},
    "tiktok":     {"voice": "tiktok",      "rate": "-5%"},
    "viral":      {"voice": "viral",       "rate": "-5%"},
    "cute":       {"voice": "cute",        "rate": "-10%"},
    "whisper":    {"voice": "warm",        "rate": "-35%"},
    "slow":       {"voice": "warm",        "rate": "-40%"},
    "fast":       {"voice": "warm",        "rate": "+10%"},
    "angry":      {"voice": "intense",     "rate": "+5%"},
    "sad":        {"voice": "caring",      "rate": "-30%"},
    "calm":       {"voice": "warm",        "rate": "-30%"},
    "excited":    {"voice": "viral",       "rate": "+5%"},
}


@dataclass
class Scene:
    text: str
    search_query: str
    visual_type: str = "video"  # "video" or "image"
    duration: float = 0.0
    start_time: float = 0.0
    visual_path: Optional[str] = None
    audio_path: Optional[str] = None
    voice: Optional[str] = None
    rate: Optional[str] = None
    mood: Optional[str] = None


def _parse_timestamp(ts: str) -> float:
    """Parse timestamp like '0:00', '1:30', '0:05', or raw seconds '5'."""
    ts = ts.strip()
    if ":" in ts:
        parts = ts.split(":")
        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    return float(ts)


def _is_timeline_script(script: str) -> bool:
    """Check if the script uses timeline format (lines with | separator)."""
    lines = [l.strip() for l in script.strip().split("\n") if l.strip()]
    if len(lines) < 2:
        return False
    return all("|" in line for line in lines)


def _parse_timeline_script(script: str) -> List[Scene]:
    """Parse a timeline-formatted script.

    Format:
        0:00 | Narration text | search keyword
        0:05 | Narration text | search keyword | image
        0:12 | Narration text | search keyword | video | dramatic
        0:18 | Narration text | search keyword | image | tension | -30%

    Fields (pipe-separated):
        1. Timestamp (required)
        2. Narration text (required)
        3. Search keyword (optional)
        4. Visual type: "image" or "video" (optional, default: image)
        5. Mood/voice: mood preset name OR voice shortcut (optional)
        6. Rate: speech speed like "-30%", "+10%" (optional)
    """
    lines = [l.strip() for l in script.strip().split("\n") if l.strip()]
    scenes = []

    for line in lines:
        if line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            continue
        timestamp = _parse_timestamp(parts[0])
        text = parts[1]
        search_query = parts[2] if len(parts) >= 3 else ""
        visual_type = "image"
        scene_mood = None
        scene_voice = None
        scene_rate = None

        for part in parts[3:]:
            val = part.strip().lower()
            if val in ("video", "image"):
                visual_type = val
            elif val in MOOD_PRESETS:
                scene_mood = val
            elif val in POPULAR_VOICES:
                scene_voice = val
            elif "%" in val:
                scene_rate = val

        scenes.append(Scene(
            text=text,
            search_query=search_query,
            start_time=timestamp,
            visual_type=visual_type,
            mood=scene_mood,
            voice=scene_voice,
            rate=scene_rate,
        ))

    # Calculate durations from timestamps
    for i in range(len(scenes) - 1):
        scenes[i].duration = scenes[i + 1].start_time - scenes[i].start_time
    # Last scene: use same duration as previous, or 10s default
    if scenes and scenes[-1].duration <= 0:
        if len(scenes) >= 2:
            scenes[-1].duration = scenes[-2].duration
        else:
            scenes[-1].duration = 10.0

    return scenes


def _split_into_scenes(script: str) -> List[Scene]:
    """Split script into scenes — either parse timeline or use LLM."""

    # If script uses timeline format, parse directly
    if _is_timeline_script(script):
        scenes = _parse_timeline_script(script)
        # Generate search queries for scenes that don't have one
        scenes_needing_query = [s for s in scenes if not s.search_query]
        if scenes_needing_query:
            _generate_search_queries(scenes_needing_query)
        return scenes

    # Otherwise, use LLM to split
    prompt = (
        f"Split this narration script into scenes for a short video. "
        f"Each scene is 1-2 sentences that will be spoken as voiceover.\n\n"
        f"For each scene, provide a search query to find matching visuals "
        f"(stock footage or images).\n\n"
        f"Return ONLY valid JSON, no markdown:\n"
        f'{{"scenes": [\n'
        f'  {{"text": "<narration text>", "search_query": "<2-4 word visual search>", '
        f'"visual_type": "<video or image>"}}\n'
        f"]}}\n\n"
        f"Script:\n{script}"
    )

    if settings.llm_provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(b.text for b in response.content if b.type == "text").strip()

    elif settings.llm_provider == "groq":
        from groq import Groq
        client = Groq(api_key=settings.groq_api_key)
        response = client.chat.completions.create(
            model=settings.groq_model,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content.strip()
    else:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")

    try:
        data = json.loads(raw)
        scenes = []
        for s in data.get("scenes", []):
            scenes.append(Scene(
                text=s["text"],
                search_query=s.get("search_query", ""),
                visual_type=s.get("visual_type", "video"),
            ))
        return scenes
    except (json.JSONDecodeError, KeyError):
        return [Scene(text=script, search_query="cinematic background", visual_type="video")]


def _generate_search_queries(scenes: List[Scene]) -> None:
    """Use LLM to generate search queries for scenes that don't have one."""
    texts = "\n".join(f"{i+1}. {s.text}" for i, s in enumerate(scenes))
    prompt = (
        f"For each narration line below, suggest a 2-4 word image search query "
        f"to find a beautiful, relevant photo or artwork.\n\n"
        f"The images will be used as background visuals for a narrated video. "
        f"Suggest searches that would find: nature landscapes, moody photography, "
        f"artistic portraits, silhouettes, or atmospheric scenes that match the MOOD "
        f"of each line. Avoid abstract/generic terms.\n\n"
        f"{texts}\n\n"
        f"Return ONLY valid JSON: {{\"queries\": [\"query1\", \"query2\", ...]}}"
    )

    if settings.llm_provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(b.text for b in response.content if b.type == "text").strip()
    elif settings.llm_provider == "groq":
        from groq import Groq
        client = Groq(api_key=settings.groq_api_key)
        response = client.chat.completions.create(
            model=settings.groq_model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content.strip()
    else:
        return

    try:
        data = json.loads(raw)
        queries = data.get("queries", [])
        for i, scene in enumerate(scenes):
            if i < len(queries):
                scene.search_query = queries[i]
    except (json.JSONDecodeError, KeyError):
        for scene in scenes:
            if not scene.search_query:
                scene.search_query = "cinematic background"


def _download_youtube_clip(query: str, output_path: str, max_duration: int = 30) -> bool:
    """Search and download a short clip from YouTube."""
    search_cmd = [
        YT_DLP,
        f"ytsearch3:{query} stock footage",
        "--dump-json",
        "--flat-playlist",
        "--no-download",
    ]
    result = subprocess.run(search_cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        return False

    video_url = None
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        try:
            data = json.loads(line)
            duration = data.get("duration") or 0
            if 5 <= duration <= 120:
                video_url = data.get("url") or data.get("webpage_url") or f"https://youtube.com/watch?v={data.get('id', '')}"
                break
        except json.JSONDecodeError:
            continue

    if not video_url:
        return False

    download_cmd = [
        YT_DLP,
        "-o", output_path,
        "--format", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--no-playlist",
        video_url,
    ]
    result = subprocess.run(download_cmd, capture_output=True, text=True, timeout=120)
    return os.path.exists(output_path)


def _download_pexels_image(query: str, output_path: str) -> bool:
    """Download a stock image from Pexels API. Tries progressively simpler queries."""
    if not PEXELS_API_KEY:
        return False

    queries_to_try = [query]
    words = query.split()
    if len(words) > 3:
        queries_to_try.append(" ".join(words[:3]))
    if len(words) > 2:
        queries_to_try.append(" ".join(words[:2]))

    for q in queries_to_try:
        url = f"https://api.pexels.com/v1/search?query={urllib.request.quote(q)}&per_page=3&orientation=portrait"
        req = urllib.request.Request(url, headers={"Authorization": PEXELS_API_KEY})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            photos = data.get("photos", [])
            if photos:
                img_url = photos[0]["src"]["large2x"]
                urllib.request.urlretrieve(img_url, output_path)
                return True
        except Exception:
            continue
    return False


def _download_image_from_youtube(query: str, output_path: str) -> bool:
    """Download a high-quality thumbnail from YouTube as a still image."""
    cmd = [
        YT_DLP,
        f"ytsearch8:{query}",
        "--dump-json",
        "--flat-playlist",
        "--no-download",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        return False

    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        try:
            data = json.loads(line)
            thumbnails = data.get("thumbnails", [])
            if thumbnails:
                # Pick the largest thumbnail (prefer maxresdefault)
                best = max(thumbnails, key=lambda t: t.get("height", 0) * t.get("width", 0))
                thumb_url = best.get("url", "")
                if thumb_url:
                    urllib.request.urlretrieve(thumb_url, output_path)
                    if os.path.exists(output_path) and os.path.getsize(output_path) > 5000:
                        return True
        except (json.JSONDecodeError, Exception):
            continue
    return False


def _download_scene_image(query: str, output_path: str) -> bool:
    """Download an image for a scene. Tries multiple sources with better search terms."""
    # Try Pexels first (if API key available)
    if _download_pexels_image(query, output_path):
        return True

    # Build better search terms for YouTube thumbnails
    # These terms help find artistic/aesthetic images, not random video thumbnails
    search_queries = [
        f"{query} wallpaper 4k",
        f"{query} aesthetic photography",
        f"{query} art illustration",
        f"{query} cinematic shot",
    ]
    words = query.split()
    if len(words) > 3:
        search_queries.append(" ".join(words[:3]) + " wallpaper")

    for sq in search_queries:
        if _download_image_from_youtube(sq, output_path):
            return True

    return False


def _download_pexels_video(query: str, output_path: str) -> bool:
    """Download a stock video from Pexels API."""
    if not PEXELS_API_KEY:
        return False

    url = f"https://api.pexels.com/videos/search?query={urllib.request.quote(query)}&per_page=1&orientation=portrait"
    req = urllib.request.Request(url, headers={"Authorization": PEXELS_API_KEY})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        videos = data.get("videos", [])
        if not videos:
            return False
        # Get the HD video file
        video_files = videos[0].get("video_files", [])
        best = None
        for vf in video_files:
            if vf.get("quality") == "hd" or vf.get("height", 0) >= 720:
                best = vf
                break
        if not best and video_files:
            best = video_files[0]
        if not best:
            return False
        urllib.request.urlretrieve(best["link"], output_path)
        return True
    except Exception:
        return False


def _image_to_video(image_path: str, duration: float, output_path: str) -> None:
    """Convert a static image to a 9:16 video without stretching.
    Uses blurred background fill + centered image with slow Ken Burns zoom."""
    # Strategy: place image centered on a 1080x1920 canvas with blurred version as background
    # Then apply slow zoom for visual interest
    frames = int(duration * 25)
    vf = (
        # Create blurred background from the image, scaled to fill 1080x1920
        f"split[bg][fg];"
        f"[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920,boxblur=25:5[blurred];"
        # Scale foreground to fit within 1080x1920 without stretching
        f"[fg]scale=1080:1920:force_original_aspect_ratio=decrease[scaled];"
        # Overlay centered
        f"[blurred][scaled]overlay=(W-w)/2:(H-h)/2[composed];"
        # Slow zoom for visual interest
        f"[composed]zoompan=z='min(zoom+0.0008,1.15)':d={frames}:s=1080x1920:fps=25,"
        f"format=yuv420p"
    )
    cmd = [
        FFMPEG, "-y",
        "-loop", "1",
        "-i", image_path,
        "-filter_complex", vf,
        "-t", str(duration),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Fallback: simple scale without stretch (black bars)
        vf_simple = (
            f"scale=1080:1920:force_original_aspect_ratio=decrease,"
            f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
            f"format=yuv420p"
        )
        cmd2 = [
            FFMPEG, "-y",
            "-loop", "1",
            "-i", image_path,
            "-vf", vf_simple,
            "-t", str(duration),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            output_path,
        ]
        result2 = subprocess.run(cmd2, capture_output=True, text=True)
        if result2.returncode != 0:
            raise RuntimeError(f"Image to video failed:\n{result2.stderr[-1000:]}")


def _trim_video_to_duration(input_path: str, duration: float, output_path: str) -> None:
    """Trim a video to exact duration."""
    cmd = [
        FFMPEG, "-y",
        "-i", input_path,
        "-t", str(duration),
        "-c:v", "libx264", "-c:a", "aac",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Trim failed:\n{result.stderr[-1000:]}")


def _get_audio_duration(path: str) -> float:
    """Get audio file duration."""
    ffprobe = os.path.join(os.path.dirname(FFMPEG), "ffprobe")
    cmd = [
        ffprobe, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 5.0


def _concat_scenes(scene_videos: List[str], output_path: str) -> None:
    """Concatenate scene videos into one (no transitions)."""
    if len(scene_videos) == 1:
        import shutil
        shutil.copy2(scene_videos[0], output_path)
        return

    list_file = output_path + ".txt"
    with open(list_file, "w") as f:
        for path in scene_videos:
            f.write(f"file '{os.path.abspath(path)}'\n")
    cmd = [
        FFMPEG, "-y", "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-an",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    os.unlink(list_file)
    if result.returncode != 0:
        raise RuntimeError(f"Concat failed:\n{result.stderr[-1000:]}")


def _concat_with_transitions(scene_videos: List[str], output_path: str, fade_duration: float = 0.8) -> None:
    """Concatenate scene videos with crossfade transitions between each scene."""
    if len(scene_videos) == 1:
        import shutil
        shutil.copy2(scene_videos[0], output_path)
        return

    if len(scene_videos) == 2:
        dur = _get_audio_duration(scene_videos[0])
        offset = max(0, dur - fade_duration)
        cmd = [
            FFMPEG, "-y",
            "-i", scene_videos[0], "-i", scene_videos[1],
            "-filter_complex",
            f"[0:v][1:v]xfade=transition=fade:duration={fade_duration}:offset={offset}[v]",
            "-map", "[v]", "-an",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            _concat_scenes(scene_videos, output_path)
        return

    # For 3+ scenes: chain xfade filters
    inputs = []
    for path in scene_videos:
        inputs += ["-i", path]

    durations = [_get_audio_duration(p) for p in scene_videos]

    # Build xfade chain
    n = len(scene_videos)
    filter_parts = []
    offset = durations[0] - fade_duration

    # First xfade
    filter_parts.append(
        f"[0:v][1:v]xfade=transition=fade:duration={fade_duration}:offset={offset:.3f}[v1]"
    )

    for i in range(2, n):
        prev = f"[v{i-1}]"
        # Cumulative offset: previous accumulated duration + current scene - fade overlap
        offset += durations[i-1] - fade_duration
        out = f"[v{i}]" if i < n - 1 else "[v]"
        filter_parts.append(
            f"{prev}[{i}:v]xfade=transition=fade:duration={fade_duration}:offset={offset:.3f}{out}"
        )

    filter_complex = ";".join(filter_parts)
    cmd = [FFMPEG, "-y"] + inputs + [
        "-filter_complex", filter_complex,
        "-map", "[v]", "-an",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Fallback to simple concat if xfade fails
        print("   Transitions failed, using simple concat...")
        _concat_scenes(scene_videos, output_path)


def _merge_audio_video(video_path: str, audio_path: str, output_path: str) -> None:
    """Merge final narration audio with the visual track. Video duration wins."""
    cmd = [
        FFMPEG, "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-map", "0:v:0", "-map", "1:a:0",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Merge failed:\n{result.stderr[-1000:]}")


def _pad_audio_to_duration(input_path: str, target_duration: float, output_path: str) -> None:
    """Pad an audio file with silence to reach target duration."""
    current_duration = _get_audio_duration(input_path)
    if current_duration >= target_duration:
        # Just trim to target
        cmd = [
            FFMPEG, "-y", "-i", input_path,
            "-t", str(target_duration),
            "-c:a", "libmp3lame",
            output_path,
        ]
    else:
        # Add silence padding after the speech
        pad_duration = target_duration - current_duration
        filter_complex = (
            f"[0:a]apad=pad_dur={pad_duration:.3f}[padded];"
            f"[padded]atrim=0:{target_duration:.3f}"
        )
        cmd = [
            FFMPEG, "-y", "-i", input_path,
            "-af", f"apad=pad_dur={pad_duration:.3f},atrim=0:{target_duration:.3f}",
            "-c:a", "libmp3lame",
            output_path,
        ]
    subprocess.run(cmd, capture_output=True, text=True)


def _concat_audios(audio_paths: List[str], output_path: str) -> None:
    """Concatenate multiple audio files into one."""
    list_file = output_path + ".txt"
    with open(list_file, "w") as f:
        for path in audio_paths:
            f.write(f"file '{os.path.abspath(path)}'\n")
    cmd = [
        FFMPEG, "-y", "-f", "concat", "-safe", "0",
        "-i", list_file, "-c:a", "libmp3lame", output_path,
    ]
    subprocess.run(cmd, capture_output=True, text=True)
    os.unlink(list_file)


VOICE_MUSIC_MAP = {
    "dramatic": "dark cinematic dramatic",
    "tension": "suspenseful dark ambient",
    "intense": "intense action epic",
    "dark": "dark horror ambient",
    "storyteller": "inspiring storytelling background",
    "warm": "warm acoustic gentle",
    "caring": "emotional piano soft",
    "friendly": "happy upbeat background",
    "cheerful": "cheerful positive pop",
    "news": "news corporate background",
    "documentary": "cinematic documentary epic",
    "narrator": "epic cinematic orchestral",
    "tiktok": "trending tiktok beat",
    "viral": "energetic viral beat",
    "cute": "cute playful fun",
    "male-id": "Indonesian gamelan ambient",
    "female-id": "Indonesian ambient soft",
}


def create_story(
    script: str,
    output_dir: str,
    voice: str = "warm",
    voice_rate: Optional[str] = None,
    music_path: Optional[str] = None,
    music_volume: float = 0.3,
    auto_music: bool = True,
    visuals: str = "download",
) -> str:
    """Create a short narrated video from a script.

    Returns the path to the final output video.
    """
    os.makedirs(output_dir, exist_ok=True)

    print("-> Splitting script into scenes...")
    scenes = _split_into_scenes(script)
    has_timeline = any(s.duration > 0 for s in scenes)
    print(f"   {len(scenes)} scenes identified" + (" (with timeline)" if has_timeline else ""))

    # Generate TTS per scene
    print("-> Generating narration audio...")
    voice_name = POPULAR_VOICES.get(voice, voice)
    # Use slower rate for calm/warm voices, or user override
    if voice_rate:
        tts_rate = voice_rate
    elif voice in ("warm", "caring", "storyteller", "dark", "tension"):
        tts_rate = "-25%"
    else:
        tts_rate = "-15%"
    print(f"   Voice: {voice_name} | Rate: {tts_rate}")

    scene_audios = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, scene in enumerate(scenes):
            audio_path = os.path.join(tmp, f"scene_{i:02d}.mp3")

            s_voice = voice_name
            s_rate = tts_rate
            if scene.mood and scene.mood in MOOD_PRESETS:
                preset = MOOD_PRESETS[scene.mood]
                s_voice = POPULAR_VOICES.get(preset["voice"], preset["voice"])
                s_rate = preset["rate"]
            if scene.voice:
                s_voice = POPULAR_VOICES.get(scene.voice, scene.voice)
            if scene.rate:
                s_rate = scene.rate

            mood_label = f" [{scene.mood}]" if scene.mood else ""
            generate_narration(scene.text, audio_path, voice=s_voice, rate=s_rate)
            tts_duration = _get_audio_duration(audio_path)
            if scene.duration <= 0:
                scene.duration = tts_duration + 2.5
            elif scene.duration < tts_duration + 1.5:
                scene.duration = tts_duration + 1.5
            scene.audio_path = audio_path
            scene_audios.append(audio_path)
            print(f"   Scene {i+1}: {scene.duration:.1f}s (tts: {tts_duration:.1f}s){mood_label} - \"{scene.text[:50]}\"")

        total_duration = sum(s.duration for s in scenes)
        print(f"   Total duration: {total_duration:.1f}s")

        # Build full narration audio: each scene's TTS padded with silence to match timeline
        print("-> Building timed narration track...")
        padded_audios = []
        for i, scene in enumerate(scenes):
            padded_path = os.path.join(tmp, f"padded_{i:02d}.mp3")
            _pad_audio_to_duration(scene.audio_path, scene.duration, padded_path)
            padded_audios.append(padded_path)

        full_narration_path = os.path.join(output_dir, "narration_full.mp3")
        _concat_audios(padded_audios, full_narration_path)

        # Generate/download visuals for each scene
        use_ai_visuals = visuals in ("openai", "sd")
        if use_ai_visuals:
            print(f"\n-> Generating AI illustrations ({visuals}) for each scene...")
        else:
            print("\n-> Downloading visuals for each scene...")
        scene_videos = []

        for i, scene in enumerate(scenes):
            print(f"   Scene {i+1}/{len(scenes)}: \"{scene.search_query}\" ({scene.duration:.1f}s)")
            visual_path = os.path.join(tmp, f"visual_{i:02d}")
            video_path = os.path.join(tmp, f"scene_video_{i:02d}.mp4")
            subtitled_path = os.path.join(tmp, f"scene_sub_{i:02d}.mp4")
            got_visual = False

            # AI-generated illustrations
            if use_ai_visuals:
                ai_img_path = visual_path + "_ai.png"
                if generate_scene_image(scene.text, scene.search_query, ai_img_path, provider=visuals):
                    _image_to_video(ai_img_path, scene.duration, video_path)
                    got_visual = True
                    print(f"      [AI illustration generated]")

            # Download mode or AI fallback
            if not got_visual and scene.visual_type == "video":
                pexels_path = visual_path + "_pexels.mp4"
                if _download_pexels_video(scene.search_query, pexels_path):
                    reframed = visual_path + "_reframed.mp4"
                    reframe_vertical(pexels_path, reframed, mode="crop")
                    _trim_video_to_duration(reframed, scene.duration, video_path)
                    got_visual = True
                    print(f"      [Pexels video]")

                if not got_visual:
                    yt_path = visual_path + "_yt.mp4"
                    if _download_youtube_clip(scene.search_query + " stock footage", yt_path):
                        reframed = visual_path + "_reframed.mp4"
                        reframe_vertical(yt_path, reframed, mode="crop")
                        _trim_video_to_duration(reframed, scene.duration, video_path)
                        got_visual = True
                        print(f"      [YouTube video]")

            if not got_visual:
                img_path = visual_path + ".jpg"
                if _download_scene_image(scene.search_query, img_path):
                    _image_to_video(img_path, scene.duration, video_path)
                    got_visual = True
                    print(f"      [Image found]")

            if not got_visual:
                fallback_img = visual_path + "_fb.jpg"
                words = scene.search_query.split()
                fallback_queries = []
                if len(words) > 2:
                    fallback_queries.append(" ".join(words[:2]))
                fallback_queries.extend(["dark cinematic landscape", "nature moody", "silhouette dramatic"])
                for fq in fallback_queries:
                    if _download_scene_image(fq, fallback_img):
                        _image_to_video(fallback_img, scene.duration, video_path)
                        got_visual = True
                        print(f"      [Fallback image: {fq}]")
                        break

            if not got_visual:
                print(f"      [Text card - no visual found]")
                _make_text_card(scene.text[:80], scene.duration, video_path)

            # Burn subtitle onto the scene video
            _burn_subtitle(video_path, scene.text, scene.duration, subtitled_path)
            scene_videos.append(subtitled_path)

        # Concatenate all scene videos with crossfade transitions
        print("\n-> Stitching scenes with transitions...")
        visual_concat = os.path.join(tmp, "visual_concat.mp4")
        _concat_with_transitions(scene_videos, visual_concat)

        # Merge with full narration audio
        print("-> Merging narration with visuals...")
        final_path = os.path.join(output_dir, "story_output.mp4")
        _merge_audio_video(visual_concat, full_narration_path, final_path)

    # Auto-find background music if none provided
    if not music_path and auto_music:
        music_genre = VOICE_MUSIC_MAP.get(voice, "cinematic background")
        print(f"\n-> Auto-searching background music: \"{music_genre}\"...")
        from .music import suggest_and_pick_music
        music_path = suggest_and_pick_music("cinematic", "narrated story", output_dir, genre=music_genre)

    # Mix background music
    if music_path and os.path.exists(music_path):
        print("-> Adding background music...")
        from .render import mix_music
        music_out = final_path + ".music.mp4"
        mix_music(final_path, music_path, music_out,
                  original_volume=1.0, music_volume=music_volume)
        os.replace(music_out, final_path)

    print(f"\n-> Story video saved: {final_path}")
    return final_path


def _burn_subtitle(input_path: str, text: str, duration: float, output_path: str) -> None:
    """Burn subtitle text onto a video clip with fade-in animation."""
    # Escape special characters for ffmpeg drawtext
    escaped = text.replace("\\", "\\\\").replace("'", "’").replace(":", "\\:").replace("%", "%%")
    # Word wrap: insert newline every ~30 chars at word boundary
    words = escaped.split()
    lines = []
    current_line = ""
    for word in words:
        if len(current_line) + len(word) + 1 > 30:
            lines.append(current_line)
            current_line = word
        else:
            current_line = f"{current_line} {word}" if current_line else word
    if current_line:
        lines.append(current_line)
    wrapped_text = "\n".join(lines)

    # Subtitle style: white text with black background box, centered at bottom
    vf = (
        f"drawtext=text='{wrapped_text}':"
        f"fontfile=/System/Library/Fonts/Supplemental/Arial Bold.ttf:"
        f"fontsize=42:fontcolor=white:"
        f"borderw=2:bordercolor=black:"
        f"box=1:boxcolor=black@0.5:boxborderw=15:"
        f"x=(w-text_w)/2:y=h-text_h-200:"
        f"enable='between(t,0.3,{duration:.2f})'"
    )
    cmd = [
        FFMPEG, "-y",
        "-i", input_path,
        "-vf", vf,
        "-c:a", "copy",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # If subtitle burn fails, just copy the video as-is
        import shutil
        shutil.copy2(input_path, output_path)


def _make_text_card(text: str, duration: float, output_path: str) -> None:
    """Create a simple text-on-black video as fallback."""
    # Escape special chars for ffmpeg drawtext
    escaped = text.replace("'", "\\'").replace(":", "\\:")
    vf = (
        f"color=c=black:s=1080x1920:d={duration},"
        f"drawtext=text='{escaped}':"
        f"fontcolor=white:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2:"
        f"fontfile=/System/Library/Fonts/Supplemental/Arial.ttf"
    )
    cmd = [
        FFMPEG, "-y",
        "-f", "lavfi", "-i", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-t", str(duration),
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Ultra fallback: just black video
        cmd2 = [
            FFMPEG, "-y",
            "-f", "lavfi", "-i", f"color=c=black:s=1080x1920:d={duration}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-t", str(duration),
            output_path,
        ]
        subprocess.run(cmd2, capture_output=True, text=True)
