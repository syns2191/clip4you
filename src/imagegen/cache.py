"""Image cache helpers — keying, lookup, and storage."""
import hashlib
import os
import shutil

CACHE_IMG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", ".cache", "images")


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _get_cached_image(key: str) -> str | None:
    for ext in (".png", ".jpg", ".webp"):
        path = os.path.join(CACHE_IMG_DIR, key + ext)
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            return path
    return None


def _cache_image(key: str, source_path: str) -> None:
    os.makedirs(CACHE_IMG_DIR, exist_ok=True)
    _, ext = os.path.splitext(source_path)
    shutil.copy2(source_path, os.path.join(CACHE_IMG_DIR, key + (ext or ".png")))
