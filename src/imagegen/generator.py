"""High-level scene image generation — dispatches to the right provider."""
import os
import shutil
from typing import Optional

from .cache import CACHE_IMG_DIR, _cache_key, _get_cached_image, _cache_image
from .presets import ART_STYLES, CATEGORY_STYLES
from .openai import generate_openai
from .stablediffusion import generate_stable_diffusion_with_reference


def generate_scene_image(
    scene_text: str,
    search_query: str,
    output_path: str,
    provider: str = "openai",
    art_style: str = "",
    category: str = "",
    mood: str = "",
    orientation: str = "portrait",
    character_name: str = "",
    use_cache: bool = True,
) -> bool:
    """Generate an AI illustration for a scene. Uses cache to avoid duplicate requests."""
    img_cache_key = _cache_key(f"img:{provider}:{character_name}:{search_query}")
    if use_cache:
        cached = _get_cached_image(img_cache_key)
        if cached:
            print("      [Cached image found]")
            shutil.copy2(cached, output_path)
            return True

    style_key = art_style or (CATEGORY_STYLES[category]["style"] if category in CATEGORY_STYLES else "")
    style = ART_STYLES.get(style_key)
    neg = style["negative"] + ", text, watermark, nsfw" if style else ""

    character_prefix = ""
    if character_name:
        from ..character import get_library
        char = get_library().get(character_name)
        if char:
            character_prefix = f"Character: {char.description}. "
            print(f"      Using character description for consistency: {character_name}")

    image_prompt = character_prefix + search_query if character_prefix else search_query

    if provider == "openai":
        print(f"      Generating with OpenAI... {image_prompt}")
        success = generate_openai(image_prompt, output_path)
    elif provider == "sd":
        print("      Generating with Stable Diffusion...")
        success = generate_stable_diffusion_with_reference(
            image_prompt, output_path,
            negative_prompt=neg,
            sd_override=style.get("sd_override") if style else None,
        )
    else:
        print(f"      Unknown provider: {provider}")
        return False

    if success:
        _cache_image(img_cache_key, output_path)
    return success


def get_variant_paths(output_path: str) -> list:
    """Return all variant paths (_v1, _v2, …) for a generated image."""
    base, ext = os.path.splitext(output_path)
    ext = ext or ".png"
    variants = []
    for i in range(1, 20):
        p = f"{base}_v{i}{ext}"
        if os.path.exists(p) and os.path.getsize(p) > 1000:
            variants.append(p)
        else:
            break
    return variants or ([output_path] if os.path.exists(output_path) else [])
