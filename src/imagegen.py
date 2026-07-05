"""AI image/video generation for story scenes.
Supports OpenAI, Stable Diffusion, and Google Veo (AI video).
Results are cached to prevent duplicate API requests."""
import hashlib
import json
import os
import shutil
import time
import urllib.request
from typing import Optional

from .cache import cache_get, cache_set
from .config import settings

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
SD_API_URL = os.getenv("SD_API_URL", "http://127.0.0.1:7860")
SD_MODEL = os.getenv("SD_MODEL", "")
SD_WIDTH = int(os.getenv("SD_WIDTH", "512"))
SD_HEIGHT = int(os.getenv("SD_HEIGHT", "768"))
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1-mini")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
VEO_MODEL = os.getenv("VEO_MODEL", "veo-3.1-lite-generate-preview")

CACHE_IMG_DIR = os.path.join(os.path.dirname(__file__), "..", ".cache", "images")

ART_STYLES = {
    "pen": {
        "name": "Pen & Ink Drawing",
        "prompt": "black ink pen drawing on white paper, hand-drawn illustration, fine line art, crosshatching, sketch style, detailed pen strokes, artistic ink illustration, white background",
        "negative": "color, painting, photograph, digital art, 3d render, blurry",
    },
    "pencil": {
        "name": "Pencil Sketch",
        "prompt": "detailed pencil sketch on textured paper, graphite drawing, realistic shading, hand-drawn, artistic pencil illustration, soft shadows",
        "negative": "color, painting, photograph, digital art, 3d render",
    },
    "watercolor": {
        "name": "Watercolor Painting",
        "prompt": "beautiful watercolor painting, soft washes, flowing colors, wet-on-wet technique, artistic watercolor illustration, paper texture, delicate brushstrokes",
        "negative": "photograph, 3d render, digital art, sharp lines",
    },
    "anime": {
        "name": "Anime Style",
        "prompt": "anime illustration, Studio Ghibli style, beautiful anime art, detailed anime drawing, soft lighting, vibrant anime colors, high quality anime",
        "negative": "photograph, realistic, 3d render, western cartoon",
    },
    "ghibli": {
        "name": "Studio Ghibli",
        "prompt": "Pencil Sketch Drawing, (Studio ghibli style, Art by Hayao Miyazaki:1.2), Anime Style, Manga Style, Hand drawn, cinematic, Sharp focus, humorous illustration, big depth of field, Masterpiece, concept art, trending on artstation, Vivid colors, Simplified style, trending on ArtStation, trending on CGSociety, Intricate, Vibrant colors, Soft Shading, Simplistic Features, Sharp Angles, Playful, black and white drawing, graphite drawing",
        "negative": "ugly, deformed, noisy, blurry, low contrast",
    },
    "cinematic": {
        "name": "Cinematic Digital Art",
        "prompt": "cinematic digital painting, dramatic lighting, highly detailed, vibrant colors, epic atmosphere, concept art, artstation trending, masterpiece",
        "negative": "blurry, low quality, deformed, ugly, sketch",
    },
    "oil": {
        "name": "Oil Painting",
        "prompt": "classical oil painting, rich colors, visible brushstrokes, museum quality, traditional art, canvas texture, Renaissance style lighting",
        "negative": "photograph, digital art, 3d render, cartoon, anime",
    },
    "comic": {
        "name": "Comic Book Style",
        "prompt": "comic book illustration, bold outlines, cel shading, dynamic composition, graphic novel art, vibrant comic colors, pop art",
        "negative": "photograph, realistic, 3d render, blurry",
    },
    "minimal": {
        "name": "Minimalist Art",
        "prompt": "minimalist illustration, clean lines, simple shapes, flat design, modern art, limited color palette, elegant simplicity, negative space",
        "negative": "complex, busy, realistic, photograph, detailed",
    },
    "pixel": {
        "name": "Pixel Art",
        "prompt": "pixel art illustration, retro game style, 16-bit aesthetic, pixelated, nostalgic, clean pixel work, vibrant pixel colors",
        "negative": "realistic, photograph, smooth, 3d render",
    },
    "charcoal": {
        "name": "Charcoal Drawing",
        "prompt": "charcoal drawing on paper, dramatic shadows, smudged edges, expressive strokes, artistic charcoal illustration, high contrast, moody atmosphere",
        "negative": "color, painting, photograph, digital art, clean lines",
    },
    "storybook": {
        "name": "Children's Storybook",
        "prompt": "children's book illustration, whimsical art style, soft pastel colors, warm and inviting, storybook aesthetic, gentle lighting, fairy tale atmosphere",
        "negative": "scary, dark, realistic, photograph, 3d render",
    },
    "realistic": {
        "name": "Photorealistic",
        "prompt": "photorealistic, ultra detailed, professional photography, sharp focus, natural lighting, 8k resolution, stunning composition",
        "negative": "cartoon, anime, painting, drawing, sketch, abstract",
    },
    "stickfigure": {
        "name": "Expressive Character Study",
        "prompt": "character study sheet, fleshed-out minimalist character, wearing a hoodie and sneakers, multiple highly expressive faces, grid of exaggerated facial expressions (happy, sad, angry, surprised), dynamic body language, clean bold black outlines on white background, modern webcomic style illustration, flat black and white line art, stylized human shape, clear and distinct strokes",
        "negative": "neutral expression, blank face, emotionless, thin lines, single continuous line drawing, stick thin, crude hand-drawn doodle, realistic anatomy, detailed, photograph, complex, shading, 3d render, color, painting, messy, scratchy"
    },
    "stickfigure": {
        "name": "Stick Figure",
        "prompt": "expressive stick figure character, {action} pose, {emotion} facial expression, interacting with {object}, bold confident black ink lines on clean white background, hand-drawn marker style, varied line weight thicker at joints and torso thinner at limb ends, circular head with clear eyes eyebrows and mouth showing emotion, dynamic full-body gesture and motion lines, well-proportioned limbs roughly 1:1 head-to-body ratio typical of gesture-doodle stick figures, clear joint dots at shoulders elbows hips and knees, object rendered in same simple line style and correct scale relative to figure, whiteboard illustration style, clean line work, storytelling illustration, single continuous scene",
        "negative": "realistic, detailed anatomy, photograph, complex shading, 3d render, full color, painting, messy scribble, single continuous one-line drawing, blurry, low quality, distorted proportions, extra limbs, floating disconnected object, mismatched scale, stiff T-pose, blank expressionless face",
    },
    "sketch": {
        "name": "Pencil Sketch Drawing",
        "prompt": "Pencil Sketch Drawing, <lora:animeoutlineV4_16:1>, black and white drawing, graphite drawing",
        "negative": "ugly, deformed, noisy, blurry, low contrast",
        "sd_override": {
            "steps": 8,
            "sampler_name": "DPM++ 2M",
            "scheduler": "Karras",
            "cfg_scale": 1.5,
        },
    },
}

CATEGORY_STYLES = {
    "meditation": {"style": "watercolor", "mood": "serene peaceful calm spiritual"},
    "horror": {"style": "charcoal", "mood": "dark ominous terrifying shadowy"},
    "fantasy": {"style": "cinematic", "mood": "magical ethereal epic mystical"},
    "romance": {"style": "watercolor", "mood": "warm intimate tender loving"},
    "motivational": {"style": "cinematic", "mood": "powerful inspiring triumphant golden"},
    "history": {"style": "oil", "mood": "ancient grand historical dramatic"},
    "scifi": {"style": "cinematic", "mood": "futuristic neon technological cosmic"},
    "nature": {"style": "watercolor", "mood": "natural organic peaceful lush"},
    "adventure": {"style": "cinematic", "mood": "epic vast adventurous dramatic"},
    "comedy": {"style": "comic", "mood": "funny playful bright cheerful"},
    "mystery": {"style": "charcoal", "mood": "mysterious dark foggy enigmatic"},
    "documentary": {"style": "realistic", "mood": "authentic real journalistic raw"},
    "fairytale": {"style": "storybook", "mood": "whimsical magical enchanted dreamy"},
    "gaming": {"style": "pixel", "mood": "retro nostalgic digital vibrant"},
    "zen": {"style": "pen", "mood": "minimal peaceful balanced harmonious"},
    "anime": {"style": "anime", "mood": "dynamic expressive vibrant emotional"},
}

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


def _enhance_prompt_with_llm(scene_text: str, search_query: str, art_style: str = "", category: str = "") -> str:
    """Use LLM to generate a detailed image generation prompt from the scene."""
    # Resolve style from category if not explicitly set
    style_key = art_style
    if not style_key and category and category in CATEGORY_STYLES:
        style_key = CATEGORY_STYLES[category]["style"]
    style = ART_STYLES.get(style_key, ART_STYLES.get("cinematic"))

    cache_input = f"imgprompt:{style_key}:{category}:{scene_text}:{search_query}"
    cached = cache_get("imagegen", _cache_key(cache_input))
    if cached is not None:
        print(f"      [Prompt cached]")
        return cached

    mood_hint = ""
    if category and category in CATEGORY_STYLES:
        mood_hint = f"\nMood/atmosphere: {CATEGORY_STYLES[category]['mood']}"

    prompt = (
        f"You are an expert at writing prompts for AI image generators (Stable Diffusion, DALL-E).\n\n"
        f"Given this narration line from a short video, write a detailed image prompt.\n\n"
        f"Narration: \"{scene_text}\"\n"
        f"Visual hint: \"{search_query}\"\n"
        f"Art style: {style['name']}\n"
        f"Style tags to include: {style['prompt']}\n"
        f"{mood_hint}\n\n"
        f"Rules:\n"
        f"- Describe the SCENE CONTENT first (what is depicted), then the art style\n"
        f"- The style tags MUST appear in your prompt — they define the look\n"
        f"- Describe specific visual elements: subjects, composition, lighting, atmosphere\n"
        f"- Portrait orientation (taller than wide)\n"
        f"- No text, words, letters, or watermarks in the image\n"
        f"- For Stable Diffusion: put the most important terms first, use commas to separate concepts\n"
        f"- End with quality tags: masterpiece, best quality, highly detailed\n"
        f"- Keep it under 150 words\n\n"
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
        result = f"{search_query}, {style['prompt']}, masterpiece, best quality, highly detailed"

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
            quality="low",
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


def _ensure_sd_model() -> None:
    """Switch SD model if SD_MODEL env var is set and differs from current."""
    if not SD_MODEL:
        return
    try:
        req = urllib.request.Request(f"{SD_API_URL}/sdapi/v1/options")
        with urllib.request.urlopen(req, timeout=10) as resp:
            options = json.loads(resp.read().decode())
        current = options.get("sd_model_checkpoint", "")
        if SD_MODEL not in current:
            print(f"      Switching SD model to {SD_MODEL}...")
            data = json.dumps({"sd_model_checkpoint": SD_MODEL}).encode()
            req = urllib.request.Request(
                f"{SD_API_URL}/sdapi/v1/options",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=120)
    except Exception:
        pass


def generate_stable_diffusion(prompt: str, output_path: str, width: int = SD_WIDTH, height: int = SD_HEIGHT, negative_prompt: str = "", sd_override: Optional[dict] = None) -> bool:
    """Generate an image using Stable Diffusion (local API — automatic1111/ComfyUI/Forge)."""
    import base64

    _ensure_sd_model()

    if not negative_prompt:
        negative_prompt = "text, watermark, logo, blurry, low quality, deformed, ugly, nsfw"

    payload = {
        "prompt": f"{prompt}<lora:ip-adapter-faceid-plusv2_sd15_lora:1>",
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "steps": 8,
        "cfg_scale": 1.5,
        "sampler_name": "DPM++ 2M",
        "scheduler": "Karras",
        "batch_size": 2,
    }

    if sd_override:
        payload.update(sd_override)

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

        base, ext = os.path.splitext(output_path)
        if not ext:
            ext = ".png"
        all_paths = []
        for i, img_b64 in enumerate(images):
            img_data = base64.b64decode(img_b64)
            p = f"{base}_v{i+1}{ext}" if len(images) > 1 else output_path
            with open(p, "wb") as f:
                f.write(img_data)
            if os.path.getsize(p) > 1000:
                all_paths.append(p)

        if not all_paths:
            return False

        shutil.copy2(all_paths[0], output_path)
        return True
    except Exception as e:
        print(f"      [Stable Diffusion error: {e}]")
        return False


def generate_veo(prompt: str, output_path: str, duration_seconds: int = 8, aspect_ratio: str = "9:16") -> bool:
    """Generate a video using Google Veo (Gemini video generation API)."""
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

        video_config = types.GenerateVideosConfig(
            person_generation="allow_all",
            aspect_ratio=aspect_ratio,
            number_of_videos=1,
            duration_seconds=min(8, max(5, duration_seconds)),
            resolution="720p",
        )

        operation = client.models.generate_videos(
            model=VEO_MODEL,
            source=types.GenerateVideosSource(prompt=prompt),
            config=video_config,
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


def _build_veo_prompt(scene_text: str, search_query: str, art_style: str = "", category: str = "") -> str:
    """Build a video generation prompt for Veo, incorporating art style."""
    style_key = art_style
    if not style_key and category and category in CATEGORY_STYLES:
        style_key = CATEGORY_STYLES[category]["style"]
    style = ART_STYLES.get(style_key)

    mood_hint = ""
    if category and category in CATEGORY_STYLES:
        mood_hint = f", {CATEGORY_STYLES[category]['mood']} atmosphere"

    style_desc = ""
    if style:
        style_desc = f", {style['name']} style, {style['prompt']}"

    return f"{scene_text}. Visual: {search_query}{style_desc}{mood_hint}, smooth camera movement, cinematic"


def generate_scene_video(
    scene_text: str,
    search_query: str,
    output_path: str,
    duration: float = 8.0,
    art_style: str = "",
    category: str = "",
) -> bool:
    """Generate a video for a scene using Veo. Uses cache to avoid duplicate requests."""
    cache_input = f"veo:{art_style}:{category}:{scene_text}:{search_query}"
    vid_cache_key = _cache_key(cache_input)
    cached_path = os.path.join(CACHE_IMG_DIR, vid_cache_key + ".mp4")
    if os.path.exists(cached_path) and os.path.getsize(cached_path) > 5000:
        print(f"      [Cached video found]")
        shutil.copy2(cached_path, output_path)
        return True

    prompt = _build_veo_prompt(scene_text, search_query, art_style=art_style, category=category)
    print(f"      Veo prompt: {prompt[:120]}...")

    success = generate_veo(prompt, output_path, duration_seconds=min(8, int(duration)))

    if success:
        os.makedirs(CACHE_IMG_DIR, exist_ok=True)
        shutil.copy2(output_path, cached_path)

    return success


def generate_scene_image(
    scene_text: str,
    search_query: str,
    output_path: str,
    provider: str = "openai",
    art_style: str = "",
    category: str = "",
) -> bool:
    """Generate an AI illustration for a scene. Uses cache to avoid duplicate requests."""
    img_cache_key = _cache_key(f"img:{provider}:{art_style}:{category}:{scene_text}:{search_query}")
    cached_path = _get_cached_image(img_cache_key)
    if cached_path:
        print(f"      [Cached image found]")
        shutil.copy2(cached_path, output_path)
        return True

    # Resolve style
    style_key = art_style
    if not style_key and category and category in CATEGORY_STYLES:
        style_key = CATEGORY_STYLES[category]["style"]
    style = ART_STYLES.get(style_key)
    neg = style["negative"] + ", text, watermark, nsfw" if style else ""

    # Check if search_query is already a detailed SD prompt (from scriptgen)
    is_detailed = ":1." in search_query or (len(search_query) > 80 and search_query.count(",") > 3)

    if is_detailed:
        image_prompt = search_query
        if style and style["prompt"] not in image_prompt:
            image_prompt += f", {style['prompt']}"
        print(f"      Using script visual directly")
        print(f"      Prompt: {image_prompt[:120]}...")
    else:
        print(f"      Generating image prompt with AI...")
        image_prompt = _enhance_prompt_with_llm(scene_text, search_query, art_style=art_style, category=category)
        print(f"      Prompt: {image_prompt[:120]}...")

    if provider == "openai":
        print(f"      Generating with OpenAI...")
        success = generate_openai(image_prompt, output_path)
    elif provider == "sd":
        print(f"      Generating with Stable Diffusion...")
        sd_over = style.get("sd_override") if style else None
        success = generate_stable_diffusion(image_prompt, output_path, negative_prompt=neg, sd_override=sd_over)
    else:
        print(f"      Unknown provider: {provider}")
        return False

    if success:
        _cache_image(img_cache_key, output_path)

    return success


def get_variant_paths(output_path: str) -> list:
    """Return all variant paths (e.g. _v1.png, _v2.png) for a generated image."""
    base, ext = os.path.splitext(output_path)
    if not ext:
        ext = ".png"
    variants = []
    for i in range(1, 20):
        p = f"{base}_v{i}{ext}"
        if os.path.exists(p) and os.path.getsize(p) > 1000:
            variants.append(p)
        else:
            break
    if not variants and os.path.exists(output_path):
        variants = [output_path]
    return variants
