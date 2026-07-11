"""Script parsing — timeline format detection, scene splitting, LLM query generation."""
import json
from typing import List

from ..config import settings
from ..narration import POPULAR_VOICES
from .models import Scene
from .presets import MOOD_PRESETS


def _parse_timestamp(ts: str) -> float:
    """Parse timestamp like '0:00', '1:30', '0:05', or raw seconds '5'."""
    ts = ts.strip()
    if ":" in ts:
        parts = ts.split(":")
        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        elif len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    return float(ts)


def _is_timeline_script(script: str) -> bool:
    """Check if the script uses timeline format (lines with | separator)."""
    lines = [l.strip() for l in script.strip().split("\n") if l.strip()]
    if len(lines) < 2:
        return False
    return all("|" in line for line in lines)


def _parse_timeline_script(script: str) -> List[Scene]:
    """Parse a timeline-formatted script.

    Format:
        0:00 | Narration text | search keyword
        0:05 | Narration text | search keyword | image
        0:12 | Narration text | search keyword | video | dramatic
        0:18 | Narration text | search keyword | image | tension | -30%

    Fields (pipe-separated):
        1. Timestamp (required)
        2. Narration text (required)
        3. Search keyword (optional)
        4. Visual type: "image" or "video" (optional, default: image)
        5. Mood/voice: mood preset name OR voice shortcut (optional)
        6. Rate: speech speed like "-30%", "+10%" (optional)
    """
    lines = [l.strip() for l in script.strip().split("\n") if l.strip()]
    scenes = []

    for line in lines:
        if line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            continue
        timestamp = _parse_timestamp(parts[0])
        text = parts[1]
        search_query = parts[2] if len(parts) >= 3 else ""
        visual_type = "image"
        scene_mood = None
        scene_voice = None
        scene_rate = None

        for part in parts[3:]:
            val = part.strip().lower()
            if val in ("video", "image"):
                visual_type = val
            elif val in MOOD_PRESETS:
                scene_mood = val
            elif val in POPULAR_VOICES:
                scene_voice = val
            elif "%" in val:
                scene_rate = val

        scenes.append(Scene(
            text=text,
            search_query=search_query,
            start_time=timestamp,
            visual_type=visual_type,
            mood=scene_mood,
            voice=scene_voice,
            rate=scene_rate,
        ))

    # Calculate durations from timestamps
    for i in range(len(scenes) - 1):
        scenes[i].duration = scenes[i + 1].start_time - scenes[i].start_time
    # Last scene: use same duration as previous, or 10s default
    if scenes and scenes[-1].duration <= 0:
        if len(scenes) >= 2:
            scenes[-1].duration = scenes[-2].duration
        else:
            scenes[-1].duration = 10.0

    # Ensure every scene has a visual query — fill empty ones from neighbors
    for i, scene in enumerate(scenes):
        if not scene.search_query or not scene.search_query.strip():
            if i > 0 and scenes[i - 1].search_query:
                scene.search_query = scenes[i - 1].search_query
            elif i + 1 < len(scenes) and scenes[i + 1].search_query:
                scene.search_query = scenes[i + 1].search_query
            else:
                scene.search_query = "cinematic background"

    return scenes


def _split_into_scenes(script: str) -> List[Scene]:
    """Split script into scenes — either parse timeline or use LLM."""

    # If script uses timeline format, parse directly
    if _is_timeline_script(script):
        scenes = _parse_timeline_script(script)
        # Generate search queries for scenes that don't have one
        scenes_needing_query = [s for s in scenes if not s.search_query]
        if scenes_needing_query:
            _generate_search_queries(scenes_needing_query)
        return scenes

    # Otherwise, use LLM to split
    prompt = (
        f"Split this narration script into scenes for a short video. "
        f"Each scene is 1-2 sentences that will be spoken as voiceover.\n\n"
        f"For each scene, provide a search query to find matching visuals "
        f"(stock footage or images).\n\n"
        f"Return ONLY valid JSON, no markdown:\n"
        f'{{"scenes": [\n'
        f'  {{"text": "<narration text>", "search_query": "<2-4 word visual search>", '
        f'"visual_type": "<video or image>"}}\n'
        f"]}}\n\n"
        f"Script:\n{script}"
    )

    if settings.llm_provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(b.text for b in response.content if b.type == "text").strip()

    elif settings.llm_provider == "groq":
        from groq import Groq
        client = Groq(api_key=settings.groq_api_key)
        response = client.chat.completions.create(
            model=settings.groq_model,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content.strip()
    else:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")

    try:
        data = json.loads(raw)
        scenes = []
        for s in data.get("scenes", []):
            scenes.append(Scene(
                text=s["text"],
                search_query=s.get("search_query", ""),
                visual_type=s.get("visual_type", "video"),
            ))
        return scenes
    except (json.JSONDecodeError, KeyError):
        return [Scene(text=script, search_query="cinematic background", visual_type="video")]


def _generate_search_queries(scenes: List[Scene]) -> None:
    """Use LLM to generate search queries for scenes that don't have one."""
    texts = "\n".join(f"{i+1}. {s.text}" for i, s in enumerate(scenes))
    prompt = (
        f"For each narration line below, suggest a 2-4 word image search query "
        f"to find a beautiful, relevant photo or artwork.\n\n"
        f"The images will be used as background visuals for a narrated video. "
        f"Suggest searches that would find: nature landscapes, moody photography, "
        f"artistic portraits, silhouettes, or atmospheric scenes that match the MOOD "
        f"of each line. Avoid abstract/generic terms.\n\n"
        f"{texts}\n\n"
        f"Return ONLY valid JSON: {{\"queries\": [\"query1\", \"query2\", ...]}}"
    )

    if settings.llm_provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(b.text for b in response.content if b.type == "text").strip()
    elif settings.llm_provider == "groq":
        from groq import Groq
        client = Groq(api_key=settings.groq_api_key)
        response = client.chat.completions.create(
            model=settings.groq_model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content.strip()
    else:
        return

    try:
        data = json.loads(raw)
        queries = data.get("queries", [])
        for i, scene in enumerate(scenes):
            if i < len(queries):
                scene.search_query = queries[i]
    except (json.JSONDecodeError, KeyError):
        for scene in scenes:
            if not scene.search_query:
                scene.search_query = "cinematic background"


def _generate_hook_text(script: str) -> str:
    """Use LLM to generate a short hook/summary text for the video intro overlay."""
    prompt = (
        "You are an expert short-form video editor. Given the following narration script, "
        "write a single short hook line (max 6 words) that would appear as "
        "a text overlay at the start of the video to grab the viewer's attention.\n\n"
        "The hook should tease the core topic or create curiosity. "
        "Use natural capitalization (capitalize first letter only, not all caps). "
        "Examples: 'The truth nobody tells you', 'Why most people fail', "
        "'This changed everything'\n\n"
        f"Script:\n{script}\n\n"
        "Return ONLY the hook text, nothing else. Max 6 words."
    )

    try:
        if settings.llm_provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            response = client.messages.create(
                model=settings.anthropic_model,
                max_tokens=50,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = "".join(b.text for b in response.content if b.type == "text").strip()
        elif settings.llm_provider == "groq":
            from groq import Groq
            client = Groq(api_key=settings.groq_api_key)
            response = client.chat.completions.create(
                model=settings.groq_model,
                max_tokens=50,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.choices[0].message.content.strip()
        else:
            return ""
    except Exception:
        return ""

    hook = raw.strip().strip('"').strip("'")
    words = hook.split()
    if len(words) > 6:
        hook = " ".join(words[:6])
    return hook
