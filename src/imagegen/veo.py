"""Google Veo video generation."""
import os
import shutil
import time

from .cache import CACHE_IMG_DIR, _cache_key
from .prompt import _build_veo_prompt

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
VEO_MODEL = os.getenv("VEO_MODEL", "veo-3.1-lite-generate-preview")


def generate_veo(prompt: str, output_path: str, duration_seconds: int = 8, aspect_ratio: str = "9:16") -> bool:
    """Generate a video using Google Veo."""
    if not GEMINI_API_KEY:
        print("      [GEMINI_API_KEY not set, skipping]")
        return False

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            http_options={"api_version": "v1beta"},
            api_key=GEMINI_API_KEY,
        )
        operation = client.models.generate_videos(
            model=VEO_MODEL,
            source=types.GenerateVideosSource(prompt=prompt),
            config=types.GenerateVideosConfig(
                person_generation="allow_all",
                aspect_ratio=aspect_ratio,
                number_of_videos=1,
                duration_seconds=min(8, max(5, duration_seconds)),
                resolution="720p",
            ),
        )

        print("      Waiting for Veo to generate video...", end="", flush=True)
        while not operation.done:
            print(".", end="", flush=True)
            time.sleep(10)
            operation = client.operations.get(operation)
        print()

        result = operation.result
        if not result or not result.generated_videos:
            print("      [Veo returned no video]")
            return False

        video = result.generated_videos[0]
        client.files.download(file=video.video)
        video.video.save(output_path)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 5000
    except Exception as e:
        print(f"\n      [Veo error: {e}]")
        return False


def generate_scene_video(
    scene_text: str,
    search_query: str,
    output_path: str,
    duration: float = 8.0,
    art_style: str = "",
    category: str = "",
) -> bool:
    """Generate a video for a scene using Veo, with caching."""
    cached_path = os.path.join(CACHE_IMG_DIR, _cache_key(f"veo:{art_style}:{category}:{scene_text}:{search_query}") + ".mp4")
    if os.path.exists(cached_path) and os.path.getsize(cached_path) > 5000:
        print("      [Cached video found]")
        shutil.copy2(cached_path, output_path)
        return True

    prompt = _build_veo_prompt(scene_text, search_query, art_style=art_style, category=category)
    print(f"      Veo prompt: {prompt[:120]}...")

    success = generate_veo(prompt, output_path, duration_seconds=min(8, int(duration)))
    if success:
        os.makedirs(CACHE_IMG_DIR, exist_ok=True)
        shutil.copy2(output_path, cached_path)
    return success
