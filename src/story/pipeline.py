"""Main create_story pipeline — orchestrates TTS, visuals, and ffmpeg rendering."""
import os
import shutil
import subprocess
import tempfile
from typing import List, Optional, Tuple

from ..config import settings
from ..render import (
    reframe_vertical, burn_captions, add_film_grain, add_text_hook,
    burn_thought_bubbles, burn_footnote, detect_head_position, click_head_position,
)
from ..narration import generate_narration, generate_silence, is_silent_scene, POPULAR_VOICES, MOOD_VOICE_SETTINGS
from ..transcribe import transcribe, Word
from ..captions import build_ass
from ..imagegen import generate_scene_image, generate_scene_video, get_variant_paths

from .models import Scene, BubbleGroup
from .presets import MOOD_PRESETS, VOICE_MUSIC_MAP
from .script_parser import _split_into_scenes, _generate_hook_text
from .visuals import _download_pexels_video, _download_youtube_clip, _download_scene_image
from .video_utils import (
    _image_to_video,
    _trim_video_to_duration,
    _get_audio_duration,
    _concat_scenes,
    _concat_scenes_with_audio,
    _concat_with_transitions,
    _merge_audio_video,
    _pad_audio_to_duration,
    _concat_audios,
    _make_text_card,
)

_STYLE_MAP = {
    "pen": "ink drawing illustration",
    "pencil": "pencil sketch drawing",
    "watercolor": "watercolor painting art",
    "anime": "anime illustration art",
    "ghibli": "studio ghibli anime art",
    "cinematic": "cinematic dramatic photography",
    "oil": "oil painting classical art",
    "comic": "comic book illustration",
    "minimal": "minimalist clean design",
    "pixel": "pixel art retro",
    "charcoal": "charcoal drawing dark",
    "storybook": "storybook illustration children",
    "realistic": "photography realistic 4k",
    "stickfigure": "simple drawing whiteboard",
    "sketch": "pencil sketch graphite drawing",
}


# ---------------------------------------------------------------------------
# TTS / narration
# ---------------------------------------------------------------------------

def _resolve_tts_rate(voice: str, voice_rate: Optional[str]) -> str:
    if voice_rate:
        return voice_rate
    if voice in ("warm", "caring", "storyteller", "dark", "tension"):
        return "-25%"
    return "-15%"


def _generate_scene_audio(scene: Scene, audio_path: str, voice_name: str, tts_rate: str) -> float:
    """Generate TTS (or silence) for one scene. Returns audio duration."""
    if is_silent_scene(scene.text):
        dur = scene.duration if scene.duration > 0 else 3.0
        generate_silence(audio_path, dur)
        scene.audio_path = audio_path
        return dur

    s_rate = tts_rate
    s_pitch = "+0Hz"
    s_mood = ""
    s_voice = voice_name

    if scene.mood and scene.mood in MOOD_VOICE_SETTINGS:
        ms = MOOD_VOICE_SETTINGS[scene.mood]
        s_rate = ms["rate"]
        s_pitch = ms["pitch"]
        s_mood = scene.mood
    elif scene.mood and scene.mood in MOOD_PRESETS:
        s_rate = MOOD_PRESETS[scene.mood]["rate"]

    if scene.voice:
        s_voice = POPULAR_VOICES.get(scene.voice, scene.voice)
    if scene.rate:
        s_rate = scene.rate

    _, scene.timings = generate_narration(scene.text, audio_path, voice=s_voice, rate=s_rate, pitch=s_pitch, mood=s_mood)
    scene.audio_path = audio_path
    return _get_audio_duration(audio_path)


def _generate_narration_track(scenes: List[Scene], tmp: str, voice: str, voice_rate: Optional[str]) -> str:
    """Generate per-scene TTS, set scene durations, build & return a padded narration mp3."""
    voice_name = POPULAR_VOICES.get(voice, voice)
    tts_rate = _resolve_tts_rate(voice, voice_rate)
    print(f"   Voice: {voice_name} | Rate: {tts_rate}")

    for i, scene in enumerate(scenes):
        audio_path = os.path.join(tmp, f"scene_{i:02d}.mp3")
        tts_dur = _generate_scene_audio(scene, audio_path, voice_name, tts_rate)

        if is_silent_scene(scene.text):
            if scene.duration <= 0:
                scene.duration = tts_dur
            mood_label = " (silent)"
        else:
            if scene.duration <= 0:
                scene.duration = tts_dur + 2.5
            elif scene.duration < tts_dur + 1.5:
                scene.duration = tts_dur + 1.5
            mood_label = f" [{scene.mood}]" if scene.mood else ""

        print(f"   Scene {i+1}: {scene.duration:.1f}s (tts: {tts_dur:.1f}s){mood_label} - \"{scene.text[:50]}\"")

    print("-> Building timed narration track...")
    padded = []
    for i, scene in enumerate(scenes):
        padded_path = os.path.join(tmp, f"padded_{i:02d}.mp3")
        _pad_audio_to_duration(scene.audio_path, scene.duration, padded_path)
        padded.append(padded_path)

    out = os.path.join(os.path.dirname(tmp), "narration_full.mp3")
    _concat_audios(padded, out)
    return out


# ---------------------------------------------------------------------------
# Visual style helpers
# ---------------------------------------------------------------------------

def _resolve_style_suffix(art_style: str, image_category: str) -> Tuple[str, List[str]]:
    """Return (style_suffix, fallback_queries) for search augmentation."""
    fallback = ["cinematic landscape", "moody atmospheric", "dark dramatic"]
    suffix = ""

    if art_style:
        from ..imagegen import ART_STYLES
        s = ART_STYLES.get(art_style)
        if s:
            term = _STYLE_MAP.get(art_style, s["name"].lower())
            suffix = " " + term
            fallback = [f"{term} background", f"{term} scene", f"{term} mood"]
    elif image_category:
        from ..imagegen import CATEGORY_STYLES
        cat = CATEGORY_STYLES.get(image_category)
        if cat:
            mood_word = cat["mood"].split()[0]
            suffix = " " + mood_word
            fallback = [f"{cat['mood']} landscape", f"{cat['mood']} atmosphere", f"{cat['mood']} scene"]

    return suffix, fallback


def _generate_scene_visual(
    scene: Scene,
    visual_path: str,
    video_path: str,
    styled_query: str,
    *,
    visuals: str,
    art_style: str,
    image_category: str,
    animation: str,
    caption_style: str,
    style_suffix: str,
    fallback_theme: List[str],
) -> Tuple[bool, Optional[str]]:
    """Fetch or generate the visual for one scene. Returns (got_visual, img_path)."""
    use_ai = visuals in ("openai", "sd", "veo")
    got_visual = False
    img_path = None

    if use_ai:
        if visuals == "veo":
            veo_path = visual_path + "_veo.mp4"
            if generate_scene_video(scene.text, scene.search_query, veo_path, duration=scene.duration, art_style=art_style, category=image_category):
                _trim_video_to_duration(veo_path, scene.duration, video_path)
                got_visual = True
                print("      [Veo video generated]")
        else:
            ai_img = visual_path + "_ai.png"
            if generate_scene_image(scene.text, scene.search_query, ai_img, provider=visuals, art_style=art_style, category=image_category):
                if caption_style == "bubble":
                    scene.head_pos = detect_head_position(ai_img, video_w=settings.vertical_width, video_h=settings.vertical_height)
                    if scene.head_pos:
                        print(f"      [Face detected at {scene.head_pos}]")
                img_path = ai_img
                _image_to_video(ai_img, scene.duration, video_path, animation=animation)
                got_visual = True
                print("      [AI illustration generated]")

    if not got_visual and scene.visual_type == "video":
        pexels_path = visual_path + "_pexels.mp4"
        if _download_pexels_video(styled_query, pexels_path):
            reframed = visual_path + "_reframed.mp4"
            reframe_vertical(pexels_path, reframed, mode="crop")
            _trim_video_to_duration(reframed, scene.duration, video_path)
            got_visual = True
            print("      [Pexels video]")

        if not got_visual:
            yt_path = visual_path + "_yt.mp4"
            if _download_youtube_clip(styled_query + " stock footage", yt_path):
                reframed = visual_path + "_reframed.mp4"
                reframe_vertical(yt_path, reframed, mode="crop")
                _trim_video_to_duration(reframed, scene.duration, video_path)
                got_visual = True
                print("      [YouTube video]")

    if not got_visual:
        dl_path = visual_path + ".jpg"
        if _download_scene_image(styled_query, dl_path):
            if caption_style == "bubble" and not scene.head_pos:
                scene.head_pos = detect_head_position(dl_path, video_w=settings.vertical_width, video_h=settings.vertical_height)
            img_path = dl_path
            _image_to_video(dl_path, scene.duration, video_path, animation=animation)
            got_visual = True
            print("      [Image found]")

    if not got_visual:
        words = scene.search_query.split()
        fallback_queries = []
        if len(words) > 2:
            fallback_queries.append(" ".join(words[:2]) + style_suffix)
        fallback_queries.extend(fallback_theme)
        fb_img = visual_path + "_fb.jpg"
        for fq in fallback_queries:
            if _download_scene_image(fq, fb_img):
                img_path = fb_img
                _image_to_video(fb_img, scene.duration, video_path, animation=animation)
                got_visual = True
                print(f"      [Fallback image: {fq}]")
                break

    if not got_visual:
        print("      [Text card - no visual found]")
        _make_text_card(scene.text[:80], scene.duration, video_path)

    return got_visual, img_path


def _generate_all_visuals(
    scenes: List[Scene],
    tmp: str,
    *,
    visuals: str,
    art_style: str,
    image_category: str,
    animation: str,
    caption_style: str,
) -> Tuple[List[str], List[str]]:
    """Generate visuals for all scenes. Returns (scene_video_paths, scene_img_paths)."""
    use_ai = visuals in ("openai", "sd", "veo")

    if use_ai:
        from ..imagegen import ART_STYLES, CATEGORY_STYLES
        label = ""
        if art_style and art_style in ART_STYLES:
            label = f", style: {ART_STYLES[art_style]['name']}"
        elif image_category and image_category in CATEGORY_STYLES:
            resolved = CATEGORY_STYLES[image_category]["style"]
            label = f", category: {image_category} → {ART_STYLES[resolved]['name']}"
        verb = "AI videos with Google Veo" if visuals == "veo" else f"AI illustrations ({visuals})"
        print(f"\n-> Generating {verb}{label} for each scene...")
    else:
        print("\n-> Downloading visuals for each scene...")

    style_suffix, fallback_theme = _resolve_style_suffix(art_style, image_category)
    if style_suffix:
        print(f"   Visual theme: \"{style_suffix.strip()}\" (applied to all searches)")

    scene_videos, scene_img_paths = [], []
    for i, scene in enumerate(scenes):
        styled_query = scene.search_query + style_suffix
        print(f"   Scene {i+1}/{len(scenes)}: \"{styled_query}\" ({scene.duration:.1f}s)")
        visual_path = os.path.join(tmp, f"visual_{i:02d}")
        video_path = os.path.join(tmp, f"scene_video_{i:02d}.mp4")
        _, img_path = _generate_scene_visual(
            scene, visual_path, video_path, styled_query,
            visuals=visuals, art_style=art_style, image_category=image_category,
            animation=animation, caption_style=caption_style,
            style_suffix=style_suffix, fallback_theme=fallback_theme,
        )
        scene_img_paths.append(img_path)
        scene_videos.append(video_path)

    return scene_videos, scene_img_paths, style_suffix, fallback_theme


# ---------------------------------------------------------------------------
# Review loop
# ---------------------------------------------------------------------------

def _run_review_loop(
    scenes: List[Scene],
    scene_img_paths: List[Optional[str]],
    scene_videos: List[str],
    scene_variants: List[List[str]],
    review_dir: str,
    tmp: str,
    *,
    visuals: str,
    art_style: str,
    image_category: str,
    animation: str,
    caption_style: str,
    style_suffix: str,
    fallback_theme: List[str],
) -> None:
    """Interactive review loop — lets user regenerate, pick variants, tag heads."""

    def _refresh_preview(idx: int) -> None:
        for f in os.listdir(review_dir):
            if f.startswith(f"scene_{idx+1:02d}"):
                os.unlink(os.path.join(review_dir, f))
        for vi, vp in enumerate(scene_variants[idx]):
            ext = os.path.splitext(vp)[1] or ".png"
            name = f"scene_{idx+1:02d}_v{vi+1}{ext}" if len(scene_variants[idx]) > 1 else f"scene_{idx+1:02d}{ext}"
            shutil.copy2(vp, os.path.join(review_dir, name))

    def _cmd_open(idx: int) -> None:
        variants = scene_variants[idx] if idx < len(scene_variants) else []
        img = scene_img_paths[idx]
        if not img:
            print(f"  No image for scene {idx+1}")
            return
        if len(variants) > 1:
            for vi, vp in enumerate(variants):
                ext = os.path.splitext(vp)[1] or ".png"
                pv = os.path.join(review_dir, f"scene_{idx+1:02d}_v{vi+1}{ext}")
                if os.path.exists(pv):
                    subprocess.run(["open", pv], capture_output=True)
        else:
            ext = os.path.splitext(img)[1] or ".png"
            pv = os.path.join(review_dir, f"scene_{idx+1:02d}{ext}")
            if os.path.exists(pv):
                subprocess.run(["open", pv], capture_output=True)
            else:
                print(f"  No image for scene {idx+1}")

    def _cmd_pick(idx: int, parts: List[str]) -> None:
        variants = scene_variants[idx] if idx < len(scene_variants) else []
        if not variants:
            print(f"  No variants for scene {idx+1}")
            return
        if len(parts) == 2:
            for vi, vp in enumerate(variants):
                ext = os.path.splitext(vp)[1] or ".png"
                pv = os.path.join(review_dir, f"scene_{idx+1:02d}_v{vi+1}{ext}")
                if os.path.exists(pv):
                    subprocess.run(["open", pv], capture_output=True)
            print(f"  Opened {len(variants)} variants. Type: pick {idx+1} <variant#>")
            return
        try:
            vi = int(parts[2]) - 1
        except ValueError:
            print(f"  Usage: pick {idx+1} 2")
            return
        if vi < 0 or vi >= len(variants):
            print(f"  Variant {vi+1} out of range (1-{len(variants)})")
            return
        chosen = variants[vi]
        scene_img_paths[idx] = chosen
        scenes[idx].head_pos = None
        video_path = os.path.join(tmp, f"scene_video_{idx:02d}.mp4")
        _image_to_video(chosen, scenes[idx].duration, video_path, animation=animation)
        scene_videos[idx] = video_path
        if caption_style == "bubble":
            scenes[idx].head_pos = detect_head_position(chosen, video_w=settings.vertical_width, video_h=settings.vertical_height)
        ext = os.path.splitext(chosen)[1] or ".png"
        shutil.copy2(chosen, os.path.join(review_dir, f"scene_{idx+1:02d}{ext}"))
        print(f"  Scene {idx+1}: using variant {vi+1}")

    def _cmd_head(idx: int, parts: List[str]) -> None:
        vw, vh = settings.vertical_width, settings.vertical_height
        img = scene_img_paths[idx]

        if len(parts) == 2:
            if img and os.path.exists(img):
                print(f"  Opening scene {idx+1} — click on the head position...")
                pos = click_head_position(img, video_w=vw, video_h=vh, current_head_pos=scenes[idx].head_pos)
                if pos:
                    scenes[idx].head_pos = pos
                    print(f"  Scene {idx+1}: head set to ({pos[0]}, {pos[1]})")
                else:
                    print(f"  Scene {idx+1}: cancelled (window closed)")
            else:
                print(f"  No image for scene {idx+1}")
        elif len(parts) == 3 and parts[2].lower() == "auto":
            if img and os.path.exists(img):
                scenes[idx].head_pos = detect_head_position(img, video_w=vw, video_h=vh)
                pos = scenes[idx].head_pos
                print(f"  Scene {idx+1}: head auto-detected at {pos}" if pos else f"  Scene {idx+1}: no head detected")
            else:
                print(f"  No image for scene {idx+1}")
        elif len(parts) == 3 and parts[2].lower() == "none":
            scenes[idx].head_pos = None
            print(f"  Scene {idx+1}: head position cleared")
        elif len(parts) == 4:
            try:
                xval, yval = parts[2], parts[3]
                hx = int(float(xval.rstrip("%")) / 100 * vw) if xval.endswith("%") else int(xval)
                hy = int(float(yval.rstrip("%")) / 100 * vh) if yval.endswith("%") else int(yval)
                scenes[idx].head_pos = (max(0, min(hx, vw)), max(0, min(hy, vh)))
                print(f"  Scene {idx+1}: head set to {scenes[idx].head_pos}")
            except (ValueError, IndexError):
                print("  Usage: head 3 540 300  or  head 3 50% 15%")
        else:
            print("  Usage: head 3 [x y | auto | none]")

    def _cmd_regenerate(indices: List[int]) -> None:
        from ..imagegen import _cache_key, CACHE_IMG_DIR
        for idx in indices:
            if idx < 0 or idx >= len(scenes):
                print(f"  Scene {idx+1} out of range, skipping")
                continue
            scene = scenes[idx]
            scene.head_pos = None
            styled_query = scene.search_query + style_suffix
            print(f"\n   Regenerating scene {idx+1}...")
            cache_k = _cache_key(f"img:{visuals}:{art_style}:{image_category}:{scene.text}:{scene.search_query}")
            for ext in (".png", ".jpg", ".webp"):
                cached = os.path.join(CACHE_IMG_DIR, cache_k + ext)
                if os.path.exists(cached):
                    os.unlink(cached)
                    print("      [Cleared cached image]")

            visual_path = os.path.join(tmp, f"visual_{idx:02d}_regen")
            video_path = os.path.join(tmp, f"scene_video_{idx:02d}.mp4")
            _, img_path = _generate_scene_visual(
                scene, visual_path, video_path, styled_query,
                visuals=visuals, art_style=art_style, image_category=image_category,
                animation=animation, caption_style=caption_style,
                style_suffix=style_suffix, fallback_theme=fallback_theme,
            )
            scene_img_paths[idx] = img_path
            scene_videos[idx] = video_path
            scene_variants[idx] = get_variant_paths(img_path) if img_path else []
            _refresh_preview(idx)
        print("\n   Regeneration complete.")

    while True:
        print("\n" + "=" * 60)
        print("  SCENE IMAGE REVIEW")
        print("=" * 60)
        for i, scene in enumerate(scenes):
            status = "OK" if scene_img_paths[i] else "no img"
            head_label = f"{scene.head_pos[0]},{scene.head_pos[1]}" if scene.head_pos else "none"
            nv = len(scene_variants[i]) if i < len(scene_variants) else 0
            var_label = f"{nv} variants" if nv > 1 else ""
            print(f"  [{i+1}] [{status:6s}] [head: {head_label:10s}] {var_label:12s} \"{scene.text[:40]}\"")
        print("=" * 60)
        print("Commands:")
        print("  2,4              — regenerate scenes 2 and 4")
        print("  open 3           — open scene 3 image in Preview")
        print("  pick 3           — open all variants, click to pick")
        print("  pick 3 2         — use variant 2 for scene 3")
        print("  head 3           — click to tag head position")
        print("  head 3 540 300   — set head position (pixels)")
        print("  head 3 50% 15%   — set head position (percentage)")
        print("  head 3 auto      — re-run auto detection")
        print("  head 3 none      — clear head position")
        print("  done             — continue to render")
        choice = input("> ").strip()
        cl = choice.lower()

        if not cl:
            continue
        if cl in ("done", "d", "ok", "continue", "c"):
            break

        if cl in ("open", "o"):
            subprocess.run(["open", review_dir], capture_output=True)
            continue

        parts = choice.split()
        cmd = parts[0].lower()

        if cmd in ("open", "o") and len(parts) >= 2:
            try:
                _cmd_open(int(parts[1]) - 1)
            except ValueError:
                print("  Usage: open 3")
            continue

        if cmd in ("pick", "p") and len(parts) >= 2:
            try:
                _cmd_pick(int(parts[1]) - 1, parts)
            except ValueError:
                print("  Usage: pick 3 [variant#]")
            continue

        if cmd in ("head", "h") and len(parts) >= 2:
            try:
                _cmd_head(int(parts[1]) - 1, parts)
            except ValueError:
                print("  Usage: head 3 [x y | auto | none]")
            continue

        try:
            indices = [int(x.strip()) - 1 for x in cl.split(",")]
            _cmd_regenerate(indices)
        except ValueError:
            print("Invalid input. Type scene numbers (e.g. '2,4'), 'head 3 540 300', or 'done'.")


# ---------------------------------------------------------------------------
# Caption burning
# ---------------------------------------------------------------------------

def _scene_time_windows(scenes: List[Scene]) -> List[Tuple[float, float]]:
    """Return (start, end) time windows per scene, accounting for 0.8s crossfades."""
    xfade = 0.8 if len(scenes) > 1 else 0.0
    cumulative = 0.0
    windows = []
    for i, s in enumerate(scenes):
        s_start = cumulative + (xfade / 2 if i > 0 else 0)
        s_end = cumulative + s.duration - (xfade / 2 if i < len(scenes) - 1 else 0)
        windows.append((s_start, s_end))
        cumulative += s.duration - (xfade if i < len(scenes) - 1 else 0)
    return windows


def _build_bubble_captions(scenes: List[Scene], words: List[Word], caption_animation: str) -> List[BubbleGroup]:
    from ..captions import WORDS_PER_CHUNK
    scene_times = _scene_time_windows(scenes)
    bubble_groups = []

    for scene_idx, (s_start, s_end) in enumerate(scene_times):
        scene_words = [w for w in words if w.start >= s_start and w.end <= s_end]
        if not scene_words:
            continue
        side = "left" if scene_idx % 2 == 0 else "right"
        head = scenes[scene_idx].head_pos if scene_idx < len(scenes) else None

        sub_chunks = []
        for ci in range(0, len(scene_words), WORDS_PER_CHUNK):
            chunk = scene_words[ci:ci + WORDS_PER_CHUNK]
            if not chunk:
                continue

            if caption_animation == "karaoke":
                text = " ".join(w.text for w in chunk)
                start, end = chunk[0].start, chunk[-1].end
                if end > start:
                    sub_chunks.append((text, start, end))

            elif caption_animation == "word":
                for wi in range(len(chunk)):
                    text = " ".join(w.text for w in chunk[:wi + 1])
                    start = chunk[wi].start
                    end = chunk[wi + 1].start if wi + 1 < len(chunk) else chunk[-1].end
                    if end > start:
                        sub_chunks.append((text, start, end))

            else:  # typing
                for wi, word in enumerate(chunk):
                    w_start, w_end = word.start, word.end
                    if w_end <= w_start:
                        continue
                    prev = " ".join(w.text for w in chunk[:wi])
                    n = len(word.text)
                    char_dur = (w_end - w_start) / max(n, 1)
                    for ci2 in range(1, n + 1):
                        partial = word.text[:ci2]
                        text = f"{prev} {partial}".strip() if prev else partial
                        start = w_start + (ci2 - 1) * char_dur
                        end = w_start + ci2 * char_dur if ci2 < n else w_end
                        if end > start:
                            sub_chunks.append((text, start, end))
                if sub_chunks:
                    last = sub_chunks[-1]
                    if last[1] < chunk[-1].end:
                        sub_chunks[-1] = (last[0], last[1], chunk[-1].end)

        if sub_chunks:
            bubble_groups.append(BubbleGroup(
                group_idx=scene_idx, side=side, chunks=sub_chunks,
                group_start=s_start, group_end=s_end, head_pos=head,
            ))

    return bubble_groups


def _build_head_ass(scenes: List[Scene], words: List[Word], scene_img_paths: List[Optional[str]], caption_animation: str, caption_font: str) -> str:
    """Build and return ASS content for head-position captions."""
    from ..captions import (
        _group_words, _build_karaoke, _build_smooth_karaoke,
        _build_word_typing, _build_char_typing,
        FONT_NAME, FONT_SIZE, PRIMARY_COLOR, OUTLINE_COLOR, BACK_COLOR, MARGIN_V, CAPTION_FONTS,
    )
    CAPTION_PADDING = 30
    canvas_w, canvas_h = settings.vertical_width, settings.vertical_height
    font_name = CAPTION_FONTS[caption_font]["ass_name"] if caption_font and caption_font in CAPTION_FONTS else FONT_NAME
    cx = canvas_w // 2
    anim = caption_animation if caption_animation != "karaoke" else "smooth-karaoke"

    for i, scene in enumerate(scenes):
        if scene.head_pos is None and i < len(scene_img_paths) and scene_img_paths[i] and os.path.exists(scene_img_paths[i]):
            scene.head_pos = detect_head_position(scene_img_paths[i], video_w=canvas_w, video_h=canvas_h)

    header = (
        f"[Script Info]\nScriptType: v4.00+\nPlayResX: {canvas_w}\nPlayResY: {canvas_h}\n\n"
        f"[V4+ Styles]\n"
        f"Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        f"Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        f"Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_name},{FONT_SIZE},{PRIMARY_COLOR},{PRIMARY_COLOR},{OUTLINE_COLOR},{BACK_COLOR},"
        f"1,0,0,0,100,100,6,0,1,3,3,2,40,40,{MARGIN_V},1\n\n"
        f"[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = [header]

    for scene_idx, (s_start, s_end) in enumerate(_scene_time_windows(scenes)):
        scene_words = [w for w in words if w.start >= s_start and w.end <= s_end]
        if not scene_words:
            continue
        head_pos = scenes[scene_idx].head_pos if scene_idx < len(scenes) else None
        pos_tag = f"{{\\pos({cx},{head_pos[1] - CAPTION_PADDING})}}" if head_pos else ""

        for chunk in _group_words(scene_words):
            if not chunk:
                continue
            chunk_end_t = chunk[-1].end - s_start
            if chunk_end_t <= 0:
                continue
            if anim == "smooth-karaoke":
                _build_smooth_karaoke(chunk, s_start, chunk_end_t, scene_words, True, lines, pos_tag=pos_tag)
            elif anim == "word":
                _build_word_typing(chunk, s_start, chunk_end_t, scene_words, True, lines, pos_tag=pos_tag)
            elif anim == "typing":
                _build_char_typing(chunk, s_start, chunk_end_t, scene_words, True, lines, pos_tag=pos_tag)
            else:
                _build_karaoke(chunk, s_start, chunk_end_t, scene_words, True, lines, pos_tag=pos_tag)

    return "".join(lines)


def _burn_captions(
    final_path: str,
    scenes: List[Scene],
    scene_img_paths: List[Optional[str]],
    output_dir: str,
    caption_style: str,
    caption_font: str,
    caption_animation: str,
) -> None:
    """Transcribe final video and burn captions in-place."""
    print("\n-> Transcribing final video for word-level captions...")
    try:
        segments = transcribe(final_path)
        words = [w for seg in segments for w in seg.words]
        if not words:
            print("   No words detected, skipping captions")
            return

        captioned = final_path + ".captioned.mp4"

        if caption_style == "bubble":
            bubble_groups = _build_bubble_captions(scenes, words, caption_animation)
            detected = sum(1 for s in scenes if s.head_pos)
            print(f"   Burning {len(bubble_groups)} animated thought bubbles ({detected}/{len(scenes)} faces detected)...")
            burn_thought_bubbles(final_path, captioned, bubble_groups, tmp_dir=output_dir, caption_font=caption_font)

        elif caption_style == "head":
            ass_content = _build_head_ass(scenes, words, scene_img_paths, caption_animation, caption_font)
            ass_path = os.path.join(output_dir, "story_captions_head.ass")
            with open(ass_path, "w", encoding="utf-8") as f:
                f.write(ass_content)
            burn_captions(final_path, ass_path, captioned)
            detected = sum(1 for s in scenes if s.head_pos)
            print(f"   Burned head-position captions ({detected}/{len(scenes)} heads tagged/detected)")

        else:
            ass_path = os.path.join(output_dir, "story_captions.ass")
            build_ass(words, clip_start=0.0, output_path=ass_path, caption_font=caption_font, caption_animation=caption_animation)
            burn_captions(final_path, ass_path, captioned)
            print(f"   Burned {len(words)} word-level captions")

        os.replace(captioned, final_path)

    except Exception as e:
        print(f"   Warning: caption transcription failed ({e}), video saved without captions")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def create_story(
    script: str,
    output_dir: str,
    voice: str = "warm",
    voice_rate: Optional[str] = None,
    music_path: Optional[str] = None,
    music_volume: float = 0.3,
    auto_music: bool = True,
    visuals: str = "download",
    art_style: str = "",
    image_category: str = "",
    animation: str = "ken-burns",
    film_grain: str = "",
    caption_style: str = "default",
    caption_font: str = "",
    caption_animation: str = "karaoke",
    hook_text: str = "",
    review_images: bool = False,
    footnote: str = "",
) -> str:
    """Create a short narrated video from a script. Returns path to the output video."""
    os.makedirs(output_dir, exist_ok=True)
    use_veo_audio = (visuals == "veo")

    print("-> Splitting script into scenes...")
    scenes = _split_into_scenes(script)
    has_timeline = any(s.duration > 0 for s in scenes)
    print(f"   {len(scenes)} scenes identified" + (" (with timeline)" if has_timeline else ""))

    resolved_hook = _resolve_hook(script, hook_text)

    with tempfile.TemporaryDirectory() as tmp:
        if use_veo_audio:
            print("-> Skipping TTS (Veo generates voice + sound effects)...")
            for i, scene in enumerate(scenes):
                if scene.duration <= 0:
                    scene.duration = 8.0
                print(f"   Scene {i+1}: {scene.duration:.1f}s - \"{scene.text[:50]}\"")
            full_narration_path = None
        else:
            print("-> Generating narration audio...")
            full_narration_path = _generate_narration_track(scenes, tmp, voice, voice_rate)

        total_dur = sum(s.duration for s in scenes)
        print(f"   Total duration: {total_dur:.1f}s")

        scene_videos, scene_img_paths, style_suffix, fallback_theme = _generate_all_visuals(
            scenes, tmp,
            visuals=visuals, art_style=art_style, image_category=image_category,
            animation=animation, caption_style=caption_style,
        )

        if review_images and visuals not in ("download", "veo"):
            scene_variants, review_dir = _setup_review(scene_img_paths, output_dir)
            _run_review_loop(
                scenes, scene_img_paths, scene_videos, scene_variants, review_dir, tmp,
                visuals=visuals, art_style=art_style, image_category=image_category,
                animation=animation, caption_style=caption_style,
                style_suffix=style_suffix, fallback_theme=fallback_theme,
            )
            shutil.rmtree(review_dir, ignore_errors=True)

        scene_img_paths = _persist_images(scene_img_paths, output_dir)

        print("\n-> Stitching scenes with transitions...")
        final_path = os.path.join(output_dir, "story_output.mp4")
        visual_concat = os.path.join(tmp, "visual_concat.mp4")

        if use_veo_audio:
            _concat_scenes_with_audio(scene_videos, visual_concat)
            shutil.copy2(visual_concat, final_path)
        else:
            _concat_with_transitions(scene_videos, visual_concat)
            print("-> Merging narration with visuals...")
            _merge_audio_video(visual_concat, full_narration_path, final_path)

    final_path = _add_music(final_path, voice, music_path, music_volume, auto_music)

    if not use_veo_audio:
        _burn_captions(final_path, scenes, scene_img_paths, output_dir, caption_style, caption_font, caption_animation)

    if resolved_hook:
        print("-> Adding hook text overlay to intro...")
        hook_duration = min(scenes[0].duration if scenes else 5.0, 5.0)
        hooked = final_path + ".hooked.mp4"
        add_text_hook(final_path, resolved_hook, hooked, clip_duration=hook_duration, caption_font=caption_font)
        os.replace(hooked, final_path)

    if footnote:
        print("-> Adding footnote to outro...")
        fn_path = final_path + ".footnote.mp4"
        burn_footnote(final_path, fn_path, footnote,
                      video_duration=_get_audio_duration(final_path),
                      outro_duration=scenes[-1].duration if scenes else 5.0,
                      caption_font=caption_font)
        os.replace(fn_path, final_path)

    if film_grain:
        print(f"-> Applying {film_grain} film grain effect...")
        grain_path = final_path + ".grain.mp4"
        add_film_grain(final_path, grain_path, intensity=film_grain)
        os.replace(grain_path, final_path)

    print(f"\n-> Story video saved: {final_path}")
    return final_path


# ---------------------------------------------------------------------------
# Small orchestration helpers used only by create_story
# ---------------------------------------------------------------------------

def _resolve_hook(script: str, hook_text: str) -> str:
    if hook_text == "auto":
        print("-> Generating intro hook text...")
        hook = _generate_hook_text(script)
        if hook:
            print(f'   Hook: "{hook}"')
        else:
            print("   Warning: could not generate hook text")
        return hook
    if hook_text:
        print(f'-> Using custom hook text: "{hook_text}"')
    return hook_text


def _setup_review(scene_img_paths: List[Optional[str]], output_dir: str):
    review_dir = os.path.join(output_dir, "_review")
    os.makedirs(review_dir, exist_ok=True)
    scene_variants = []
    for i, img_path in enumerate(scene_img_paths):
        variants = get_variant_paths(img_path) if img_path else []
        scene_variants.append(variants)
        for vi, vp in enumerate(variants):
            ext = os.path.splitext(vp)[1] or ".png"
            name = f"scene_{i+1:02d}_v{vi+1}{ext}" if len(variants) > 1 else f"scene_{i+1:02d}{ext}"
            shutil.copy2(vp, os.path.join(review_dir, name))
    print(f"\n   Preview images saved to: {review_dir}")
    try:
        subprocess.run(["open", review_dir], capture_output=True)
    except Exception:
        pass
    return scene_variants, review_dir


def _persist_images(scene_img_paths: List[Optional[str]], output_dir: str) -> List[Optional[str]]:
    out = []
    for i, img_path in enumerate(scene_img_paths):
        if img_path and os.path.exists(img_path):
            ext = os.path.splitext(img_path)[1] or ".png"
            dest = os.path.join(output_dir, f"scene_{i:02d}{ext}")
            shutil.copy2(img_path, dest)
            out.append(dest)
        else:
            out.append(None)
    return out


def _add_music(final_path: str, voice: str, music_path: Optional[str], music_volume: float, auto_music: bool) -> str:
    if not music_path and auto_music:
        from ..music import suggest_and_pick_music
        genre = VOICE_MUSIC_MAP.get(voice, "cinematic background")
        print(f"\n-> Auto-searching background music: \"{genre}\"...")
        music_path = suggest_and_pick_music("cinematic", "narrated story", os.path.dirname(final_path), genre=genre)

    if music_path and os.path.exists(music_path):
        from ..render import mix_music
        print("-> Adding background music...")
        music_out = final_path + ".music.mp4"
        mix_music(final_path, music_path, music_out, original_volume=1.0, music_volume=music_volume)
        os.replace(music_out, final_path)

    return final_path
