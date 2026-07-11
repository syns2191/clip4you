"""Script generation logic — builds the prompt and calls the LLM."""
from typing import Optional

from ..config import settings
from .presets import CATEGORY_GUIDANCE, CHARACTER_PRESETS, BACKGROUND_THEMES, ART_STYLE_TEMPLATES
from .prompt import SCRIPT_PROMPT


def _build_prompt(
    topic: str,
    category: str,
    art_style: str,
    duration: int,
    num_scenes: int,
    tone: str,
    character: str,
    background: str,
    extra_instructions: str,
) -> str:
    cat_guidance = CATEGORY_GUIDANCE.get(category, "")
    if cat_guidance:
        cat_guidance = f"CATEGORY GUIDANCE ({category}):\n{cat_guidance}"

    art_prompt = ART_STYLE_TEMPLATES.get(art_style, ART_STYLE_TEMPLATES["sketch"])
    print(f"   Using art style template: {art_style} → {art_prompt}")

    char_section = ""
    if character and character in CHARACTER_PRESETS:
        cp = CHARACTER_PRESETS[character]
        char_section = (
            f"CHARACTER (use this SAME character in EVERY scene — keep appearance consistent):\n"
            f"  Name: {cp['name']}\n"
            f"  Visual tags: {cp['visual']}\n"
            f"  IMPORTANT: Start every visual description with these exact character tags. "
            f"The character must look the same in every scene."
        )

    bg_section = ""
    if background and background in BACKGROUND_THEMES:
        bt = BACKGROUND_THEMES[background]
        bg_section = (
            f"BACKGROUND THEME (use this environment as the base setting for all scenes):\n"
            f"  Name: {bt['name']}\n"
            f"  Visual tags: {bt['visual']}\n"
            f"  Lighting: {bt['lighting']}\n"
            f"  You can vary the specific location within this theme per scene, "
            f"but keep the overall environment and lighting consistent."
        )

    print(f"character_section {char_section}")
    print(f"background_section {bg_section}")

    return SCRIPT_PROMPT.format(
        topic=topic,
        tone=tone,
        art_style_prompt=art_prompt,
        duration=duration,
        num_scenes=num_scenes,
        category_guidance=cat_guidance,
        character_section=char_section,
        background_section=bg_section,
        extra_instructions=extra_instructions,
    )


def _call_llm(prompt: str) -> str:
    if settings.llm_provider == "groq":
        from groq import Groq
        client = Groq(api_key=settings.groq_api_key)
        response = client.chat.completions.create(
            model=settings.groq_model,
            max_tokens=4000,
            temperature=0.8,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()

    if settings.llm_provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in response.content if b.type == "text").strip()

    raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")


def _clean_script(raw: str) -> str:
    if raw.startswith("```"):
        lines = [l for l in raw.split("\n") if not l.startswith("```")]
        return "\n".join(lines).strip()
    return raw


def generate_script(
    topic: str,
    category: str = "life-lesson",
    art_style: str = "sketch",
    duration: int = 60,
    tone: str = "reflective and powerful",
    character: str = "",
    background: str = "",
    extra_instructions: str = "",
    output_path: Optional[str] = None,
    scene_count: int = 0,
) -> str:
    """Generate a story script using the configured LLM. Returns the script text."""
    num_scenes = scene_count if scene_count > 0 else max(4, duration // 10)

    print("-> Generating script with AI...")
    print(f"   Topic: {topic} | Category: {category} | Style: {art_style} | ~{duration}s ({num_scenes} scenes)")
    if character:
        print(f"   Character: {CHARACTER_PRESETS.get(character, {}).get('name', character)}")
    if background:
        print(f"   Background: {BACKGROUND_THEMES.get(background, {}).get('name', background)}")

    prompt = _build_prompt(topic, category, art_style, duration, num_scenes, tone, character, background, extra_instructions)
    raw = _call_llm(prompt)
    script = _clean_script(raw)

    valid_lines = [l for l in script.split("\n") if "|" in l and l.strip()]
    if len(valid_lines) < 3:
        print(f"   Warning: LLM returned {len(valid_lines)} valid lines, expected {num_scenes}+")
    print(f"   Generated {len(valid_lines)} scenes")

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(script)
        print(f"   Saved to: {output_path}")

    return script
