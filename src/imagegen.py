"""AI image generation for story scenes. Supports OpenAI and Stable Diffusion.
Results are cached to prevent duplicate API requests."""
import hashlib
import json
import os
import shutil
import urllib.request
from typing import Optional

from .cache import cache_get, cache_set
from .config import settings

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
SD_API_URL = os.getenv("SD_API_URL", "http://127.0.0.1:7860")
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")

CACHE_IMG_DIR = os.path.join(os.path.dirname(__file__), "..", ".cache", "images")

ILLUSTRATION_STYLE_PROMPT = (
    "Digital illustration, cinematic lighting, highly detailed, "
    "vibrant colors, dramatic atmosphere, 9:16 portrait aspect ratio, "
    "storytelling scene, no text, no watermark"
)


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _get_cached_image(key: str) -> Optional[str]:
    """Check if a generated image is cached. Returns path if found."""
    for ext in (".png", ".jpg", ".webp"):
        path = os.path.join(CACHE_IMG_DIR, key + ext)
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            return path
    return None


def _cache_image(key: str, source_path: str) -> None:
    """Copy a generated image into the cache."""
    os.makedirs(CACHE_IMG_DIR, exist_ok=True)
    _, ext = os.path.splitext(source_path)
    if not ext:
        ext = ".png"
    dest = os.path.join(CACHE_IMG_DIR, key + ext)
    shutil.copy2(source_path, dest)


def _enhance_prompt_with_llm(scene_text: str, search_query: str) -> str:
    """Use LLM to generate a detailed image generation prompt from the scene."""
    cache_input = f"imgprompt:{scene_text}:{search_query}"
    cached = cache_get("imagegen", _cache_key(cache_input))
    if cached is not None:
        print(f"      [Prompt cached]")
        return cached

    prompt = (
        f"You are an expert at writing prompts for AI image generators (DALL-E, Stable Diffusion).\n\n"
        f"Given this narration line from a short video, write a detailed image prompt that captures "
        f"the mood and visual essence of the scene. The image will be used as a background visual.\n\n"
        f"Narration: \"{scene_text}\"\n"
        f"Visual hint: \"{search_query}\"\n\n"
        f"Rules:\n"
        f"- Describe a single, visually striking scene\n"
        f"- Include art style (digital painting, cinematic, etc), lighting, mood, colors\n"
        f"- Portrait orientation (taller than wide)\n"
        f"- No text or words in the image\n"
        f"- Keep it under 200 words\n\n"
        f"Return ONLY the image prompt, nothing else."
    )

    if settings.llm_provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        result = "".join(b.text for b in response.content if b.type == "text").strip()

    elif settings.llm_provider == "groq":
        from groq import Groq
        client = Groq(api_key=settings.groq_api_key)
        response = client.chat.completions.create(
            model=settings.groq_model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        result = response.choices[0].message.content.strip()

    else:
        result = f"{search_query}, {ILLUSTRATION_STYLE_PROMPT}"

    cache_set("imagegen", _cache_key(cache_input), result)
    return result


def generate_openai(prompt: str, output_path: str, size: str = "1024x1536") -> bool:
    """Generate an image using OpenAI (gpt-image-1, dall-e-3, etc)."""
    if not OPENAI_API_KEY:
        print("      [OPENAI_API_KEY not set, skipping]")
        return False

    try:
        import base64
        import openai
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        print(f"      Using model: {OPENAI_IMAGE_MODEL}")

        response = client.images.generate(
            model=OPENAI_IMAGE_MODEL,
            prompt=prompt,
            size=size,
            quality="auto",
            n=1,
        )

        img = response.data[0]

        if hasattr(img, "b64_json") and img.b64_json:
            img_data = base64.b64decode(img.b64_json)
            with open(output_path, "wb") as f:
                f.write(img_data)
        elif hasattr(img, "url") and img.url:
            urllib.request.urlretrieve(img.url, output_path)
        else:
            print("      [No image data in response]")
            return False

        return os.path.exists(output_path) and os.path.getsize(output_path) > 1000
    except Exception as e:
        print(f"      [OpenAI image error: {e}]")
        return False


def generate_stable_diffusion(prompt: str, output_path: str, width: int = 768, height: int = 1344) -> bool:
    """Generate an image using Stable Diffusion (local API — automatic1111/ComfyUI/Forge)."""
    import base64

    payload = {
        "prompt": prompt,
        "negative_prompt": "text, watermark, logo, blurry, low quality, deformed, ugly, nsfw",
        "width": width,
        "height": height,
        "steps": 30,
        "cfg_scale": 7,
        "sampler_name": "DPM++ 2M Karras",
        "batch_size": 1,
    }

    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{SD_API_URL}/sdapi/v1/txt2img",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())

        images = result.get("images", [])
        if not images:
            return False

        img_data = base64.b64decode(images[0])
        with open(output_path, "wb") as f:
            f.write(img_data)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 1000
    except Exception as e:
        print(f"      [Stable Diffusion error: {e}]")
        return False


def generate_scene_image(
    scene_text: str,
    search_query: str,
    output_path: str,
    provider: str = "openai",
) -> bool:
    """Generate an AI illustration for a scene. Uses cache to avoid duplicate requests."""
    # Check image cache first
    img_cache_key = _cache_key(f"img:{provider}:{scene_text}:{search_query}")
    cached_path = _get_cached_image(img_cache_key)
    if cached_path:
        print(f"      [Cached image found]")
        shutil.copy2(cached_path, output_path)
        return True

    print(f"      Generating image prompt with AI...")
    image_prompt = _enhance_prompt_with_llm(scene_text, search_query)
    print(f"      Prompt: {image_prompt[:100]}...")

    if provider == "openai":
        print(f"      Generating with OpenAI...")
        success = generate_openai(image_prompt, output_path)
    elif provider == "sd":
        print(f"      Generating with Stable Diffusion...")
        success = generate_stable_diffusion(image_prompt, output_path)
    else:
        print(f"      Unknown provider: {provider}")
        return False

    if success:
        _cache_image(img_cache_key, output_path)

    return success
