"""Decompose create_story() into 4 GUI-friendly phases sharing a StorySession."""

import os
import re
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from ...config import settings
from ...narration import (
    POPULAR_VOICES, MOOD_VOICE_SETTINGS,
    generate_narration, generate_silence, is_silent_scene,
    _tts_cache_key, _cache_hit,
)
from ...story import (
    Scene, BubbleGroup, MOOD_PRESETS, VOICE_MUSIC_MAP, ANIMATION_PRESETS,
    _split_into_scenes, _generate_hook_text, _pad_audio_to_duration,
    _concat_audios, _get_audio_duration, _image_to_video,
    _trim_video_to_duration, _concat_with_transitions,
    _concat_scenes_with_audio, _merge_audio_video,
    _download_scene_image, _download_pexels_video,
    _download_youtube_clip, _make_text_card,
)
from ...imagegen import (
    generate_scene_image, generate_scene_video, get_variant_paths,
    ART_STYLES, CATEGORY_STYLES, _cache_key, CACHE_IMG_DIR,
)
from ...render import (
    detect_head_position, burn_captions, burn_thought_bubbles,
    add_text_hook, burn_footnote, add_film_grain, mix_music,
)
from ...transcribe import transcribe
from ...captions import build_ass, WORDS_PER_CHUNK


@dataclass
class StorySession:
    script: str
    output_dir: str
    voice: str = "warm"
    voice_rate: Optional[str] = None
    music_path: Optional[str] = None
    music_volume: float = 0.3
    auto_music: bool = True
    visuals: str = "download"
    art_style: str = ""
    image_category: str = ""
    animation: str = "ken-burns"
    film_grain: str = ""
    caption_style: str = "default"
    caption_font: str = ""
    caption_animation: str = "karaoke"
    hook_text: str = ""
    footnote: str = ""
    output_filename: str = ""  # empty = auto-generated from script
    use_tts_cache: bool = True
    orientation: str = "portrait"  # portrait | landscape | square
    gallery_folder: str = ""          # non-empty only when visuals == "gallery"
    gallery_images: List[str] = field(default_factory=list)  # abs paths found in gallery_folder

    work_dir: str = ""
    scenes: List[Scene] = field(default_factory=list)
    resolved_hook: str = ""
    full_narration_path: Optional[str] = None
    use_veo_audio: bool = False

    scene_img_paths: List[Optional[str]] = field(default_factory=list)
    scene_video_paths: List[str] = field(default_factory=list)
    scene_variants: List[List[str]] = field(default_factory=list)

    _style_suffix: str = ""
    _fallback_theme: List[str] = field(default_factory=lambda: ["cinematic landscape", "moody atmospheric", "dark dramatic"])

    final_video_path: Optional[str] = None


def _resolve_style(session: StorySession):
    _style_map = {
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
    if session.art_style:
        s = ART_STYLES.get(session.art_style)
        if s:
            session._style_suffix = " " + _style_map.get(session.art_style, s["name"].lower())
            session._fallback_theme = [
                f"{_style_map.get(session.art_style, '')} background",
                f"{_style_map.get(session.art_style, '')} scene",
                f"{_style_map.get(session.art_style, '')} mood",
            ]
    elif session.image_category:
        cat = CATEGORY_STYLES.get(session.image_category)
        if cat:
            session._style_suffix = " " + cat["mood"].split()[0]
            session._fallback_theme = [
                f"{cat['mood']} landscape",
                f"{cat['mood']} atmosphere",
                f"{cat['mood']} scene",
            ]


_ORIENTATION_DIMS = {
    "portrait":  (1080, 1920),
    "landscape": (1920, 1080),
    "square":    (1080, 1080),
}


def execute_phase1(session: StorySession):
    """Parse script, generate TTS, build narration track."""
    # Apply orientation — mutates global settings so all downstream code uses correct dims
    w, h = _ORIENTATION_DIMS.get(session.orientation, (1080, 1920))
    settings.vertical_width  = w
    settings.vertical_height = h
    print(f"-> Orientation: {session.orientation} ({w}x{h})")

    os.makedirs(session.output_dir, exist_ok=True)
    session.work_dir = os.path.join(session.output_dir, f"_gui_work_{uuid.uuid4().hex[:8]}")
    os.makedirs(session.work_dir, exist_ok=True)

    print("-> Splitting script into scenes...")
    session.scenes = _split_into_scenes(session.script)
    has_timeline = any(s.duration > 0 for s in session.scenes)
    print(f"   {len(session.scenes)} scenes identified" + (" (with timeline)" if has_timeline else ""))

    session.resolved_hook = ""
    if session.hook_text == "auto":
        print("-> Generating intro hook text...")
        session.resolved_hook = _generate_hook_text(session.script)
        if session.resolved_hook:
            print(f'   Hook: "{session.resolved_hook}"')
    elif session.hook_text:
        session.resolved_hook = session.hook_text

    session.use_veo_audio = (session.visuals == "veo")

    if session.use_veo_audio:
        print("-> Skipping TTS (Veo generates voice + sound effects)...")
        for i, scene in enumerate(session.scenes):
            if scene.duration <= 0:
                scene.duration = 8.0
            print(f"   Scene {i+1}: {scene.duration:.1f}s - \"{scene.text[:50]}\"")
    else:
        print("-> Generating narration audio...")
        voice_name = POPULAR_VOICES.get(session.voice, session.voice)
        if session.voice_rate:
            tts_rate = session.voice_rate
        elif session.voice in ("warm", "caring", "storyteller", "dark", "tension"):
            tts_rate = "-25%"
        else:
            tts_rate = "-15%"
        cache_label = " | Cache: ON" if session.use_tts_cache else " | Cache: OFF (regenerate)"
        print(f"   Voice: {voice_name} | Rate: {tts_rate}{cache_label}")

        for i, scene in enumerate(session.scenes):
            audio_path = os.path.join(session.work_dir, f"scene_{i:02d}.mp3")

            if is_silent_scene(scene.text):
                silent_dur = scene.duration if scene.duration > 0 else 3.0
                generate_silence(audio_path, silent_dur)
                if scene.duration <= 0:
                    scene.duration = silent_dur
                scene.audio_path = audio_path
                print(f"   Scene {i+1}: {scene.duration:.1f}s (silent) - \"{scene.text[:50]}\"")
                continue

            s_voice = voice_name
            s_rate = tts_rate
            s_pitch = "+0Hz"
            s_mood = ""

            if scene.mood and scene.mood in MOOD_VOICE_SETTINGS:
                ms = MOOD_VOICE_SETTINGS[scene.mood]
                s_rate = ms["rate"]
                s_pitch = ms["pitch"]
                s_mood = scene.mood
            elif scene.mood and scene.mood in MOOD_PRESETS:
                preset = MOOD_PRESETS[scene.mood]
                s_rate = preset["rate"]

            if scene.voice:
                s_voice = POPULAR_VOICES.get(scene.voice, scene.voice)
            if scene.rate:
                s_rate = scene.rate

            from_cache = session.use_tts_cache and bool(
                _cache_hit(_tts_cache_key(scene.text, s_voice, s_rate, s_pitch))
            )
            _, scene.timings = generate_narration(
                scene.text, audio_path, voice=s_voice, rate=s_rate, pitch=s_pitch, mood=s_mood,
                use_cache=session.use_tts_cache,
            )
            tts_duration = _get_audio_duration(audio_path)
            if scene.duration <= 0:
                scene.duration = tts_duration + 2.5
            elif scene.duration < tts_duration + 1.5:
                scene.duration = tts_duration + 1.5
            scene.audio_path = audio_path
            cache_tag = " [cache]" if from_cache else ""
            print(f"   Scene {i+1}: {scene.duration:.1f}s (tts: {tts_duration:.1f}s){cache_tag} - \"{scene.text[:50]}\"")

    total_duration = sum(s.duration for s in session.scenes)
    print(f"   Total duration: {total_duration:.1f}s")

    if not session.use_veo_audio:
        print("-> Building timed narration track...")
        padded_audios = []
        for i, scene in enumerate(session.scenes):
            padded_path = os.path.join(session.work_dir, f"padded_{i:02d}.mp3")
            _pad_audio_to_duration(scene.audio_path, scene.duration, padded_path)
            padded_audios.append(padded_path)

        session.full_narration_path = os.path.join(session.output_dir, "narration_full.mp3")
        _concat_audios(padded_audios, session.full_narration_path)

    _resolve_style(session)


def execute_phase2(session: StorySession):
    """Generate/download visuals for each scene."""
    use_ai = session.visuals in ("openai", "sd", "veo")
    if use_ai:
        print(f"\n-> Generating AI visuals ({session.visuals}) for each scene...")
    else:
        print("\n-> Downloading visuals for each scene...")

    session.scene_img_paths = []
    session.scene_video_paths = []
    session.scene_variants = []

    for i, scene in enumerate(session.scenes):
        styled_query = scene.search_query + session._style_suffix
        print(f"   Scene {i+1}/{len(session.scenes)}: \"{styled_query[:60]}\" ({scene.duration:.1f}s)")

        visual_path = os.path.join(session.work_dir, f"visual_{i:02d}")
        video_path = os.path.join(session.work_dir, f"scene_video_{i:02d}.mp4")

        got_visual, img_path = _generate_one_visual(session, i, scene, visual_path, video_path, styled_query)

        session.scene_img_paths.append(img_path)
        session.scene_video_paths.append(video_path)

        if img_path:
            variants = get_variant_paths(img_path)
        else:
            variants = []
        session.scene_variants.append(variants)

    print(f"   Phase 2 complete: {sum(1 for p in session.scene_img_paths if p)}/{len(session.scenes)} scenes have images")


def execute_phase2_gallery(session: StorySession):
    """Populate scene variants from a local image folder instead of generating/downloading."""
    folder = session.gallery_folder.strip()
    if not folder or not os.path.isdir(folder):
        raise ValueError(f"Gallery folder not found: '{folder}'")

    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    images = sorted(
        os.path.abspath(os.path.join(folder, f))
        for f in os.listdir(folder)
        if os.path.splitext(f)[1].lower() in IMAGE_EXTS
    )
    if not images:
        raise ValueError(f"No images found in gallery folder: '{folder}'")

    session.gallery_images = images
    n = len(session.scenes)
    session.scene_img_paths   = [None] * n
    session.scene_video_paths = [""]   * n
    # Every scene gets the full gallery as its variant pool
    session.scene_variants    = [list(images) for _ in range(n)]
    print(f"\n-> Gallery mode: {len(images)} images loaded from '{folder}'")
    print(f"   Pick one image per scene in the wizard step.")


def _generate_one_visual(session, i, scene, visual_path, video_path, styled_query):
    """Generate or download visual for a single scene."""
    got_visual = False
    scene_img_path = None
    use_ai = session.visuals in ("openai", "sd", "veo")

    if use_ai:
        if session.visuals == "veo":
            veo_path = visual_path + "_veo.mp4"
            if generate_scene_video(scene.text, scene.search_query, veo_path,
                                    duration=scene.duration, art_style=session.art_style,
                                    category=session.image_category):
                _trim_video_to_duration(veo_path, scene.duration, video_path)
                got_visual = True
                print(f"      [Veo video generated]")
        else:
            ai_img_path = visual_path + "_ai.png"
            if generate_scene_image(scene.text, scene.search_query, ai_img_path,
                                    provider=session.visuals, art_style=session.art_style,
                                    category=session.image_category):
                if session.caption_style == "bubble":
                    scene.head_pos = detect_head_position(
                        ai_img_path, video_w=settings.vertical_width, video_h=settings.vertical_height,
                    )
                    if scene.head_pos:
                        print(f"      [Face detected at {scene.head_pos}]")
                scene_img_path = ai_img_path
                _image_to_video(ai_img_path, scene.duration, video_path, animation=session.animation)
                got_visual = True
                print(f"      [AI illustration generated]")

    if not got_visual and scene.visual_type == "video":
        pexels_path = visual_path + "_pexels.mp4"
        if _download_pexels_video(styled_query, pexels_path):
            from ...render import reframe_vertical
            reframed = visual_path + "_reframed.mp4"
            reframe_vertical(pexels_path, reframed, mode="crop")
            _trim_video_to_duration(reframed, scene.duration, video_path)
            got_visual = True

        if not got_visual:
            yt_path = visual_path + "_yt.mp4"
            if _download_youtube_clip(styled_query + " stock footage", yt_path):
                from ...render import reframe_vertical
                reframed = visual_path + "_reframed.mp4"
                reframe_vertical(yt_path, reframed, mode="crop")
                _trim_video_to_duration(reframed, scene.duration, video_path)
                got_visual = True

    if not got_visual:
        img_path = visual_path + ".jpg"
        if _download_scene_image(styled_query, img_path):
            if session.caption_style == "bubble" and not scene.head_pos:
                scene.head_pos = detect_head_position(
                    img_path, video_w=settings.vertical_width, video_h=settings.vertical_height,
                )
            scene_img_path = img_path
            _image_to_video(img_path, scene.duration, video_path, animation=session.animation)
            got_visual = True

    if not got_visual:
        fallback_img = visual_path + "_fb.jpg"
        words = scene.search_query.split()
        fallback_queries = []
        if len(words) > 2:
            fallback_queries.append(" ".join(words[:2]) + session._style_suffix)
        fallback_queries.extend(session._fallback_theme)
        for fq in fallback_queries:
            if _download_scene_image(fq, fallback_img):
                scene_img_path = fallback_img
                _image_to_video(fallback_img, scene.duration, video_path, animation=session.animation)
                got_visual = True
                break

    if not got_visual:
        _make_text_card(scene.text[:80], scene.duration, video_path)

    return got_visual, scene_img_path


def regenerate_scene(session: StorySession, idx: int):
    """Regenerate visual for a single scene. Returns updated variants."""
    scene = session.scenes[idx]
    scene.head_pos = None
    styled_query = scene.search_query + session._style_suffix

    print(f"   Regenerating scene {idx+1}...")

    cache_k = _cache_key(f"img:{session.visuals}:{session.art_style}:{session.image_category}:{scene.text}:{scene.search_query}")
    for ext in (".png", ".jpg", ".webp"):
        cached = os.path.join(CACHE_IMG_DIR, cache_k + ext)
        if os.path.exists(cached):
            os.unlink(cached)
            print(f"      [Cleared cached image]")

    visual_path = os.path.join(session.work_dir, f"visual_{idx:02d}_regen_{uuid.uuid4().hex[:4]}")
    video_path = os.path.join(session.work_dir, f"scene_video_{idx:02d}.mp4")

    got_visual, img_path = _generate_one_visual(session, idx, scene, visual_path, video_path, styled_query)
    session.scene_img_paths[idx] = img_path
    session.scene_video_paths[idx] = video_path

    if img_path:
        variants = get_variant_paths(img_path)
    else:
        variants = []
    session.scene_variants[idx] = variants
    return variants


def pick_variant(session: StorySession, scene_idx: int, variant_idx: int):
    """Select a specific variant for a scene."""
    variants = session.scene_variants[scene_idx]
    if variant_idx < 0 or variant_idx >= len(variants):
        return
    chosen = variants[variant_idx]
    session.scene_img_paths[scene_idx] = chosen
    scene = session.scenes[scene_idx]
    scene.head_pos = None

    video_path = os.path.join(session.work_dir, f"scene_video_{scene_idx:02d}.mp4")
    _image_to_video(chosen, scene.duration, video_path, animation=session.animation)
    session.scene_video_paths[scene_idx] = video_path

    if session.caption_style == "bubble":
        scene.head_pos = detect_head_position(
            chosen, video_w=settings.vertical_width, video_h=settings.vertical_height,
        )


def _resolve_output_filename(session: StorySession) -> str:
    if session.output_filename.strip():
        name = session.output_filename.strip()
        if not name.lower().endswith(".mp4"):
            name += ".mp4"
        return os.path.join(session.output_dir, name)
    # Auto: first non-empty, non-tag line of script + timestamp
    first_line = ""
    for line in session.script.splitlines():
        cleaned = re.sub(r"\[.*?\]|#.*", "", line).strip()
        if cleaned:
            first_line = cleaned[:40]
            break
    slug = re.sub(r"[^\w\s-]", "", first_line).strip()
    slug = re.sub(r"[\s]+", "_", slug).lower() or "story"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(session.output_dir, f"{slug}_{ts}.mp4")


def execute_phase4(session: StorySession) -> str:
    """Stitch scenes, merge audio, burn captions, apply effects. Returns final path."""
    print("\n-> Stitching scenes with transitions...")
    final_path = _resolve_output_filename(session)
    print(f"   Output: {os.path.basename(final_path)}")

    if session.use_veo_audio:
        visual_concat = os.path.join(session.work_dir, "visual_concat.mp4")
        _concat_scenes_with_audio(session.scene_video_paths, visual_concat)
        shutil.copy2(visual_concat, final_path)
    else:
        visual_concat = os.path.join(session.work_dir, "visual_concat.mp4")
        _concat_with_transitions(session.scene_video_paths, visual_concat)
        print("-> Merging narration with visuals...")
        _merge_audio_video(visual_concat, session.full_narration_path, final_path)

    # Music is applied if already resolved (via GUI picker or uploaded file)
    music_path = session.music_path

    if music_path and os.path.exists(music_path):
        print("-> Adding background music...")
        music_out = final_path + ".music.mp4"
        mix_music(final_path, music_path, music_out,
                  original_volume=1.0, music_volume=session.music_volume)
        os.replace(music_out, final_path)

    # Captions
    if not session.use_veo_audio:
        print("\n-> Transcribing final video for word-level captions...")
        try:
            segments = transcribe(final_path)
            words = [w for seg in segments for w in seg.words]
            if words:
                if session.caption_style == "bubble":
                    _burn_bubble_captions(session, final_path, words)
                else:
                    ass_path = os.path.join(session.output_dir, "story_captions.ass")
                    build_ass(words, clip_start=0.0, output_path=ass_path,
                              caption_font=session.caption_font,
                              caption_animation=session.caption_animation)
                    captioned_path = final_path + ".captioned.mp4"
                    burn_captions(final_path, ass_path, captioned_path)
                    os.replace(captioned_path, final_path)
                    print(f"   Burned {len(words)} word-level captions")
            else:
                print("   No words detected, skipping captions")
        except Exception as e:
            print(f"   Warning: caption transcription failed ({e})")

    # Hook text
    if session.resolved_hook:
        print(f"-> Adding hook text overlay...")
        hook_duration = min(session.scenes[0].duration if session.scenes else 5.0, 5.0)
        hooked_path = final_path + ".hooked.mp4"
        add_text_hook(final_path, session.resolved_hook, hooked_path,
                      clip_duration=hook_duration, caption_font=session.caption_font)
        os.replace(hooked_path, final_path)

    # Footnote
    if session.footnote:
        print(f"-> Adding footnote to outro...")
        total_dur = _get_audio_duration(final_path)
        outro_dur = session.scenes[-1].duration if session.scenes else 5.0
        fn_path = final_path + ".footnote.mp4"
        burn_footnote(final_path, fn_path, session.footnote,
                      video_duration=total_dur, outro_duration=outro_dur,
                      caption_font=session.caption_font)
        os.replace(fn_path, final_path)

    # Film grain
    if session.film_grain:
        print(f"-> Applying {session.film_grain} film grain...")
        grain_path = final_path + ".grain.mp4"
        add_film_grain(final_path, grain_path, intensity=session.film_grain)
        os.replace(grain_path, final_path)

    # Cleanup work dir
    shutil.rmtree(session.work_dir, ignore_errors=True)

    session.final_video_path = final_path
    print(f"\n-> Story video saved: {final_path}")
    return final_path


def _burn_bubble_captions(session: StorySession, final_path: str, words):
    scenes = session.scenes
    head_positions = [s.head_pos for s in scenes]
    xfade_dur = 0.8 if len(scenes) > 1 else 0.0
    cumulative = 0.0
    scene_times = []
    for i, s in enumerate(scenes):
        s_start = cumulative
        s_end = cumulative + s.duration
        if i > 0:
            s_start += xfade_dur / 2
        if i < len(scenes) - 1:
            s_end -= xfade_dur / 2
        scene_times.append((s_start, s_end))
        cumulative += s.duration
        if i < len(scenes) - 1:
            cumulative -= xfade_dur

    bubble_groups = []
    for scene_idx, (s_start, s_end) in enumerate(scene_times):
        scene_words = [w for w in words if w.start >= s_start and w.end <= s_end]
        if not scene_words:
            continue
        side = "left" if scene_idx % 2 == 0 else "right"
        head = head_positions[scene_idx] if scene_idx < len(head_positions) else None

        sub_chunks = []
        for ci in range(0, len(scene_words), WORDS_PER_CHUNK):
            chunk = scene_words[ci:ci + WORDS_PER_CHUNK]
            if not chunk:
                continue

            if session.caption_animation == "karaoke":
                text = " ".join(w.text for w in chunk)
                start = chunk[0].start
                end = chunk[-1].end
                if end > start:
                    sub_chunks.append((text, start, end))
            elif session.caption_animation == "word":
                for word_idx in range(len(chunk)):
                    text = " ".join(w.text for w in chunk[:word_idx + 1])
                    start = chunk[word_idx].start
                    end = chunk[word_idx + 1].start if word_idx + 1 < len(chunk) else chunk[-1].end
                    if end > start:
                        sub_chunks.append((text, start, end))
            else:
                for word_idx, word in enumerate(chunk):
                    w_start = word.start
                    w_end = word.end
                    if w_end <= w_start:
                        continue
                    prev_text = " ".join(w.text for w in chunk[:word_idx])
                    cur_word = word.text
                    n_chars = len(cur_word)
                    char_dur = (w_end - w_start) / max(n_chars, 1)
                    for char_i in range(1, n_chars + 1):
                        partial = cur_word[:char_i]
                        parts = [prev_text, partial] if prev_text else [partial]
                        text = " ".join(parts)
                        start = w_start + (char_i - 1) * char_dur
                        end = w_start + char_i * char_dur if char_i < n_chars else w_end
                        if end > start:
                            sub_chunks.append((text, start, end))
                if sub_chunks:
                    chunk_end = chunk[-1].end
                    last_text, last_start, last_end = sub_chunks[-1]
                    if last_start < chunk_end:
                        sub_chunks[-1] = (last_text, last_start, chunk_end)

        if sub_chunks:
            bubble_groups.append(BubbleGroup(
                group_idx=scene_idx, side=side, chunks=sub_chunks,
                group_start=s_start, group_end=s_end, head_pos=head,
            ))

    detected = sum(1 for h in head_positions if h)
    print(f"   Burning {len(bubble_groups)} thought bubbles ({detected}/{len(scenes)} faces detected)...")
    captioned_path = final_path + ".captioned.mp4"
    burn_thought_bubbles(
        final_path, captioned_path, bubble_groups,
        tmp_dir=session.output_dir, caption_font=session.caption_font,
    )
    os.replace(captioned_path, final_path)
