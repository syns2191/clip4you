"""
AI script generator — uses Groq LLM to generate story scripts
in the timeline format ready for story mode rendering.
"""
import json
import os
from typing import Optional

from .config import settings


SCRIPT_PROMPT = """You are an expert short-form video scriptwriter for YouTube Shorts / TikTok / Reels.

Generate a narrated story script in this EXACT timeline format:

```
TIMESTAMP | NARRATION TEXT | VISUAL DESCRIPTION | image | MOOD | RATE
```

RULES:
1. Each line = one scene (5-12 seconds of narration)
2. Timestamps must be sequential starting from 0:00, spaced by scene duration
3. Narration text = what the voice will say. Write in {tone} tone. Keep sentences short and punchy.
4. Visual description = detailed image generation prompt for Stable Diffusion. Include:
   - Main subject with weight (subject:1.4)
   - Key visual elements with weight (element:1.3)
   - Composition details (full body visible, background)
   - Art style: {art_style_prompt}
5. Use "image" as visual type for all scenes
6. Mood must be one of: cinematic, dramatic, calm, tense, melancholic, hopeful, cheerful, sad, excited, whisper
7. Rate controls speech speed: -10% to -25% (slower = more dramatic)
8. First line should be a silent intro: 0:00| [INTRO] — silence — | ... | image | cinematic | -20%
9. Last line should be a silent outro: TIMESTAMP | — silence — | VISUAL DESCRIPTION | image | cinematic | -25%
   The outro MUST have a full visual description — a powerful closing image that matches the story's resolution.
   NEVER leave the visual description empty on any line.
10. Total duration should be {duration} seconds ({num_scenes} scenes)
11. The script must tell a complete story arc: hook → buildup → climax → resolution
12. Every line must grab attention — no filler, no boring transitions
13. EVERY line must have a visual description — no empty visual fields

VISUAL STORYTELLING (CRITICAL — the images must tell a CONNECTED visual story):
- Think of the visuals as a CAMERA FOLLOWING the character through a journey
- Scene 1→2→3 should flow like a continuous visual narrative, not random independent images
- The character's POSE and ACTION must reflect what the narration says:
  * Struggle/defeat → character kneeling, head bowed, hands in mud, slumped against wall
  * Hope/resolution → character standing tall, chin up, looking at horizon, arms open
  * Reflection/thinking → character sitting still, looking at water/mirror, journal open
  * Loss/sadness → character alone, back turned, empty space beside them, head down
  * Action/determination → character walking forward, climbing, pushing through
- The ENVIRONMENT should evolve with the emotional arc:
  * Stay in the SAME world throughout (e.g. all scenes on a coastline, or all in a forest)
  * Shift the specific spot scene by scene (beach → cliff → rocks → shore → sunset)
  * Dark/enclosed/stormy for tension → open/bright/golden for hope and resolution
  * Lighting shifts: dim shadows early → warm golden light at the end
- VISUAL PROGRESSION:
  * Each scene's image = the NEXT FRAME in a visual journey, not a random photo
  * The character physically MOVES through the environment scene by scene
  * Include ONE KEY OBJECT or SYMBOL that evolves with the story (e.g. crumpled paper → smooth page, broken chain → open hands, extinguished candle → burning flame)
  * NEVER repeat the exact same pose or composition in two scenes
  * Each visual must show ONE clear action or gesture that directly matches the narration text

HOOK (first 3 seconds — viewer decides to stay or swipe):
- Use ONE of these proven hook patterns:
  * CONTRARIAN: "Everyone tells you to [common advice]... they're wrong."
  * MYSTERY: "There's something about [topic] that nobody talks about."
  * CHALLENGE: "You've been doing [thing] wrong your entire life."
  * STORY LOOP: "A [person] once said something that changed everything."
  * SHOCK STAT: "97% of people will never [achieve thing]. Here's why."
  * DIRECT ATTACK: "If you [relatable bad habit], this is for you."
  * PROMISE: "In the next 60 seconds, you'll understand [powerful insight]."
- The first sentence MUST create an open loop — a question the viewer needs answered
- NEVER start with context or background. Start with the punch.

RETENTION (middle — keep the viewer watching):
- Every 8-10 seconds, inject a micro-hook: "But here's the thing...", "And this is where it gets interesting...", "Wait..."
- Use the "1-2 punch": setup an expectation, then subvert it
- Increase emotional intensity scene by scene — never plateau
- Use short, punchy sentences. Max 15 words per sentence.
- Add contrast: pair a dark moment with a light one, silence with action
- Ask rhetorical questions that make the viewer answer in their head

ENDING (last scene — make them share/comment/follow):
- Use ONE of these ending patterns:
  * CALLBACK: Return to the opening hook and answer it with a twist
  * CLIFF: End with an unresolved question: "So ask yourself... what are you waiting for?"
  * EMOTIONAL PEAK: The most powerful line of the entire script. Make it hit.
  * IDENTITY SHIFT: "You are not [old identity]. You are [new identity]."
  * ACTION: End with a specific action the viewer can take right now
- The last sentence should be QUOTABLE — something viewers screenshot or repeat
- Slow the speech rate on the final line (-25% or slower) for maximum impact
- NEVER end with generic advice like "be yourself" or "just do it"

{character_section}

{background_section}

{category_guidance}

TOPIC: {topic}

{extra_instructions}

Return ONLY the script lines, no markdown fences, no explanation. One scene per line."""


CATEGORY_GUIDANCE = {
    "stoic": "Draw from Stoic philosophy (Marcus Aurelius, Epictetus, Seneca). Use ancient wisdom applied to modern struggles. Themes: discipline, resilience, self-honesty, memento mori.",
    "motivation": "Inspirational and empowering. Focus on overcoming adversity, taking action, breaking free from comfort zones. Raw and honest, not generic motivational cliches.",
    "meditation": "Calm, reflective, mindful. Guide the viewer through inner awareness. Themes: stillness, presence, letting go, breath, acceptance.",
    "horror": "Build dread slowly. Use suggestion over gore. The scariest thing is what you don't see. Themes: isolation, the unknown, things that feel wrong.",
    "love": "Explore love in all forms — romantic, self-love, loss, longing. Honest and vulnerable, not cheesy. Show don't tell.",
    "psychology": "Explore the human mind. Use psychological concepts made accessible. Themes: cognitive biases, behavior patterns, why we do what we do.",
    "history": "Bring historical events or figures to life. Make the past feel present and relevant. Focus on the human story behind the facts.",
    "philosophy": "Deep thinking made accessible. Explore big questions about existence, meaning, consciousness, morality. Challenge assumptions.",
    "nature": "The beauty and power of the natural world. Themes: cycles of life, interconnection, wilderness, seasons, the small and the vast.",
    "scifi": "Speculative and thought-provoking. Near-future scenarios, what-if questions, technology's impact on humanity.",
    "mystery": "Unsolved puzzles, strange phenomena, things that don't add up. Build curiosity and suspense.",
    "life-lesson": "Universal truths learned through experience. Practical wisdom. The kind of advice you wish someone told you earlier.",
    "dark": "Explore the shadow side of human nature. Uncomfortable truths. Not nihilistic — honest.",
    "faith": "Spiritual themes across traditions. Faith, doubt, surrender, grace, the sacred in the ordinary.",
    "money": "Financial wisdom, wealth mindset, the relationship between money and happiness. Honest about both sides.",
    "relationship": "The dynamics between people. Communication, boundaries, attachment, growth. Real talk, not advice columns.",
}

CHARACTER_PRESETS = {
    "man": {
        "name": "Adult Man",
        "visual": "(man:1.4), adult male, medium build",
    },
    "woman": {
        "name": "Adult Woman",
        "visual": "(woman:1.4), adult female, graceful posture",
    },
    "elder": {
        "name": "Wise Elder",
        "visual": "(elderly man:1.4), gray hair, weathered face, wise expression, long simple robe",
    },
    "youth": {
        "name": "Young Person",
        "visual": "(young person:1.4), youthful face, casual clothing, curious expression",
    },
    "warrior": {
        "name": "Warrior",
        "visual": "(warrior:1.4), muscular build, battle-worn armor, scarred, determined expression",
    },
    "monk": {
        "name": "Monk",
        "visual": "(monk:1.4), shaved head, simple robes, calm serene expression, bare feet",
    },
    "child": {
        "name": "Child",
        "visual": "(child:1.4), small figure, innocent expression, simple clothing",
    },
    "silhouette": {
        "name": "Silhouette Figure",
        "visual": "(silhouette figure:1.4), dark outline, featureless, mysterious",
    },
    "stickman": {
        "name": "Stick Figure",
        "visual": "(stick figure:1.4), simple line drawing, basic human shape",
    },
    "businessman": {
        "name": "Business Person",
        "visual": "(man in suit:1.4), professional attire, tie, briefcase, urban",
    },
    "artist": {
        "name": "Artist",
        "visual": "(artist:1.4), paint-stained clothes, creative expression, messy hair",
    },
    "samurai": {
        "name": "Samurai",
        "visual": "(samurai:1.4), traditional armor, katana at side, disciplined posture, topknot hair",
    },
    "philosopher": {
        "name": "Ancient Philosopher",
        "visual": "(philosopher:1.4), toga, sandals, long beard, contemplative expression, scroll in hand",
    },
    "traveler": {
        "name": "Lone Traveler",
        "visual": "(traveler:1.4), worn cloak, backpack, walking staff, weathered boots, distant gaze",
    },
    "robot": {
        "name": "Humanoid Robot",
        "visual": "(humanoid robot:1.4), sleek metal body, glowing eyes, mechanical joints, futuristic",
    },
    "girl": {
        "name": "Young Girl",
        "visual": "(young girl:1.4), long hair, simple dress, gentle expression, bare feet",
    },
}

BACKGROUND_THEMES = {
    "nature": {
        "name": "Nature & Wilderness",
        "visual": "open natural landscape, rolling hills, trees, grass, vast sky",
        "lighting": "natural golden hour light",
    },
    "urban": {
        "name": "Urban City",
        "visual": "city streets, buildings, concrete, modern architecture",
        "lighting": "harsh streetlight, neon glow",
    },
    "forest": {
        "name": "Deep Forest",
        "visual": "dense forest, tall trees, filtered light through canopy, moss, ferns",
        "lighting": "dappled sunlight through leaves",
    },
    "ocean": {
        "name": "Ocean & Coast",
        "visual": "ocean waves, coastline, sandy beach, vast horizon",
        "lighting": "soft coastal light, sea mist",
    },
    "mountain": {
        "name": "Mountains",
        "visual": "mountain peaks, rocky terrain, valleys, snow-capped summits",
        "lighting": "dramatic mountain light, clouds below",
    },
    "temple": {
        "name": "Ancient Temple",
        "visual": "stone ruins, ancient columns, sacred architecture, moss-covered walls",
        "lighting": "soft diffused light, dusty rays",
    },
    "desert": {
        "name": "Desert",
        "visual": "vast sand dunes, empty horizon, cracked earth, heat haze",
        "lighting": "harsh overhead sun, long shadows",
    },
    "space": {
        "name": "Cosmic Space",
        "visual": "starfield, nebula, cosmic void, planets in distance",
        "lighting": "ethereal glow, starlight",
    },
    "minimal": {
        "name": "Minimalist",
        "visual": "clean empty background, simple ground plane, negative space",
        "lighting": "soft even studio light",
    },
    "rain": {
        "name": "Rainy Atmosphere",
        "visual": "rain falling, wet surfaces, reflections on ground, overcast sky",
        "lighting": "dim diffused gray light, rain streaks",
    },
    "night": {
        "name": "Night Scene",
        "visual": "dark night sky, stars or moon, shadows, quiet darkness",
        "lighting": "moonlight, dim blue tones",
    },
    "countryside": {
        "name": "Countryside",
        "visual": "rolling fields, farmland, stone walls, dirt paths, wildflowers",
        "lighting": "warm pastoral light",
    },
    "underwater": {
        "name": "Underwater",
        "visual": "deep ocean, coral, fish, light rays from surface, bubbles",
        "lighting": "blue-green filtered light from above",
    },
    "ruins": {
        "name": "Ancient Ruins",
        "visual": "crumbling stone walls, overgrown vegetation, fallen pillars, forgotten civilization",
        "lighting": "warm afternoon light through broken roof",
    },
    "library": {
        "name": "Old Library",
        "visual": "towering bookshelves, dusty books, reading desk, candlelight, wooden floor",
        "lighting": "warm candlelight, dust particles in air",
    },
    "battlefield": {
        "name": "Battlefield",
        "visual": "scarred terrain, broken weapons, smoke, desolate field, dramatic sky",
        "lighting": "overcast stormy light, fire glow",
    },
    "greek": {
        "name": "Ancient Greece",
        "visual": "marble columns, Greek agora, olive trees, amphitheater, Parthenon-style architecture, Mediterranean hillside, terracotta rooftops, stone pathways",
        "lighting": "warm Mediterranean sunlight, golden afternoon glow",
    },
}

ART_STYLE_TEMPLATES = {
    "sketch": "pencil sketch, black and white, cross hatching, fine line art",
    "watercolor": "watercolor painting, soft washes, flowing colors, paper texture",
    "cinematic": "cinematic, dramatic lighting, highly detailed, vibrant colors",
    "anime": "anime illustration, Studio Ghibli style, vibrant anime colors",
    "ghibli": "Studio Ghibli style, Art by Hayao Miyazaki, hand drawn, cinematic, vivid colors, soft shading, playful",
    "oil": "classical oil painting, rich colors, visible brushstrokes, canvas texture",
    "minimal": "minimalist illustration, clean lines, simple shapes, negative space",
    "charcoal": "charcoal drawing, dramatic shadows, smudged edges, high contrast",
    "stickfigure": "simple stick figure drawing, black lines on white background, whiteboard sketch",
    "realistic": "photorealistic, ultra detailed, professional photography, sharp focus",
}


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
) -> str:
    """Generate a story script using Groq LLM.

    Returns the script text. Optionally saves to output_path.
    """
    num_scenes = max(4, duration // 10)
    cat_guidance = CATEGORY_GUIDANCE.get(category, "")
    if cat_guidance:
        cat_guidance = f"CATEGORY GUIDANCE ({category}):\n{cat_guidance}"

    art_prompt = ART_STYLE_TEMPLATES.get(art_style, ART_STYLE_TEMPLATES["sketch"])

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

    prompt = SCRIPT_PROMPT.format(
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

    print(f"-> Generating script with AI...")
    print(f"   Topic: {topic}")
    print(f"   Category: {category}")
    print(f"   Art style: {art_style}")
    if character:
        print(f"   Character: {CHARACTER_PRESETS.get(character, {}).get('name', character)}")
    if background:
        print(f"   Background: {BACKGROUND_THEMES.get(background, {}).get('name', background)}")
    print(f"   Duration: ~{duration}s ({num_scenes} scenes)")

    if settings.llm_provider == "groq":
        from groq import Groq
        client = Groq(api_key=settings.groq_api_key)
        response = client.chat.completions.create(
            model=settings.groq_model,
            max_tokens=4000,
            temperature=0.8,
            messages=[{"role": "user", "content": prompt}],
        )
        script = response.choices[0].message.content.strip()

    elif settings.llm_provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        script = "".join(b.text for b in response.content if b.type == "text").strip()

    else:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")

    # Clean up — remove markdown fences if the LLM wrapped them
    if script.startswith("```"):
        lines = script.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        script = "\n".join(lines).strip()

    # Validate — check it looks like a timeline script
    valid_lines = [l for l in script.split("\n") if "|" in l and l.strip()]
    if len(valid_lines) < 3:
        print(f"   Warning: LLM returned {len(valid_lines)} valid lines, expected {num_scenes}+")

    print(f"   Generated {len(valid_lines)} scenes")

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(script)
        print(f"   Saved to: {output_path}")

    return script
