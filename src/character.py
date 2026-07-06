"""Character creation, management, and reference-image-based consistency."""

import base64
import json
import os
import shutil
from dataclasses import dataclass, field, asdict
from typing import Optional

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
_STORE_FILE = os.path.join(_ROOT, "characters.json")
CHAR_IMG_DIR = os.path.join(_ROOT, ".cache", "characters")


@dataclass
class Character:
    name: str
    description: str
    art_style: str = "cinematic"
    portrait_path: str = ""
    extra: dict = field(default_factory=dict)


class CharacterLibrary:
    def __init__(self):
        self._chars: list[Character] = []
        self._load()

    def _load(self):
        if not os.path.exists(_STORE_FILE):
            return
        try:
            with open(_STORE_FILE) as f:
                raw = json.load(f)
            self._chars = [Character(**c) for c in raw]
        except Exception as e:
            print(f"[characters] Warning: failed to load {_STORE_FILE}: {e}")
            self._chars = []

    def _save(self):
        tmp = _STORE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump([asdict(c) for c in self._chars], f, indent=2)
        os.replace(tmp, _STORE_FILE)

    def all(self) -> list[Character]:
        return list(self._chars)

    def names(self) -> list[str]:
        return [c.name for c in self._chars]

    def get(self, name: str) -> Optional[Character]:
        return next((c for c in self._chars if c.name == name), None)

    def upsert(self, char: Character):
        for i, c in enumerate(self._chars):
            if c.name == char.name:
                self._chars[i] = char
                self._save()
                return
        self._chars.append(char)
        self._save()

    def remove(self, name: str):
        self._chars = [c for c in self._chars if c.name != name]
        self._save()


_library: Optional[CharacterLibrary] = None


def get_library() -> CharacterLibrary:
    global _library
    if _library is None:
        _library = CharacterLibrary()
    return _library


def generate_character_portrait(
    name: str,
    description: str,
    art_style: str = "cinematic",
    provider: str = "openai",
    reference_image_path: str = "",
) -> str:
    """Generate a portrait for a character. Returns path to saved portrait image."""
    from .imagegen import (
        ART_STYLES, generate_openai,
        generate_stable_diffusion_with_reference,
    )

    os.makedirs(CHAR_IMG_DIR, exist_ok=True)

    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    output_path = os.path.join(CHAR_IMG_DIR, f"{safe_name}.png")

    style = ART_STYLES.get(art_style, ART_STYLES["cinematic"])
    neg = style["negative"] + ", text, watermark, nsfw"

    portrait_prompt = (
        f"Character portrait of {description}, "
        f"full face visible, expressive eyes, detailed features, "
        f"consistent character design, {style['prompt']}, "
        f"masterpiece, best quality, highly detailed"
    )

    if provider == "openai":
        success = generate_openai(portrait_prompt, output_path, size="1024x1024")
    elif provider == "sd":
        sd_over = style.get("sd_override")
        success = generate_stable_diffusion_with_reference(
            portrait_prompt,
            output_path,
            width=512,
            height=512,
            negative_prompt=neg,
            sd_override=sd_over,
            reference_image_path=reference_image_path,
        )
    else:
        success = False

    if success:
        lib = get_library()
        char = lib.get(name) or Character(name=name, description=description)
        char.description = description
        char.art_style = art_style
        char.portrait_path = output_path
        lib.upsert(char)
        return output_path

    return ""


def get_reference_image_b64(character_name: str) -> str:
    """Return base64-encoded portrait for the named character, or empty string."""
    lib = get_library()
    char = lib.get(character_name)
    if not char or not char.portrait_path or not os.path.exists(char.portrait_path):
        return ""
    with open(char.portrait_path, "rb") as f:
        return base64.b64encode(f.read()).decode()
