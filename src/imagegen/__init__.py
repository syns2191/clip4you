"""AI image/video generation for story scenes.
Supports OpenAI, Stable Diffusion, and Google Veo."""
from .presets import ART_STYLES, CATEGORY_STYLES, ILLUSTRATION_STYLE_PROMPT
from .cache import CACHE_IMG_DIR, _cache_key, _get_cached_image, _cache_image
from .openai import generate_openai
from .stablediffusion import generate_stable_diffusion, generate_stable_diffusion_with_reference
from .veo import generate_veo, generate_scene_video
from .generator import generate_scene_image, get_variant_paths

__all__ = [
    "ART_STYLES",
    "CATEGORY_STYLES",
    "ILLUSTRATION_STYLE_PROMPT",
    "CACHE_IMG_DIR",
    "_cache_key",
    "_get_cached_image",
    "_cache_image",
    "generate_openai",
    "generate_stable_diffusion",
    "generate_stable_diffusion_with_reference",
    "generate_veo",
    "generate_scene_video",
    "generate_scene_image",
    "get_variant_paths",
]
