"""
Post-render clip enhancement — uses an LLM to analyze a rendered clip and
generate enhancement instructions (text overlays, transitions, pacing fixes),
then applies them via ffmpeg.

Can run automatically after rendering or be triggered manually via the
'enhance' subcommand.
"""
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional

from .config import settings
from .render import FFMPEG, _run, _render_hook_png, generate_crowd_roar as _gen_crowd, generate_sfx as _gen_sfx, mix_sfx as _mix_sfx

_VW = settings.vertical_width
_VH = settings.vertical_height

ANALYZE_PROMPT = """You are a professional short-form video editor. Analyze this clip and suggest concrete enhancements to make it more engaging and polished.

CLIP INFO:
- Duration: {duration:.1f} seconds
- Title: {title}
- Category: {category}
- Hook text: {hook_text}
- Virality score: {score}/100
- Reason it was selected: {reason}

TRANSCRIPT (with timestamps relative to clip start):
{transcript}

{user_prompt}

Suggest enhancements from these types:
1. **text_overlay**: Add text at a specific timestamp to reinforce key moments, add context, or keep visual interest during slow sections. Good for: emphasizing a key phrase the narrator says, adding "Part 1" / "Wait for it..." type engagement hooks, labeling what's happening.
2. **zoom**: Zoom into the frame at a specific moment for emphasis (e.g. reaction moments, punchlines).
3. **speed**: Speed up or slow down a section (e.g. slow-mo a key moment, speed through a boring setup).
4. **flash**: Quick white flash transition between distinct scenes or topic changes.
5. **crowd_roar**: Add stadium crowd cheering/roaring sound effect. PERFECT for sports content — use at goal celebrations, amazing plays, victories. Also works for hype moments in any video (big reveal, concert crowd). The effect layers ON TOP of the existing audio, it doesn't replace it.
6. **sound_effect**: Add a sound effect at a specific moment. Types available: "whoosh" (fast transition/movement), "impact" (hit/collision/dramatic moment), "rise" (building tension/anticipation before a big moment), "drop" (bass drop after buildup).

Rules:
- Only suggest enhancements that genuinely improve the clip. Don't add things just because you can.
- Be precise with timestamps — they must fall within 0.0 to {duration:.1f}
- Text overlays should be SHORT (max 5 words), punchy, and add value the audio doesn't already provide
- Don't overlay text that duplicates what the captions already show word-for-word
- For zoom, keep it subtle (1.2x-1.5x) and brief (0.3-1.0 seconds)
- For speed changes, keep them subtle (0.7x-1.5x) and purposeful
- For crowd_roar, use at peak emotional moments (goals, celebrations, victories, reveals). Duration 2-5 seconds. Volume 0.3-0.8 (don't overpower the original audio).
- For sound_effect, use sparingly — one or two per clip max. They should feel natural, not gimmicky.

Return ONLY valid JSON:
{{
  "enhancements": [
    {{
      "type": "text_overlay",
      "start": <float seconds from clip start>,
      "duration": <float seconds to show>,
      "text": "<short text>",
      "position": "<top|center|bottom>",
      "reason": "<why this helps>"
    }},
    {{
      "type": "zoom",
      "start": <float seconds>,
      "duration": <float seconds>,
      "scale": <float 1.0-1.5>,
      "reason": "<why>"
    }},
    {{
      "type": "speed",
      "start": <float seconds>,
      "end": <float seconds>,
      "factor": <float, e.g. 0.5 for half speed, 2.0 for double>,
      "reason": "<why>"
    }},
    {{
      "type": "flash",
      "at": <float seconds>,
      "reason": "<why>"
    }},
    {{
      "type": "crowd_roar",
      "start": <float seconds>,
      "duration": <float seconds, 2-5>,
      "volume": <float 0.3-0.8, how loud relative to original audio>,
      "reason": "<why>"
    }},
    {{
      "type": "sound_effect",
      "at": <float seconds>,
      "effect": "<one of: whoosh, impact, rise, drop>",
      "reason": "<why>"
    }}
  ]
}}

If the clip is already good and doesn't need enhancement, return {{"enhancements": []}}.
"""


@dataclass
class Enhancement:
    type: str
    reason: str = ""
    # text_overlay
    start: float = 0.0
    duration: float = 2.0
    text: str = ""
    position: str = "bottom"
    # zoom
    scale: float = 1.3
    # speed
    end: float = 0.0
    factor: float = 1.0
    # flash
    at: float = 0.0
    # crowd_roar
    volume: float = 0.5
    # sound_effect
    effect: str = "whoosh"


def _call_llm(prompt: str) -> str:
    if settings.llm_provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in response.content if b.type == "text").strip()

    elif settings.llm_provider == "groq":
        from groq import Groq
        client = Groq(api_key=settings.groq_api_key)
        response = client.chat.completions.create(
            model=settings.groq_model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()

    raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")


def analyze_clip(
    duration: float,
    title: str = "",
    category: str = "",
    hook_text: str = "",
    score: int = 0,
    reason: str = "",
    transcript: str = "",
    user_prompt: str = "",
) -> List[Enhancement]:
    prompt_text = ""
    if user_prompt:
        prompt_text = f"ADDITIONAL INSTRUCTIONS FROM THE USER:\n{user_prompt}"

    prompt = ANALYZE_PROMPT.format(
        duration=duration,
        title=title,
        category=category,
        hook_text=hook_text,
        score=score,
        reason=reason,
        transcript=transcript or "(no transcript available)",
        user_prompt=prompt_text,
    )

    raw = _call_llm(prompt)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(raw[start:end])
            except json.JSONDecodeError:
                return []
        else:
            return []

    enhancements = []
    for e in data.get("enhancements", []):
        try:
            enhancements.append(Enhancement(
                type=e["type"],
                reason=e.get("reason", ""),
                start=float(e.get("start", 0)),
                duration=float(e.get("duration", 2.0)),
                text=e.get("text", ""),
                position=e.get("position", "bottom"),
                scale=float(e.get("scale", 1.3)),
                end=float(e.get("end", 0)),
                factor=float(e.get("factor", 1.0)),
                at=float(e.get("at", 0)),
                volume=float(e.get("volume", 0.5)),
                effect=e.get("effect", "whoosh"),
            ))
        except (KeyError, ValueError, TypeError):
            continue

    return enhancements


def _apply_text_overlay(input_path: str, output_path: str, enh: Enhancement, clip_duration: float) -> None:
    overlay_png = output_path + f".overlay_{enh.start:.1f}.png"
    _render_hook_png(enh.text, overlay_png)

    y_map = {"top": "120", "center": "(H-h)/2", "bottom": "H-h-200"}
    y_expr = y_map.get(enh.position, "H-h-200")

    fade_in = enh.start
    fade_out = min(enh.start + enh.duration, clip_duration)

    vf = (
        f"[1:v]format=rgba[ovl];"
        f"[0:v][ovl]overlay="
        f"x=(W-w)/2:y={y_expr}:"
        f"enable='between(t,{fade_in:.2f},{fade_out:.2f})'"
    )
    _run([
        FFMPEG, "-y",
        "-i", input_path,
        "-i", overlay_png,
        "-filter_complex", vf,
        "-c:a", "copy",
        output_path,
    ])
    os.unlink(overlay_png)


def _apply_zoom(input_path: str, output_path: str, enh: Enhancement) -> None:
    zoom_end = enh.start + enh.duration
    s = enh.scale
    # Use filter_complex with escaped expressions to avoid comma parsing issues.
    # The crop filter's w/h/x/y use 'if(between())' which contains commas that
    # ffmpeg misreads as parameter separators in -vf mode.
    inv_s = 1.0 / s
    vf = (
        f"[0:v]crop="
        f"w='if(between(t\\,{enh.start:.2f}\\,{zoom_end:.2f})\\,iw*{inv_s:.4f}\\,iw)':"
        f"h='if(between(t\\,{enh.start:.2f}\\,{zoom_end:.2f})\\,ih*{inv_s:.4f}\\,ih)':"
        f"x='(iw-out_w)/2':y='(ih-out_h)/2',"
        f"scale={_VW}:{_VH}:flags=lanczos[vout]"
    )
    _run([
        FFMPEG, "-y",
        "-i", input_path,
        "-filter_complex", vf,
        "-map", "[vout]", "-map", "0:a",
        "-c:a", "copy",
        output_path,
    ])


def _apply_flash(input_path: str, output_path: str, enh: Enhancement) -> None:
    flash_dur = 0.1
    t = enh.at
    vf = (
        f"drawbox=x=0:y=0:w=iw:h=ih:color=white@0.8:t=fill:"
        f"enable='between(t,{t:.2f},{t + flash_dur:.2f})'"
    )
    _run([
        FFMPEG, "-y",
        "-i", input_path,
        "-vf", vf,
        "-c:a", "copy",
        output_path,
    ])


def _apply_speed(input_path: str, output_path: str, enh: Enhancement, clip_duration: float) -> None:
    seg_start = enh.start
    seg_end = enh.end if enh.end > enh.start else enh.start + 2.0
    factor = max(0.5, min(2.0, enh.factor))
    atempo = factor

    # Split into 3 parts: before, speed-changed, after
    # Use trim + setpts + concat
    pts_factor = 1.0 / factor

    vf = (
        f"[0:v]split=3[v1][v2][v3];"
        f"[v1]trim=0:{seg_start:.2f},setpts=PTS-STARTPTS[pre];"
        f"[v2]trim={seg_start:.2f}:{seg_end:.2f},setpts={pts_factor}*(PTS-STARTPTS)[mid];"
        f"[v3]trim={seg_end:.2f},setpts=PTS-STARTPTS[post];"
        f"[pre][mid][post]concat=n=3:v=1:a=0[vout]"
    )
    af = (
        f"[0:a]asplit=3[a1][a2][a3];"
        f"[a1]atrim=0:{seg_start:.2f},asetpts=PTS-STARTPTS[apre];"
        f"[a2]atrim={seg_start:.2f}:{seg_end:.2f},atempo={atempo}[amid];"
        f"[a3]atrim={seg_end:.2f},asetpts=PTS-STARTPTS[apost];"
        f"[apre][amid][apost]concat=n=3:v=0:a=1[aout]"
    )
    _run([
        FFMPEG, "-y",
        "-i", input_path,
        "-filter_complex", f"{vf};{af}",
        "-map", "[vout]", "-map", "[aout]",
        output_path,
    ])


def _apply_crowd_roar(input_path: str, output_path: str, enh: Enhancement) -> None:
    sfx_path = output_path + ".crowd.m4a"
    try:
        duration = max(1.0, min(8.0, enh.duration))
        _gen_crowd(sfx_path, duration)
        vol = max(0.1, min(1.0, enh.volume))
        _mix_sfx(input_path, sfx_path, output_path, offset=enh.start, volume=vol)
    finally:
        if os.path.exists(sfx_path):
            os.unlink(sfx_path)


def _apply_sound_effect(input_path: str, output_path: str, enh: Enhancement) -> None:
    sfx_path = output_path + ".sfx.m4a"
    try:
        _gen_sfx(sfx_path, enh.effect)
        _mix_sfx(input_path, sfx_path, output_path, offset=enh.at, volume=0.6)
    finally:
        if os.path.exists(sfx_path):
            os.unlink(sfx_path)


def apply_enhancements(
    input_path: str,
    output_path: str,
    enhancements: List[Enhancement],
    clip_duration: float,
) -> str:
    if not enhancements:
        import shutil
        shutil.copy2(input_path, output_path)
        return output_path

    current = input_path
    with tempfile.TemporaryDirectory() as tmp:
        for i, enh in enumerate(enhancements):
            is_last = (i == len(enhancements) - 1)
            out = output_path if is_last else os.path.join(tmp, f"step_{i}.mp4")

            print(f"      [{i+1}/{len(enhancements)}] {enh.type}: {enh.reason}")

            try:
                if enh.type == "text_overlay":
                    _apply_text_overlay(current, out, enh, clip_duration)
                elif enh.type == "zoom":
                    _apply_zoom(current, out, enh)
                elif enh.type == "flash":
                    _apply_flash(current, out, enh)
                elif enh.type == "speed":
                    _apply_speed(current, out, enh, clip_duration)
                elif enh.type == "crowd_roar":
                    _apply_crowd_roar(current, out, enh)
                elif enh.type == "sound_effect":
                    _apply_sound_effect(current, out, enh)
                else:
                    if is_last:
                        import shutil
                        shutil.copy2(current, out)
                    continue
            except RuntimeError as e:
                print(f"      Warning: {enh.type} failed, skipping: {e}")
                if is_last:
                    import shutil
                    shutil.copy2(current, out)
                continue

            current = out

    return output_path


def enhance_clip(
    video_path: str,
    output_path: str,
    title: str = "",
    category: str = "",
    hook_text: str = "",
    score: int = 0,
    reason: str = "",
    transcript: str = "",
    user_prompt: str = "",
) -> str:
    duration = _get_duration(video_path)

    print(f"   Analyzing clip for enhancements...")
    enhancements = analyze_clip(
        duration=duration,
        title=title,
        category=category,
        hook_text=hook_text,
        score=score,
        reason=reason,
        transcript=transcript,
        user_prompt=user_prompt,
    )

    if not enhancements:
        print(f"   No enhancements suggested — clip is already good.")
        import shutil
        shutil.copy2(video_path, output_path)
        return output_path

    print(f"   Applying {len(enhancements)} enhancement(s)...")
    return apply_enhancements(video_path, output_path, enhancements, duration)


def _get_duration(path: str) -> float:
    ffprobe = os.path.join(os.path.dirname(FFMPEG), "ffprobe")
    cmd = [
        ffprobe,
        "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 30.0
