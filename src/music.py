"""
AI-suggested background music for short clips.
Uses the LLM to suggest a music mood/genre, searches YouTube for
royalty-free tracks, downloads audio via yt-dlp, and lets the user pick.

Also supports a local music/ folder — if tracks exist there, AI picks
from those first (faster, no download needed).

IMPORTANT: Only searches from verified copyright-safe channels to avoid
Content ID claims.
"""
import json
import os
import subprocess
from dataclasses import dataclass
from typing import List, Optional

from .config import settings

MUSIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "music")

# Verified copyright-safe YouTube channels.
# These channels ONLY upload music that is confirmed free to use
# without Content ID claims.
SAFE_CHANNELS = [
    "UCht8qITGkBvXKsR1Byln-wA",  # NoCopyrightSounds
    "UCHEioEoqyFPvOQfNMGCpyrg",  # Audio Library — Music for content creators
    "UC_aEa8K-EOJ3D6gOs7HcyNg",  # NCS
    "UCCr-efJkFaFxiuNBqRkZiig",  # Vlog No Copyright Music
    "UCc1VKsMXwNHSeGGiECjYdOw",  # Infraction - No Copyright Music
    "UCQKGLOK2FqmVgVwYferltKQ",  # Copyright Free Music
    "UCpDJl2EmP7Oh90Vylx0dZtA",  # Frequency — No Copyright Music
]


@dataclass
class MusicOption:
    title: str
    url: str
    duration: str
    channel: str = ""
    path: Optional[str] = None


def _suggest_search_query(category: str, title: str) -> str:
    """Ask the LLM to suggest a YouTube search query for background music."""
    prompt = (
        f"You are picking background music for a short-form vertical video clip.\n"
        f"Clip category: {category}\n"
        f"Clip title: {title}\n\n"
        f"Suggest a YouTube search query (3-6 words) to find a matching "
        f"royalty-free/no-copyright background music track.\n"
        f"Add 'no copyright' to ensure results are free to use.\n"
        f"Return ONLY the search query, nothing else.\n"
        f"Examples: 'upbeat energetic no copyright music', "
        f"'dark suspenseful no copyright background', "
        f"'funny comedy no copyright music short'"
    )

    if settings.llm_provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=50,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in response.content if b.type == "text").strip().strip('"\'')

    elif settings.llm_provider == "groq":
        from groq import Groq
        client = Groq(api_key=settings.groq_api_key)
        response = client.chat.completions.create(
            model=settings.groq_model,
            max_tokens=50,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip().strip('"\'')

    return f"{category} no copyright background music"


def _search_youtube(query: str, num_results: int = 5, safe_only: bool = True) -> List[MusicOption]:
    """Search YouTube for music tracks using yt-dlp.
    When safe_only=True, only returns results from verified no-copyright channels."""
    # Search more results so we can filter down to safe channels
    search_count = num_results * 4 if safe_only else num_results
    cmd = [
        "yt-dlp",
        f"ytsearch{search_count}:{query}",
        "--dump-json",
        "--flat-playlist",
        "--no-download",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        return []

    options = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        try:
            data = json.loads(line)
            duration_s = data.get("duration") or 0
            if duration_s < 30 or duration_s > 300:
                continue

            # Filter to safe channels only
            if safe_only:
                channel_id = data.get("channel_id") or ""
                channel = data.get("channel") or data.get("uploader") or ""
                channel_lower = channel.lower()
                is_safe = (
                    channel_id in SAFE_CHANNELS
                    or "no copyright" in channel_lower
                    or "copyright free" in channel_lower
                    or "royalty free" in channel_lower
                    or "audio library" in channel_lower
                    or "ncs" in channel_lower
                    or "infraction" in channel_lower
                    or "frequency" in channel_lower
                )
                if not is_safe:
                    continue

            mins = int(duration_s) // 60
            secs = int(duration_s) % 60
            channel_name = data.get("channel") or data.get("uploader") or "Unknown"
            options.append(MusicOption(
                title=data.get("title", "Unknown"),
                url=data.get("url") or data.get("webpage_url") or f"https://youtube.com/watch?v={data.get('id', '')}",
                duration=f"{mins}:{secs:02d}",
                channel=channel_name,
            ))
            if len(options) >= num_results:
                break
        except json.JSONDecodeError:
            continue
    return options


def _download_audio(url: str, output_dir: str, filename: str) -> Optional[str]:
    """Download audio from YouTube URL as mp3."""
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, filename)

    if os.path.exists(output_path):
        return output_path

    cmd = [
        "yt-dlp",
        "-x", "--audio-format", "mp3",
        "-o", output_path,
        "--no-playlist",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    # yt-dlp may add .mp3 extension
    if os.path.exists(output_path):
        return output_path
    if os.path.exists(output_path + ".mp3"):
        return output_path + ".mp3"
    # Check for any file matching the base name
    base = os.path.splitext(output_path)[0]
    for ext in (".mp3", ".m4a", ".opus", ".webm"):
        if os.path.exists(base + ext):
            return base + ext

    return None


def _get_local_tracks() -> List[str]:
    """List all audio files in the music/ folder."""
    if not os.path.isdir(MUSIC_DIR):
        return []
    extensions = (".mp3", ".wav", ".m4a", ".ogg", ".flac")
    return [f for f in os.listdir(MUSIC_DIR) if f.lower().endswith(extensions)]


def _ai_pick_local(tracks: List[str], category: str, title: str) -> Optional[str]:
    """Ask the LLM to pick the best local track."""
    tracks_list = "\n".join(f"  {i+1}. {t}" for i, t in enumerate(tracks))
    prompt = (
        f"Pick background music for a short video clip.\n"
        f"Category: {category} | Title: {title}\n\n"
        f"Available tracks:\n{tracks_list}\n\n"
        f"Return ONLY a JSON: {{\"pick\": <number>}}"
    )

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
        return None

    try:
        idx = int(json.loads(raw)["pick"]) - 1
        if 0 <= idx < len(tracks):
            return tracks[idx]
    except (json.JSONDecodeError, KeyError, ValueError, IndexError):
        pass
    return None


@dataclass
class MusicOptions:
    local: List[str]           # filenames in music/ folder
    youtube: List[MusicOption]  # YouTube search results
    ai_local: Optional[str]    # AI-suggested local filename (or None)
    genre: str                 # query used


def get_music_options(
    category: str,
    title: str,
    genre: Optional[str] = None,
) -> MusicOptions:
    """Fetch local tracks + YouTube results without any blocking I/O."""
    local_tracks = _get_local_tracks()
    ai_choice = None
    if local_tracks and not genre:
        ai_choice = _ai_pick_local(local_tracks, category, title)

    if genre:
        query = f"{genre} no copyright music free to use"
    else:
        query = _suggest_search_query(category, title)

    yt_options = _search_youtube(query, safe_only=True)
    if not yt_options:
        yt_options = _search_youtube(query, safe_only=False)

    return MusicOptions(
        local=local_tracks,
        youtube=yt_options,
        ai_local=ai_choice,
        genre=genre or query,
    )


def resolve_music_choice(
    choice_key: str,
    options: MusicOptions,
    output_dir: str,
) -> Optional[str]:
    """Resolve a user selection key to a local file path, downloading if needed.

    choice_key values:
      "skip"          — no music
      "local:<name>"  — a filename from options.local
      "yt:<idx>"      — 0-based index into options.youtube (will download)
    """
    if not choice_key or choice_key == "skip":
        return None

    if choice_key.startswith("local:"):
        name = choice_key[len("local:"):]
        return os.path.join(MUSIC_DIR, name)

    if choice_key.startswith("yt:"):
        try:
            idx = int(choice_key[3:])
            selected = options.youtube[idx]
            safe_name = "".join(c if c.isalnum() or c in "-_ " else "" for c in selected.title)[:50]
            path = _download_audio(selected.url, MUSIC_DIR, f"{safe_name}.mp3")
            return path
        except (ValueError, IndexError):
            return None

    return None


def suggest_and_pick_music(
    category: str,
    title: str,
    output_dir: str,
    genre: Optional[str] = None,
) -> Optional[str]:
    """Full flow: check local tracks first, otherwise search YouTube."""

    # Check local music/ folder first
    local_tracks = _get_local_tracks()
    if local_tracks and not genre:
        print(f"\n-> Found {len(local_tracks)} track(s) in music/ folder.")
        ai_choice = _ai_pick_local(local_tracks, category, title)

        print("\n" + "=" * 60)
        print("LOCAL MUSIC")
        print("=" * 60)
        for i, track in enumerate(local_tracks, start=1):
            marker = " <-- AI suggests" if track == ai_choice else ""
            print(f"  [{i}] {track}{marker}")
        print(f"  [0] Search YouTube instead")
        print("=" * 60)
        print("Pick a track (Enter = AI's pick, 0 = search online):")
        choice = input("> ").strip()

        if choice == "" and ai_choice:
            print(f"   Using: {ai_choice}")
            return os.path.join(MUSIC_DIR, ai_choice)
        if choice != "0":
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(local_tracks):
                    print(f"   Using: {local_tracks[idx]}")
                    return os.path.join(MUSIC_DIR, local_tracks[idx])
            except (ValueError, IndexError):
                pass

    # Search YouTube for royalty-free music (safe channels only)
    if genre:
        query = f"{genre} no copyright music free to use"
        print(f"\n-> Searching YouTube for genre: {genre} (safe channels only)")
    else:
        print(f"\n-> AI is suggesting music for: {title} ({category})...")
        query = _suggest_search_query(category, title)
    print(f"   Searching YouTube: \"{query}\"")

    options = _search_youtube(query, safe_only=True)
    if not options:
        print("   No results from safe channels. Trying broader search...")
        options = _search_youtube(query, safe_only=False)
        if not options:
            print("   No results found. Skipping music.")
            return None
        print("   WARNING: These results are NOT verified copyright-safe!")

    print("\n" + "=" * 60)
    print("MUSIC FROM YOUTUBE (copyright-safe channels only)")
    print("=" * 60)
    for i, opt in enumerate(options, start=1):
        print(f"  [{i}] {opt.title} ({opt.duration})")
        if opt.channel:
            print(f"      channel: {opt.channel}")
    print("  [0] Skip — no music")
    print("=" * 60)
    print("Pick a track to download:")
    choice = input("> ").strip()

    if choice == "0" or choice == "":
        return None

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(options):
            selected = options[idx]
            print(f"   Downloading: {selected.title}...")
            safe_name = "".join(c if c.isalnum() or c in "-_ " else "" for c in selected.title)[:50]
            path = _download_audio(selected.url, MUSIC_DIR, f"{safe_name}.mp3")
            if path:
                print(f"   Saved to: {path}")
                return path
            else:
                print("   Download failed. Skipping music.")
                return None
    except (ValueError, IndexError):
        pass

    print("   Invalid selection. Skipping music.")
    return None
