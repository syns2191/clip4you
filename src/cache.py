"""
Simple file-based cache for transcription and LLM results.
Avoids re-running expensive API calls when re-processing the same video.
"""
import hashlib
import json
import os
from typing import Optional

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", ".cache")


def _ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def cache_get(namespace: str, key: str) -> Optional[str]:
    path = os.path.join(CACHE_DIR, namespace, _hash_key(key))
    if os.path.exists(path):
        with open(path, "r") as f:
            return f.read()
    return None


def cache_set(namespace: str, key: str, value: str) -> None:
    _ensure_cache_dir()
    ns_dir = os.path.join(CACHE_DIR, namespace)
    os.makedirs(ns_dir, exist_ok=True)
    path = os.path.join(ns_dir, _hash_key(key))
    with open(path, "w") as f:
        f.write(value)
