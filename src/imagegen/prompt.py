"""LLM-assisted prompt enhancement for image and video generation."""
from typing import Optional

from ..cache import cache_get, cache_set
from ..config import settings
from .cache import _cache_key
from .presets import ART_STYLES, CATEGORY_STYLES


def _enhance_prompt_with_llm(
    scene_text: str,
    search_query: str,
    art_style: str = "",
    category: str = "",
    mood: str = "",
    orientation: str = "portrait",
) -> str:
    """Use the LLM to generate a detailed image prompt grounded in the narration text."""
    style_key = art_style or (CATEGORY_STYLES[category]["style"] if category in CATEGORY_STYLES else "")
    style = ART_STYLES.get(style_key, ART_STYLES.get("cinematic"))

    cache_input = f"imgprompt:{style_key}:{category}:{mood}:{orientation}:{scene_text}:{search_query}"
    cached = cache_get("imagegen", _cache_key(cache_input))
    if cached is not None:
        print("      [Prompt cached]")
        return cached

    mood_hint = ""
    if mood:
        mood_hint = f"Scene mood: {mood}\n"
    elif category in CATEGORY_STYLES:
        mood_hint = f"Scene mood/atmosphere: {CATEGORY_STYLES[category]['mood']}\n"

    orientation_hint = {
        "portrait":  "Portrait orientation (taller than wide, vertical format)",
        "landscape": "Landscape orientation (wider than tall, horizontal format)",
        "square":    "Square format (equal width and height)",
    }.get(orientation, "Portrait orientation (taller than wide)")

    llm_prompt = (
        f"You are an expert at writing prompts for AI image generators (Stable Diffusion, DALL-E).\n\n"
        f"Your task: create a vivid image prompt that visually illustrates exactly what the narrator is saying.\n\n"
        f"Narration (PRIMARY source — illustrate this literally): \"{scene_text}\"\n"
        f"Supporting visual hint (secondary, use only if narration is too abstract): \"{search_query}\"\n"
        f"Art style: {style['name']}\n"
        f"Style tags to include: {style['prompt']}\n"
        f"{mood_hint}"
        f"\nRules:\n"
        f"- The image must depict what the narration describes — a viewer should feel they are seeing the words\n"
        f"- Describe in this order: (1) subject & pose — exact body position, stance, hand placement, angle; "
        f"(2) facial expression — eyes, brow, mouth, emotion conveyed; "
        f"(3) action & scene elements — what objects, environment, props are present and their spatial relationship; "
        f"(4) lighting & atmosphere; (5) style tags\n"
        f"- Be specific about pose: e.g. 'leaning forward with both hands on desk, head tilted slightly down' not just 'standing'\n"
        f"- Be specific about expression: e.g. 'furrowed brows, tight lips, downcast eyes showing worry' not just 'sad'\n"
        f"- The style tags MUST appear in your prompt\n"
        f"- {orientation_hint}\n"
        f"- No text, words, letters, or watermarks\n"
        f"- For Stable Diffusion: most important terms first, comma-separated\n"
        f"- End with: masterpiece, best quality, highly detailed\n"
        f"- Keep it under 150 words\n\n"
        f"Return ONLY the image prompt, nothing else."
    )

    if settings.llm_provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=300,
            messages=[{"role": "user", "content": llm_prompt}],
        )
        result = "".join(b.text for b in response.content if b.type == "text").strip()
    elif settings.llm_provider == "groq":
        from groq import Groq
        client = Groq(api_key=settings.groq_api_key)
        response = client.chat.completions.create(
            model=settings.groq_model,
            max_tokens=300,
            messages=[{"role": "user", "content": llm_prompt}],
        )
        result = response.choices[0].message.content.strip()
    else:
        result = f"{search_query}, {style['prompt']}, masterpiece, best quality, highly detailed"

    cache_set("imagegen", _cache_key(cache_input), result)
    return result


def _build_veo_prompt(scene_text: str, search_query: str, art_style: str = "", category: str = "") -> str:
    """Build a video generation prompt for Veo."""
    style_key = art_style or (CATEGORY_STYLES[category]["style"] if category in CATEGORY_STYLES else "")
    style = ART_STYLES.get(style_key)
    mood_hint = f", {CATEGORY_STYLES[category]['mood']} atmosphere" if category in CATEGORY_STYLES else ""
    style_desc = f", {style['name']} style, {style['prompt']}" if style else ""
    return f"{scene_text}. Visual: {search_query}{style_desc}{mood_hint}, smooth camera movement, cinematic"
