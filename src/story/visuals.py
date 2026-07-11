"""Visual asset downloading helpers (Pexels, YouTube)."""
import json
import os
import shutil
import subprocess
import sys
import urllib.request

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")

# Resolve yt-dlp path (may be in venv)
YT_DLP = shutil.which("yt-dlp") or os.path.join(os.path.dirname(sys.executable), "yt-dlp")


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
