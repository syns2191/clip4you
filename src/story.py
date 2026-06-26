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
from .render import FFMPEG, reframe_vertical, burn_captions, add_film_grain, add_text_hook, burn_thought_bubbles, burn_footnote, detect_head_position, click_head_position
from .narration import generate_narration, generate_silence, is_silent_scene, SentenceTiming, POPULAR_VOICES, MOOD_VOICE_SETTINGS
from .transcribe import transcribe, transcribe_audio, Word
from .captions import build_ass
from .imagegen import generate_scene_image, generate_scene_video, get_variant_paths

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
    timings: List[SentenceTiming] = field(default_factory=list)
    words: List[Word] = field(default_factory=list)
    head_pos: Optional[tuple] = None


@dataclass
class BubbleGroup:
    group_idx: int
    side: str
    chunks: list
    group_start: float
    group_end: float
    head_pos: Optional[tuple] = None


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

    # Ensure every scene has a visual query — fill empty ones from neighbors
    for i, scene in enumerate(scenes):
        if not scene.search_query or not scene.search_query.strip():
            if i > 0 and scenes[i - 1].search_query:
                scene.search_query = scenes[i - 1].search_query
            elif i + 1 < len(scenes) and scenes[i + 1].search_query:
                scene.search_query = scenes[i + 1].search_query
            else:
                scene.search_query = "cinematic background"

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


def _generate_hook_text(script: str) -> str:
    """Use LLM to generate a short hook/summary text for the video intro overlay."""
    prompt = (
        "You are an expert short-form video editor. Given the following narration script, "
        "write a single short hook line (max 6 words) that would appear as "
        "a text overlay at the start of the video to grab the viewer's attention.\n\n"
        "The hook should tease the core topic or create curiosity. "
        "Use natural capitalization (capitalize first letter only, not all caps). "
        "Examples: 'The truth nobody tells you', 'Why most people fail', "
        "'This changed everything'\n\n"
        f"Script:\n{script}\n\n"
        "Return ONLY the hook text, nothing else. Max 6 words."
    )

    try:
        if settings.llm_provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            response = client.messages.create(
                model=settings.anthropic_model,
                max_tokens=50,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = "".join(b.text for b in response.content if b.type == "text").strip()
        elif settings.llm_provider == "groq":
            from groq import Groq
            client = Groq(api_key=settings.groq_api_key)
            response = client.chat.completions.create(
                model=settings.groq_model,
                max_tokens=50,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.choices[0].message.content.strip()
        else:
            return ""
    except Exception:
        return ""

    hook = raw.strip().strip('"').strip("'")
    words = hook.split()
    if len(words) > 6:
        hook = " ".join(words[:6])
    return hook


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


ANIMATION_PRESETS = [
    "zoom-in", "zoom-out", "pan-left", "pan-right",
    "pan-up", "pan-down", "zoom-pan", "ken-burns", "static",
]

_KEN_BURNS_CYCLE = ["zoom-in", "pan-right", "zoom-out", "pan-left", "zoom-pan", "pan-up"]
_ken_burns_idx = 0


def _get_zoompan_expr(animation: str, frames: int, w: int, h: int) -> str:
    """Build the zoompan filter expression for a given animation preset."""
    d = frames
    zoom_in_step = 0.2 / max(d, 1)
    zoom_out_step = 0.3 / max(d, 1)
    if animation == "zoom-in":
        return f"zoompan=z='min(zoom+{zoom_in_step:.6f},1.2)':d={d}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps=25"
    elif animation == "zoom-out":
        return f"zoompan=z='if(eq(on,1),1.3,max(zoom-{zoom_out_step:.6f},1.0))':d={d}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps=25"
    elif animation == "pan-left":
        return f"zoompan=z=1.1:d={d}:x='iw*0.15*(1-on/{d})':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps=25"
    elif animation == "pan-right":
        return f"zoompan=z=1.1:d={d}:x='iw*0.15*on/{d}':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps=25"
    elif animation == "pan-up":
        return f"zoompan=z=1.1:d={d}:x='iw/2-(iw/zoom/2)':y='ih*0.15*(1-on/{d})':s={w}x{h}:fps=25"
    elif animation == "pan-down":
        return f"zoompan=z=1.1:d={d}:x='iw/2-(iw/zoom/2)':y='ih*0.15*on/{d}':s={w}x{h}:fps=25"
    elif animation == "zoom-pan":
        return f"zoompan=z='min(zoom+{zoom_in_step:.6f},1.2)':d={d}:x='iw*0.1*on/{d}':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps=25"
    else:  # static
        return f"zoompan=z=1:d={d}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps=25"


def _image_to_video(image_path: str, duration: float, output_path: str, animation: str = "ken-burns") -> None:
    """Convert a static image to a video with selectable animation effect."""
    global _ken_burns_idx
    w = settings.vertical_width
    h = settings.vertical_height
    frames = int(duration * 25)

    # Ken Burns mode cycles through different effects per scene
    if animation == "ken-burns":
        actual = _KEN_BURNS_CYCLE[_ken_burns_idx % len(_KEN_BURNS_CYCLE)]
        _ken_burns_idx += 1
    else:
        actual = animation

    zoompan_expr = _get_zoompan_expr(actual, frames, w, h)

    vf = (
        f"split[bg][fg];"
        f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},boxblur=25:5[blurred];"
        f"[fg]scale={w}:{h}:force_original_aspect_ratio=decrease[scaled];"
        f"[blurred][scaled]overlay=(W-w)/2:(H-h)/2[composed];"
        f"[composed]{zoompan_expr},"
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
        vf_simple = (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,"
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


def _concat_scenes_with_audio(scene_videos: List[str], output_path: str) -> None:
    """Concatenate scene videos keeping their audio tracks (for Veo)."""
    if len(scene_videos) == 1:
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
        "-c:a", "aac",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    os.unlink(list_file)
    if result.returncode != 0:
        raise RuntimeError(f"Concat with audio failed:\n{result.stderr[-1000:]}")


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
    art_style: str = "",
    image_category: str = "",
    animation: str = "ken-burns",
    film_grain: str = "",
    caption_style: str = "default",
    caption_font: str = "",
    caption_animation: str = "karaoke",
    hook_text: str = "",
    review_images: bool = False,
    footnote: str = "",
) -> str:
    """Create a short narrated video from a script.

    Returns the path to the final output video.
    """
    os.makedirs(output_dir, exist_ok=True)

    print("-> Splitting script into scenes...")
    scenes = _split_into_scenes(script)
    has_timeline = any(s.duration > 0 for s in scenes)
    print(f"   {len(scenes)} scenes identified" + (" (with timeline)" if has_timeline else ""))

    resolved_hook = ""
    if hook_text == "auto":
        print("-> Generating intro hook text...")
        resolved_hook = _generate_hook_text(script)
        if resolved_hook:
            print(f'   Hook: "{resolved_hook}"')
        else:
            print("   Warning: could not generate hook text")
    elif hook_text:
        resolved_hook = hook_text
        print(f'-> Using custom hook text: "{resolved_hook}"')

    use_veo_audio = (visuals == "veo")

    scene_audios = []
    with tempfile.TemporaryDirectory() as tmp:
        if use_veo_audio:
            print("-> Skipping TTS (Veo generates voice + sound effects)...")
            # Still need scene durations from timeline or defaults
            for i, scene in enumerate(scenes):
                if scene.duration <= 0:
                    scene.duration = 8.0  # Veo generates 5-8s clips
                print(f"   Scene {i+1}: {scene.duration:.1f}s - \"{scene.text[:50]}\"")
        else:
            # Generate TTS per scene
            print("-> Generating narration audio...")
            voice_name = POPULAR_VOICES.get(voice, voice)
            if voice_rate:
                tts_rate = voice_rate
            elif voice in ("warm", "caring", "storyteller", "dark", "tension"):
                tts_rate = "-25%"
            else:
                tts_rate = "-15%"
            print(f"   Voice: {voice_name} | Rate: {tts_rate}")

            for i, scene in enumerate(scenes):
                audio_path = os.path.join(tmp, f"scene_{i:02d}.mp3")

                # Check for silent scenes
                if is_silent_scene(scene.text):
                    silent_dur = scene.duration if scene.duration > 0 else 3.0
                    generate_silence(audio_path, silent_dur)
                    if scene.duration <= 0:
                        scene.duration = silent_dur
                    scene.audio_path = audio_path
                    scene_audios.append(audio_path)
                    print(f"   Scene {i+1}: {scene.duration:.1f}s (silent) - \"{scene.text[:50]}\"")
                    continue

                s_voice = voice_name
                s_rate = tts_rate
                s_pitch = "+0Hz"
                s_mood = ""

                # Mood changes intonation (pitch + rate) only, keeps the same voice actor
                if scene.mood and scene.mood in MOOD_VOICE_SETTINGS:
                    ms = MOOD_VOICE_SETTINGS[scene.mood]
                    s_rate = ms["rate"]
                    s_pitch = ms["pitch"]
                    s_mood = scene.mood
                elif scene.mood and scene.mood in MOOD_PRESETS:
                    preset = MOOD_PRESETS[scene.mood]
                    s_rate = preset["rate"]

                # Explicit voice/rate override from script line
                if scene.voice:
                    s_voice = POPULAR_VOICES.get(scene.voice, scene.voice)
                if scene.rate:
                    s_rate = scene.rate

                mood_label = f" [{scene.mood}]" if scene.mood else ""
                _, scene.timings = generate_narration(scene.text, audio_path, voice=s_voice, rate=s_rate, pitch=s_pitch, mood=s_mood)
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

        if not use_veo_audio:
            # Build full narration audio: each scene's TTS padded with silence to match timeline
            print("-> Building timed narration track...")
            padded_audios = []
            for i, scene in enumerate(scenes):
                padded_path = os.path.join(tmp, f"padded_{i:02d}.mp3")
                _pad_audio_to_duration(scene.audio_path, scene.duration, padded_path)
                padded_audios.append(padded_path)

        full_narration_path = None
        if not use_veo_audio:
            full_narration_path = os.path.join(output_dir, "narration_full.mp3")
            _concat_audios(padded_audios, full_narration_path)

        # Generate/download visuals for each scene
        use_ai_visuals = visuals in ("openai", "sd", "veo")
        if use_ai_visuals:
            from .imagegen import ART_STYLES, CATEGORY_STYLES
            style_label = ""
            if art_style and art_style in ART_STYLES:
                style_label = f", style: {ART_STYLES[art_style]['name']}"
            elif image_category and image_category in CATEGORY_STYLES:
                resolved = CATEGORY_STYLES[image_category]["style"]
                style_label = f", category: {image_category} → {ART_STYLES[resolved]['name']}"
            if visuals == "veo":
                print(f"\n-> Generating AI videos with Google Veo{style_label} for each scene...")
            else:
                print(f"\n-> Generating AI illustrations ({visuals}{style_label}) for each scene...")
        else:
            print("\n-> Downloading visuals for each scene...")
        scene_videos = []

        # Build consistent visual style suffix for download queries
        # This ensures all downloaded images share the same visual theme
        _style_suffix = ""
        _fallback_theme = ["cinematic landscape", "moody atmospheric", "dark dramatic"]
        if art_style:
            from .imagegen import ART_STYLES
            s = ART_STYLES.get(art_style)
            if s:
                # Extract key visual terms for search
                _style_map = {
                    "pen": "ink drawing illustration",
                    "pencil": "pencil sketch drawing",
                    "watercolor": "watercolor painting art",
                    "anime": "anime illustration art",
                    "ghibli": "studio ghibli anime art",
                    "cinematic": "cinematic dramatic photography",
                    "oil": "oil painting classical art",
                    "comic": "comic book illustration",
                    "minimal": "minimalist clean design",
                    "pixel": "pixel art retro",
                    "charcoal": "charcoal drawing dark",
                    "storybook": "storybook illustration children",
                    "realistic": "photography realistic 4k",
                    "stickfigure": "simple drawing whiteboard",
                    "sketch": "pencil sketch graphite drawing",
                }
                _style_suffix = " " + _style_map.get(art_style, s["name"].lower())
                _fallback_theme = [
                    f"{_style_map.get(art_style, '')} background",
                    f"{_style_map.get(art_style, '')} scene",
                    f"{_style_map.get(art_style, '')} mood",
                ]
        elif image_category:
            from .imagegen import CATEGORY_STYLES
            cat = CATEGORY_STYLES.get(image_category)
            if cat:
                _style_suffix = " " + cat["mood"].split()[0]  # first mood word
                _fallback_theme = [
                    f"{cat['mood']} landscape",
                    f"{cat['mood']} atmosphere",
                    f"{cat['mood']} scene",
                ]

        if _style_suffix:
            print(f"   Visual theme: \"{_style_suffix.strip()}\" (applied to all searches)")

        def _generate_scene_visual(i, scene, visual_path, video_path, styled_query):
            """Generate or download visual for a single scene. Returns (got_visual, img_path_or_None)."""
            got_visual = False
            scene_img_path = None

            if use_ai_visuals:
                if visuals == "veo":
                    veo_path = visual_path + "_veo.mp4"
                    if generate_scene_video(scene.text, scene.search_query, veo_path, duration=scene.duration, art_style=art_style, category=image_category):
                        _trim_video_to_duration(veo_path, scene.duration, video_path)
                        got_visual = True
                        print(f"      [Veo video generated]")
                else:
                    ai_img_path = visual_path + "_ai.png"
                    if generate_scene_image(scene.text, scene.search_query, ai_img_path, provider=visuals, art_style=art_style, category=image_category):
                        if caption_style == "bubble":
                            scene.head_pos = detect_head_position(ai_img_path, video_w=settings.vertical_width, video_h=settings.vertical_height)
                            if scene.head_pos:
                                print(f"      [Face detected at {scene.head_pos}]")
                        scene_img_path = ai_img_path
                        _image_to_video(ai_img_path, scene.duration, video_path, animation=animation)
                        got_visual = True
                        print(f"      [AI illustration generated]")

            if not got_visual and scene.visual_type == "video":
                pexels_path = visual_path + "_pexels.mp4"
                if _download_pexels_video(styled_query, pexels_path):
                    reframed = visual_path + "_reframed.mp4"
                    reframe_vertical(pexels_path, reframed, mode="crop")
                    _trim_video_to_duration(reframed, scene.duration, video_path)
                    got_visual = True
                    print(f"      [Pexels video]")

                if not got_visual:
                    yt_path = visual_path + "_yt.mp4"
                    if _download_youtube_clip(styled_query + " stock footage", yt_path):
                        reframed = visual_path + "_reframed.mp4"
                        reframe_vertical(yt_path, reframed, mode="crop")
                        _trim_video_to_duration(reframed, scene.duration, video_path)
                        got_visual = True
                        print(f"      [YouTube video]")

            if not got_visual:
                img_path = visual_path + ".jpg"
                if _download_scene_image(styled_query, img_path):
                    if caption_style == "bubble" and not scene.head_pos:
                        scene.head_pos = detect_head_position(img_path, video_w=settings.vertical_width, video_h=settings.vertical_height)
                    scene_img_path = img_path
                    _image_to_video(img_path, scene.duration, video_path, animation=animation)
                    got_visual = True
                    print(f"      [Image found]")

            if not got_visual:
                fallback_img = visual_path + "_fb.jpg"
                words = scene.search_query.split()
                fallback_queries = []
                if len(words) > 2:
                    fallback_queries.append(" ".join(words[:2]) + _style_suffix)
                fallback_queries.extend(_fallback_theme)
                for fq in fallback_queries:
                    if _download_scene_image(fq, fallback_img):
                        scene_img_path = fallback_img
                        _image_to_video(fallback_img, scene.duration, video_path, animation=animation)
                        got_visual = True
                        print(f"      [Fallback image: {fq}]")
                        break

            if not got_visual:
                print(f"      [Text card - no visual found]")
                _make_text_card(scene.text[:80], scene.duration, video_path)

            return got_visual, scene_img_path

        # Generate all scene visuals
        scene_img_paths = []
        for i, scene in enumerate(scenes):
            styled_query = scene.search_query + _style_suffix
            print(f"   Scene {i+1}/{len(scenes)}: \"{styled_query}\" ({scene.duration:.1f}s)")
            visual_path = os.path.join(tmp, f"visual_{i:02d}")
            video_path = os.path.join(tmp, f"scene_video_{i:02d}.mp4")
            got_visual, img_path = _generate_scene_visual(i, scene, visual_path, video_path, styled_query)
            scene_img_paths.append(img_path)
            scene_videos.append(video_path)

        # Review & regenerate loop
        if review_images and use_ai_visuals and visuals != "veo":
            # Copy images to output dir for easy preview
            review_dir = os.path.join(output_dir, "_review")
            os.makedirs(review_dir, exist_ok=True)

            # Collect all variants per scene
            scene_variants = []
            for i, img_path in enumerate(scene_img_paths):
                if img_path:
                    variants = get_variant_paths(img_path)
                else:
                    variants = []
                scene_variants.append(variants)
                for vi, vp in enumerate(variants):
                    ext = os.path.splitext(vp)[1] or ".png"
                    if len(variants) > 1:
                        preview_path = os.path.join(review_dir, f"scene_{i+1:02d}_v{vi+1}{ext}")
                    else:
                        preview_path = os.path.join(review_dir, f"scene_{i+1:02d}{ext}")
                    shutil.copy2(vp, preview_path)

            # Open preview folder
            print(f"\n   Preview images saved to: {review_dir}")
            try:
                subprocess.run(["open", review_dir], capture_output=True)
            except Exception:
                pass

            while True:
                print("\n" + "=" * 60)
                print("  SCENE IMAGE REVIEW")
                print("=" * 60)
                for i, scene in enumerate(scenes):
                    has_img = scene_img_paths[i] is not None
                    text_preview = scene.text[:40]
                    status = "OK" if has_img else "no img"
                    if scene.head_pos:
                        head_label = f"{scene.head_pos[0]},{scene.head_pos[1]}"
                    else:
                        head_label = "none"
                    nv = len(scene_variants[i]) if i < len(scene_variants) else 0
                    var_label = f"{nv} variants" if nv > 1 else ""
                    print(f"  [{i+1}] [{status:6s}] [head: {head_label:10s}] {var_label:12s} \"{text_preview}\"")
                print("=" * 60)
                print("Commands:")
                print("  2,4              — regenerate scenes 2 and 4")
                print("  open 3           — open scene 3 image in Preview")
                print("  pick 3           — open all variants, click to pick")
                print("  pick 3 2         — use variant 2 for scene 3")
                print("  head 3           — click to tag head position")
                print("  head 3 540 300   — set head position (pixels)")
                print("  head 3 50% 15%   — set head position (percentage)")
                print("  head 3 auto      — re-run auto detection")
                print("  head 3 none      — clear head position")
                print("  done             — continue to render")
                choice = input("> ").strip()
                choice_lower = choice.lower()

                if choice_lower in ("done", "d", "ok", "continue", "c"):
                    break

                if choice_lower == "open" or choice_lower == "o":
                    try:
                        subprocess.run(["open", review_dir], capture_output=True)
                    except Exception:
                        pass
                    continue

                if choice_lower.startswith("open ") or choice_lower.startswith("o "):
                    try:
                        idx = int(choice_lower.split()[-1]) - 1
                        if 0 <= idx < len(scene_img_paths) and scene_img_paths[idx]:
                            variants = scene_variants[idx] if idx < len(scene_variants) else []
                            if len(variants) > 1:
                                for vi, vp in enumerate(variants):
                                    ext = os.path.splitext(vp)[1] or ".png"
                                    pv = os.path.join(review_dir, f"scene_{idx+1:02d}_v{vi+1}{ext}")
                                    if os.path.exists(pv):
                                        subprocess.run(["open", pv], capture_output=True)
                            else:
                                ext = os.path.splitext(scene_img_paths[idx])[1] or ".png"
                                preview = os.path.join(review_dir, f"scene_{idx+1:02d}{ext}")
                                if os.path.exists(preview):
                                    subprocess.run(["open", preview], capture_output=True)
                                else:
                                    print(f"  No image for scene {idx+1}")
                        else:
                            print(f"  No image for scene {idx+1}")
                    except (ValueError, IndexError):
                        print("  Usage: open 3")
                    continue

                if choice_lower.startswith("pick ") or choice_lower.startswith("p "):
                    parts = choice.split()
                    if len(parts) < 2:
                        print("  Usage: pick 3 [variant#]")
                        continue
                    try:
                        idx = int(parts[1]) - 1
                    except ValueError:
                        print("  Usage: pick 3 [variant#]")
                        continue
                    if idx < 0 or idx >= len(scenes):
                        print(f"  Scene {idx+1} out of range")
                        continue
                    variants = scene_variants[idx] if idx < len(scene_variants) else []
                    if not variants:
                        print(f"  No variants for scene {idx+1}")
                        continue

                    if len(parts) == 2:
                        # Open all variants for viewing
                        for vi, vp in enumerate(variants):
                            ext = os.path.splitext(vp)[1] or ".png"
                            pv = os.path.join(review_dir, f"scene_{idx+1:02d}_v{vi+1}{ext}")
                            if os.path.exists(pv):
                                subprocess.run(["open", pv], capture_output=True)
                        print(f"  Opened {len(variants)} variants. Type: pick {idx+1} <variant#>")
                    elif len(parts) == 3:
                        try:
                            vi = int(parts[2]) - 1
                        except ValueError:
                            print(f"  Usage: pick {idx+1} 2")
                            continue
                        if vi < 0 or vi >= len(variants):
                            print(f"  Variant {vi+1} out of range (1-{len(variants)})")
                            continue
                        chosen = variants[vi]
                        scene_img_paths[idx] = chosen
                        scene.head_pos = None
                        # Re-create video from chosen variant
                        video_path = os.path.join(tmp, f"scene_video_{idx:02d}.mp4")
                        _image_to_video(chosen, scenes[idx].duration, video_path, animation=animation)
                        scene_videos[idx] = video_path
                        if caption_style == "bubble":
                            scenes[idx].head_pos = detect_head_position(chosen, video_w=settings.vertical_width, video_h=settings.vertical_height)
                        # Update main preview
                        ext = os.path.splitext(chosen)[1] or ".png"
                        preview_path = os.path.join(review_dir, f"scene_{idx+1:02d}{ext}")
                        shutil.copy2(chosen, preview_path)
                        print(f"  Scene {idx+1}: using variant {vi+1}")
                    continue

                if choice_lower.startswith("head ") or choice_lower.startswith("h "):
                    parts = choice.split()
                    if len(parts) < 2:
                        print("  Usage: head 3 [x y | auto | none]")
                        continue
                    try:
                        idx = int(parts[1]) - 1
                    except ValueError:
                        print("  Usage: head 3 [x y | auto | none]")
                        continue
                    if idx < 0 or idx >= len(scenes):
                        print(f"  Scene {idx+1} out of range")
                        continue

                    if len(parts) == 2:
                        img_path = scene_img_paths[idx]
                        if img_path and os.path.exists(img_path):
                            print(f"  Opening scene {idx+1} — click on the head position...")
                            pos = click_head_position(
                                img_path,
                                video_w=settings.vertical_width,
                                video_h=settings.vertical_height,
                                current_head_pos=scenes[idx].head_pos,
                            )
                            if pos:
                                scenes[idx].head_pos = pos
                                print(f"  Scene {idx+1}: head set to ({pos[0]}, {pos[1]})")
                            else:
                                print(f"  Scene {idx+1}: cancelled (window closed)")
                        else:
                            print(f"  No image for scene {idx+1}")
                    elif len(parts) == 3 and parts[2].lower() == "auto":
                        img_path = scene_img_paths[idx]
                        if img_path and os.path.exists(img_path):
                            scenes[idx].head_pos = detect_head_position(
                                img_path,
                                video_w=settings.vertical_width,
                                video_h=settings.vertical_height,
                            )
                            pos = scenes[idx].head_pos
                            print(f"  Scene {idx+1}: head auto-detected at {pos}" if pos else f"  Scene {idx+1}: no head detected")
                        else:
                            print(f"  No image for scene {idx+1}")
                    elif len(parts) == 3 and parts[2].lower() == "none":
                        scenes[idx].head_pos = None
                        print(f"  Scene {idx+1}: head position cleared")
                    elif len(parts) == 4:
                        try:
                            vw = settings.vertical_width
                            vh = settings.vertical_height
                            xval, yval = parts[2], parts[3]
                            if xval.endswith("%"):
                                hx = int(float(xval.rstrip("%")) / 100 * vw)
                            else:
                                hx = int(xval)
                            if yval.endswith("%"):
                                hy = int(float(yval.rstrip("%")) / 100 * vh)
                            else:
                                hy = int(yval)
                            hx = max(0, min(hx, vw))
                            hy = max(0, min(hy, vh))
                            scenes[idx].head_pos = (hx, hy)
                            print(f"  Scene {idx+1}: head set to ({hx}, {hy})")
                        except (ValueError, IndexError):
                            print("  Usage: head 3 540 300  or  head 3 50% 15%")
                    else:
                        print("  Usage: head 3 [x y | auto | none]")
                    continue

                if not choice_lower:
                    continue

                try:
                    indices = [int(x.strip()) - 1 for x in choice_lower.split(",")]
                except ValueError:
                    print("Invalid input. Type scene numbers (e.g. '2,4'), 'head 3 540 300', or 'done'.")
                    continue

                for idx in indices:
                    if idx < 0 or idx >= len(scenes):
                        print(f"  Scene {idx+1} out of range, skipping")
                        continue
                    scene = scenes[idx]
                    scene.head_pos = None
                    styled_query = scene.search_query + _style_suffix
                    print(f"\n   Regenerating scene {idx+1}...")
                    visual_path = os.path.join(tmp, f"visual_{idx:02d}_regen")
                    video_path = os.path.join(tmp, f"scene_video_{idx:02d}.mp4")

                    # Clear cached image so SD generates a new one
                    from .imagegen import _cache_key, CACHE_IMG_DIR
                    cache_k = _cache_key(f"img:{visuals}:{art_style}:{image_category}:{scene.text}:{scene.search_query}")
                    for ext in (".png", ".jpg", ".webp"):
                        cached = os.path.join(CACHE_IMG_DIR, cache_k + ext)
                        if os.path.exists(cached):
                            os.unlink(cached)
                            print(f"      [Cleared cached image]")

                    got_visual, img_path = _generate_scene_visual(idx, scene, visual_path, video_path, styled_query)
                    scene_img_paths[idx] = img_path
                    scene_videos[idx] = video_path

                    # Update variants and preview
                    if img_path:
                        variants = get_variant_paths(img_path)
                    else:
                        variants = []
                    scene_variants[idx] = variants
                    # Remove old preview files for this scene
                    for f in os.listdir(review_dir):
                        if f.startswith(f"scene_{idx+1:02d}"):
                            os.unlink(os.path.join(review_dir, f))
                    for vi, vp in enumerate(variants):
                        ext = os.path.splitext(vp)[1] or ".png"
                        if len(variants) > 1:
                            pv = os.path.join(review_dir, f"scene_{idx+1:02d}_v{vi+1}{ext}")
                        else:
                            pv = os.path.join(review_dir, f"scene_{idx+1:02d}{ext}")
                        shutil.copy2(vp, pv)

                print(f"\n   Regeneration complete.")

            # Cleanup review dir
            shutil.rmtree(review_dir, ignore_errors=True)

        # Concatenate all scene videos
        print("\n-> Stitching scenes with transitions...")
        final_path = os.path.join(output_dir, "story_output.mp4")

        if use_veo_audio:
            # Veo scenes have their own audio — concat with audio preserved
            visual_concat = os.path.join(tmp, "visual_concat.mp4")
            _concat_scenes_with_audio(scene_videos, visual_concat)
            shutil.copy2(visual_concat, final_path)
        else:
            visual_concat = os.path.join(tmp, "visual_concat.mp4")
            _concat_with_transitions(scene_videos, visual_concat)
            print("-> Merging narration with visuals...")
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

    # Transcribe the final video and burn captions (skip for Veo)
    if not use_veo_audio:
        print("\n-> Transcribing final video for word-level captions...")
        try:
            segments = transcribe(final_path)
            words = [w for seg in segments for w in seg.words]
            if words:
                if caption_style == "bubble":
                    from .captions import WORDS_PER_CHUNK

                    head_positions = [s.head_pos for s in scenes]
                    xfade_dur = 0.8 if len(scenes) > 1 else 0.0
                    cumulative = 0.0
                    scene_times = []
                    for i, s in enumerate(scenes):
                        s_start = cumulative
                        s_end = cumulative + s.duration
                        if i > 0:
                            s_start += xfade_dur / 2
                        if i < len(scenes) - 1:
                            s_end -= xfade_dur / 2
                        scene_times.append((s_start, s_end))
                        cumulative += s.duration
                        if i < len(scenes) - 1:
                            cumulative -= xfade_dur

                    bubble_groups = []
                    for scene_idx, (s_start, s_end) in enumerate(scene_times):
                        scene_words = [w for w in words if w.start >= s_start and w.end <= s_end]
                        if not scene_words:
                            continue
                        side = "left" if scene_idx % 2 == 0 else "right"
                        head = head_positions[scene_idx] if scene_idx < len(head_positions) else None

                        sub_chunks = []
                        for ci in range(0, len(scene_words), WORDS_PER_CHUNK):
                            chunk = scene_words[ci:ci + WORDS_PER_CHUNK]
                            if not chunk:
                                continue

                            if caption_animation == "karaoke":
                                text = " ".join(w.text for w in chunk)
                                start = chunk[0].start
                                end = chunk[-1].end
                                if end > start:
                                    sub_chunks.append((text, start, end))

                            elif caption_animation == "word":
                                for word_idx in range(len(chunk)):
                                    text = " ".join(w.text for w in chunk[:word_idx + 1])
                                    start = chunk[word_idx].start
                                    end = chunk[word_idx + 1].start if word_idx + 1 < len(chunk) else chunk[-1].end
                                    if end > start:
                                        sub_chunks.append((text, start, end))

                            else:  # typing
                                for word_idx, word in enumerate(chunk):
                                    w_start = word.start
                                    w_end = word.end
                                    if w_end <= w_start:
                                        continue
                                    prev_text = " ".join(w.text for w in chunk[:word_idx])
                                    cur_word = word.text
                                    n_chars = len(cur_word)
                                    char_dur = (w_end - w_start) / max(n_chars, 1)
                                    for char_i in range(1, n_chars + 1):
                                        partial = cur_word[:char_i]
                                        parts = [prev_text, partial] if prev_text else [partial]
                                        text = " ".join(parts)
                                        start = w_start + (char_i - 1) * char_dur
                                        end = w_start + char_i * char_dur if char_i < n_chars else w_end
                                        if end > start:
                                            sub_chunks.append((text, start, end))
                                if sub_chunks:
                                    chunk_end = chunk[-1].end
                                    last_text, last_start, last_end = sub_chunks[-1]
                                    if last_start < chunk_end:
                                        sub_chunks[-1] = (last_text, last_start, chunk_end)

                        if sub_chunks:
                            bubble_groups.append(BubbleGroup(
                                group_idx=scene_idx,
                                side=side,
                                chunks=sub_chunks,
                                group_start=s_start,
                                group_end=s_end,
                                head_pos=head,
                            ))

                    detected = sum(1 for h in head_positions if h)
                    print(f"   Burning {len(bubble_groups)} animated thought bubbles ({detected}/{len(scenes)} faces detected)...")
                    captioned_path = final_path + ".captioned.mp4"
                    burn_thought_bubbles(
                        final_path, captioned_path, bubble_groups,
                        tmp_dir=output_dir,
                        caption_font=caption_font,
                    )
                    os.replace(captioned_path, final_path)
                else:
                    ass_path = os.path.join(output_dir, "story_captions.ass")
                    build_ass(words, clip_start=0.0, output_path=ass_path, caption_font=caption_font, caption_animation=caption_animation)
                    captioned_path = final_path + ".captioned.mp4"
                    burn_captions(final_path, ass_path, captioned_path)
                    os.replace(captioned_path, final_path)
                    print(f"   Burned {len(words)} word-level captions")
            else:
                print("   No words detected, skipping captions")
        except Exception as e:
            print(f"   Warning: caption transcription failed ({e}), video saved without captions")

    # Apply hook text overlay on intro
    if resolved_hook:
        print(f"-> Adding hook text overlay to intro...")
        hook_duration = min(scenes[0].duration if scenes else 5.0, 5.0)
        hooked_path = final_path + ".hooked.mp4"
        add_text_hook(final_path, resolved_hook, hooked_path, clip_duration=hook_duration, caption_font=caption_font)
        os.replace(hooked_path, final_path)

    # Burn footnote on outro
    if footnote:
        print(f"-> Adding footnote to outro...")
        total_dur = _get_audio_duration(final_path)
        outro_dur = scenes[-1].duration if scenes else 5.0
        fn_path = final_path + ".footnote.mp4"
        burn_footnote(final_path, fn_path, footnote, video_duration=total_dur,
                      outro_duration=outro_dur, caption_font=caption_font)
        os.replace(fn_path, final_path)

    # Apply film grain effect
    if film_grain:
        print(f"-> Applying {film_grain} film grain effect...")
        grain_path = final_path + ".grain.mp4"
        add_film_grain(final_path, grain_path, intensity=film_grain)
        os.replace(grain_path, final_path)

    print(f"\n-> Story video saved: {final_path}")
    return final_path


def _escape_drawtext(text: str) -> str:
    """Escape text for ffmpeg drawtext filter."""
    t = text
    t = t.replace("\\", "\\\\")
    t = t.replace("'", "\\'")
    t = t.replace(":", "\\:")
    t = t.replace("%", "%%")
    t = t.replace('"', '\\"')
    return t


def _wrap_text(text: str, max_chars: int = 25) -> str:
    """Word-wrap text for subtitle display."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 > max_chars:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        lines.append(current)
    return "\n".join(lines)


def _build_typewriter_filters(
    words: List[str],
    start: float,
    end: float,
    fontfile: str,
    y_base: str = "h-text_h-180",
) -> List[str]:
    """Build drawtext filters that reveal words one by one (typewriter effect).
    Each word appears at a staggered time within the sentence duration."""
    if not words:
        return []

    total_dur = end - start
    fade_out_dur = 0.4
    # Time per word reveal — spread words evenly across ~70% of duration
    typing_window = total_dur * 0.7
    delay_per_word = typing_window / max(len(words), 1)

    filters = []
    for i in range(len(words)):
        # Show accumulated words up to this point
        partial_text = " ".join(words[:i + 1])
        escaped = _escape_drawtext(partial_text)
        wrapped = _wrap_text(escaped)

        word_start = start + (i * delay_per_word)
        # Next word replaces this one, or this is the last
        if i < len(words) - 1:
            word_end = start + ((i + 1) * delay_per_word)
        else:
            word_end = end

        # Alpha: appear instantly, hold, fade out at sentence end (only last word fades)
        if i < len(words) - 1:
            alpha = (
                f"if(between(t\\,{word_start:.2f}\\,{word_end:.2f})\\,1\\,0)"
            )
        else:
            alpha = (
                f"if(lt(t\\,{word_start:.2f})\\,0\\,"
                f"if(lt(t\\,{end - fade_out_dur:.2f})\\,1\\,"
                f"if(lt(t\\,{end:.2f})\\,({end:.2f}-t)/{fade_out_dur:.2f}\\,"
                f"0)))"
            )

        filters.append(
            f"drawtext=text='{wrapped}':"
            f"fontfile={fontfile}:"
            f"fontsize=46:fontcolor=white:"
            f"shadowcolor=black@0.8:shadowx=3:shadowy=3:"
            f"borderw=1:bordercolor=black@0.3:"
            f"x=(w-text_w)/2:y={y_base}:"
            f"alpha='{alpha}'"
        )

    # Blinking cursor after last word
    cursor_start = start
    cursor_end = end - fade_out_dur
    # Cursor x position: after the text. Use a fixed offset since we can't measure dynamically.
    # Blink every 0.5s using mod
    cursor_alpha = (
        f"if(between(t\\,{cursor_start:.2f}\\,{cursor_end:.2f})\\,"
        f"if(lt(mod(t\\,0.8)\\,0.5)\\,1\\,0)\\,0)"
    )
    filters.append(
        f"drawtext=text='|':"
        f"fontfile={fontfile}:"
        f"fontsize=46:fontcolor=white@0.9:"
        f"x=(w/2)+30:y={y_base}:"
        f"alpha='{cursor_alpha}'"
    )

    return filters


def _burn_subtitle(input_path: str, text: str, duration: float, output_path: str,
                   timings: Optional[List] = None) -> None:
    """Burn cinematic typewriter subtitles synced to speech timing.
    Words appear one by one as they are spoken, with a blinking cursor."""
    from .narration import is_silent_scene
    if is_silent_scene(text):
        shutil.copy2(input_path, output_path)
        return

    font_primary = "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"
    font_fallback = "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf"
    font_last = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    fontfile = font_primary
    if not os.path.exists(fontfile):
        fontfile = font_fallback if os.path.exists(font_fallback) else font_last

    all_filters = []

    if timings and len(timings) > 0:
        for st in timings:
            words = st.text.split()
            start = st.start
            end = st.start + st.duration
            all_filters.extend(
                _build_typewriter_filters(words, start, end, fontfile)
            )
    else:
        words = text.split()
        start = 0.3
        end = duration - 0.2
        all_filters.extend(
            _build_typewriter_filters(words, start, end, fontfile)
        )

    if not all_filters:
        shutil.copy2(input_path, output_path)
        return

    vf = ",".join(all_filters)

    cmd = [
        FFMPEG, "-y",
        "-i", input_path,
        "-vf", vf,
        "-c:a", "copy",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        shutil.copy2(input_path, output_path)


def _make_text_card(text: str, duration: float, output_path: str) -> None:
    """Create a simple text-on-black video as fallback."""
    # Escape special chars for ffmpeg drawtext
    escaped = text.replace("'", "\\'").replace(":", "\\:")
    w = settings.vertical_width
    h = settings.vertical_height
    vf = (
        f"color=c=black:s={w}x{h}:d={duration},"
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
        cmd2 = [
            FFMPEG, "-y",
            "-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:d={duration}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-t", str(duration),
            output_path,
        ]
        subprocess.run(cmd2, capture_output=True, text=True)
