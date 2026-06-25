import argparse
import os
import subprocess
import tempfile
from typing import List, Optional

from .config import settings
from .download import download_youtube
from .transcribe import transcribe, Word
from .clip_selector import select_clips, ClipCandidate
from .captions import build_ass
from .render import cut_clip, reframe_vertical, burn_captions, add_text_hook, add_emoji_overlay, mix_music, mix_sfx, generate_crowd_roar, generate_sfx, FFMPEG
from .music import suggest_and_pick_music
from .narration import generate_narration, mix_narration, POPULAR_VOICES
from .translate import translate_words
from .upload import upload_to_youtube, _generate_clip_metadata, _generate_story_metadata
from .enhance import enhance_clip


def _fmt_timestamp(seconds: float) -> str:
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m:02d}:{s:05.2f}"


def _show_candidates(candidates: List[ClipCandidate], segments) -> None:
    """Display clip candidates with timestamps, transcript preview, and audio info."""
    print("\n" + "=" * 70)
    print("  CLIP CANDIDATES (sorted by virality score)")
    print("=" * 70)
    for i, clip in enumerate(candidates, start=1):
        duration = clip.end - clip.start
        # Get transcript text for this clip's time range
        clip_words = []
        for seg in segments:
            for w in seg.words:
                if clip.start <= w.start <= clip.end:
                    clip_words.append(w.text)
        transcript_preview = " ".join(clip_words)
        if len(transcript_preview) > 150:
            transcript_preview = transcript_preview[:147] + "..."

        print(f"  [{i}] {clip.emoji} {clip.title}")
        print(f"      ⏱  {_fmt_timestamp(clip.start)} → {_fmt_timestamp(clip.end)}  ({duration:.0f}s)")
        print(f"      📊 category: {clip.category} | score: {clip.score}/100")
        print(f"      🪝 hook: \"{clip.hook_text}\"")
        print(f"      💡 {clip.reason}")
        if transcript_preview:
            print(f"      💬 \"{transcript_preview}\"")
        print()
    print("=" * 70)


def _interactive_select(candidates: List[ClipCandidate], segments) -> List[ClipCandidate]:
    """Display clip candidates and let the user pick which ones to render."""
    _show_candidates(candidates, segments)
    print("Enter clip numbers to render (e.g. '1,3,5' or 'all'):")
    choice = input("> ").strip().lower()

    if choice == "all" or choice == "":
        return candidates

    try:
        indices = [int(x.strip()) - 1 for x in choice.split(",")]
        selected = [candidates[i] for i in indices if 0 <= i < len(candidates)]
        if not selected:
            print("No valid selections. Using all clips.")
            return candidates
        return selected
    except (ValueError, IndexError):
        print("Invalid input. Using all clips.")
        return candidates


def _interactive_upload_select(video_paths: List[str]) -> List[int]:
    """Show rendered videos and let the user pick which ones to upload."""
    print("\n" + "=" * 60)
    print("RENDERED VIDEOS")
    print("=" * 60)
    for i, path in enumerate(video_paths, start=1):
        size_mb = os.path.getsize(path) / 1024 / 1024
        print(f"  [{i}] {os.path.basename(path)}  ({size_mb:.1f} MB)")
    print("=" * 60)
    print("Which videos to upload? (e.g. '1,3' or 'all' or 'none'):")
    choice = input("> ").strip().lower()

    if choice in ("none", "n", "0"):
        return []
    if choice in ("all", "a", ""):
        return list(range(len(video_paths)))

    try:
        indices = [int(x.strip()) - 1 for x in choice.split(",")]
        return [i for i in indices if 0 <= i < len(video_paths)]
    except ValueError:
        print("Invalid input. Skipping upload.")
        return []


def _concat_montage(clip_paths: List[str], output_path: str, transition: str = "xfade") -> None:
    """Concatenate rendered clips into one montage with crossfade transitions."""
    if len(clip_paths) == 1:
        import shutil
        shutil.copy2(clip_paths[0], output_path)
        return

    if transition == "xfade":
        _concat_xfade(clip_paths, output_path)
    else:
        _concat_simple(clip_paths, output_path)


def _concat_simple(clip_paths: List[str], output_path: str) -> None:
    """Simple concatenation without transitions (fallback)."""
    list_file = output_path + ".txt"
    with open(list_file, "w") as f:
        for path in clip_paths:
            f.write(f"file '{os.path.abspath(path)}'\n")
    cmd = [
        FFMPEG, "-y", "-f", "concat", "-safe", "0",
        "-i", list_file, "-c", "copy", output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    os.unlink(list_file)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg concat failed:\n{result.stderr[-2000:]}")


def _concat_xfade(clip_paths: List[str], output_path: str, fade_duration: float = 0.5) -> None:
    """Concatenate clips with crossfade video transitions and audio crossfade."""
    if len(clip_paths) == 2:
        # Simple two-clip xfade
        duration_cmd = [
            FFMPEG, "-i", clip_paths[0], "-f", "null", "-"
        ]
        result = subprocess.run(duration_cmd, capture_output=True, text=True)
        # Parse duration from stderr
        dur = _get_duration(clip_paths[0])
        offset = max(0, dur - fade_duration)

        filter_v = f"[0:v][1:v]xfade=transition=fade:duration={fade_duration}:offset={offset}"
        filter_a = f"[0:a][1:a]acrossfade=d={fade_duration}"
        cmd = [
            FFMPEG, "-y",
            "-i", clip_paths[0], "-i", clip_paths[1],
            "-filter_complex", f"{filter_v}[v];{filter_a}[a]",
            "-map", "[v]", "-map", "[a]",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            _concat_simple(clip_paths, output_path)
        return

    # For 3+ clips, chain xfade filters
    inputs = []
    for path in clip_paths:
        inputs += ["-i", path]

    durations = [_get_duration(p) for p in clip_paths]
    offsets = []
    cumulative = 0.0
    for i, dur in enumerate(durations[:-1]):
        cumulative += dur - fade_duration
        offsets.append(cumulative)

    # Build video filter chain
    n = len(clip_paths)
    vfilter_parts = []
    afilter_parts = []

    # First xfade
    vfilter_parts.append(
        f"[0:v][1:v]xfade=transition=fade:duration={fade_duration}:offset={offsets[0]:.3f}[v1]"
    )
    afilter_parts.append(
        f"[0:a][1:a]acrossfade=d={fade_duration}[a1]"
    )

    for i in range(2, n):
        prev_v = f"[v{i-1}]"
        prev_a = f"[a{i-1}]"
        out_v = f"[v{i}]" if i < n - 1 else "[v]"
        out_a = f"[a{i}]" if i < n - 1 else "[a]"
        vfilter_parts.append(
            f"{prev_v}[{i}:v]xfade=transition=fade:duration={fade_duration}:offset={offsets[i-1]:.3f}{out_v}"
        )
        afilter_parts.append(
            f"{prev_a}[{i}:a]acrossfade=d={fade_duration}{out_a}"
        )

    # If only 2 clips, output labels are already [v1] and [a1]
    if n == 2:
        map_v, map_a = "[v1]", "[a1]"
    else:
        map_v, map_a = "[v]", "[a]"

    filter_complex = ";".join(vfilter_parts + afilter_parts)
    cmd = [FFMPEG, "-y"] + inputs + [
        "-filter_complex", filter_complex,
        "-map", map_v, "-map", map_a,
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Fallback to simple concat if xfade fails
        print("   xfade failed, falling back to simple concat...")
        _concat_simple(clip_paths, output_path)


def _get_duration(path: str) -> float:
    """Get video duration in seconds using ffprobe."""
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


def _trim_source(input_path: str, start: float, end: float, output_path: str) -> None:
    cmd = [FFMPEG, "-y", "-ss", str(start), "-i", input_path]
    if end is not None:
        cmd += ["-t", str(end - start)]
    cmd += ["-c", "copy", "-avoid_negative_ts", "make_zero", output_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg trim failed:\n{result.stderr[-2000:]}")


def process_video(
    input_path: str,
    num_clips: int,
    output_dir: str,
    start: Optional[float] = None,
    end: Optional[float] = None,
    reframe: str = "crop",
    emoji: bool = False,
    user_prompt: str = "",
    video_category: str = "auto",
    interactive: bool = False,
    montage: bool = False,
    max_duration: Optional[float] = None,
    narration: Optional[str] = None,
    narration_voice: str = "male-en",
    narration_vol: float = 1.0,
    music: Optional[str] = None,
    music_ai: bool = False,
    music_vol: float = 0.05,
    music_level: float = 1.0,
    music_genre: Optional[str] = None,
    translate: Optional[str] = None,
    sfx: Optional[str] = None,
    sfx_vol: float = 0.6,
    enhance: bool = False,
    enhance_prompt: str = "",
    upload: bool = False,
    upload_privacy: str = "private",
) -> None:
    os.makedirs(output_dir, exist_ok=True)

    if start is not None or end is not None:
        trim_start = start or 0
        trim_end = end
        label = f"{trim_start:.0f}s"
        label += f"-{trim_end:.0f}s" if trim_end else "-end"
        print(f"-> Trimming source to {label}...")
        trimmed_path = os.path.join(output_dir, "trimmed_source.mp4")
        _trim_source(input_path, trim_start, trim_end, trimmed_path)
        input_path = trimmed_path

    print("-> Transcribing (this can take a while for long videos)...")
    segments = transcribe(input_path)

    print(f"-> Asking LLM to find the best {num_clips} moments...")
    if video_category != "auto":
        print(f"   video category: {video_category}")
    if user_prompt:
        print(f"   with guidance: \"{user_prompt}\"")
    candidates = select_clips(segments, num_clips=num_clips, user_prompt=user_prompt, video_category=video_category, video_path=input_path)

    if not candidates:
        print("No clips were selected. Try a longer or more eventful source video.")
        return

    # Always show what the LLM found
    _show_candidates(candidates, segments)

    if interactive:
        print("Enter clip numbers to render (e.g. '1,3,5' or 'all'):")
        choice = input("> ").strip().lower()

        if choice in ("all", "a", ""):
            pass  # render all
        else:
            try:
                indices = [int(x.strip()) - 1 for x in choice.split(",")]
                selected = [candidates[i] for i in indices if 0 <= i < len(candidates)]
                if selected:
                    candidates = selected
                else:
                    print("No valid selections. Using all clips.")
            except (ValueError, IndexError):
                print("Invalid input. Using all clips.")

        if not candidates:
            print("No clips selected. Exiting.")
            return

    print(f"\n-> Rendering {len(candidates)} clip(s)...\n")

    if max_duration:
        for clip in candidates:
            duration = clip.end - clip.start
            if duration > max_duration:
                clip.end = clip.start + max_duration

    if music_ai and not music:
        top_clip = candidates[0]
        music_path = suggest_and_pick_music(top_clip.category, top_clip.title, output_dir, genre=music_genre)
        if music_path:
            music = music_path

    if montage:
        montage_tmp = tempfile.mkdtemp()

    rendered_paths: List[str] = []

    for i, clip in enumerate(candidates, start=1):
        print(f"-> Rendering clip {i}/{len(candidates)}: {clip.title} (score {clip.score})")
        with tempfile.TemporaryDirectory() as tmp:
            cut_path = os.path.join(tmp, "cut.mp4")
            vertical_path = os.path.join(tmp, "vertical.mp4")
            ass_path = os.path.join(tmp, "captions.ass")
            captioned_path = os.path.join(tmp, "captioned.mp4")
            hooked_path = os.path.join(tmp, "hooked.mp4")

            if montage:
                final_path = os.path.join(montage_tmp, f"part_{i:02d}.mp4")
            else:
                final_path = os.path.join(
                    output_dir, f"clip_{i:02d}_{clip.category}_{clip.score}.mp4"
                )

            cut_clip(input_path, clip.start, clip.end, cut_path)
            reframe_vertical(cut_path, vertical_path, mode=reframe)

            clip_words = [
                Word(w.text, w.start, w.end)
                for seg in segments
                for w in seg.words
                if clip.start <= w.start <= clip.end
            ]
            if translate:
                clip_words = translate_words(clip_words, translate)
            clip_duration = clip.end - clip.start
            build_ass(clip_words, clip.start, ass_path)
            burn_captions(vertical_path, ass_path, captioned_path)
            add_text_hook(captioned_path, clip.hook_text, hooked_path,
                          clip_duration=clip_duration)

            if emoji:
                add_emoji_overlay(hooked_path, clip.emoji, clip_duration, final_path)
            else:
                os.rename(hooked_path, final_path)

            if music:
                music_out = final_path + ".music.mp4"
                mix_music(final_path, music, music_out, original_volume=music_vol, music_volume=music_level)
                os.replace(music_out, final_path)

            if narration:
                voice = POPULAR_VOICES.get(narration_voice, narration_voice)
                narr_audio = final_path + ".narr.mp3"
                generate_narration(narration, narr_audio, voice=voice)
                narr_out = final_path + ".narr.mp4"
                orig_vol = 0.3 if not music else 1.0
                mix_narration(final_path, narr_audio, narr_out,
                              original_volume=orig_vol, narration_volume=narration_vol)
                os.replace(narr_out, final_path)
                os.unlink(narr_audio)

            if sfx:
                import tempfile as _tmpmod
                sfx_audio = final_path + ".sfx.m4a"
                if sfx == "crowd":
                    print(f"   Adding crowd roar SFX...")
                    generate_crowd_roar(sfx_audio, clip_duration)
                else:
                    print(f"   Adding {sfx} SFX...")
                    generate_sfx(sfx_audio, sfx)
                sfx_out = final_path + ".sfx.mp4"
                mix_sfx(final_path, sfx_audio, sfx_out, offset=0.0, volume=sfx_vol)
                os.replace(sfx_out, final_path)
                os.unlink(sfx_audio)

            if enhance:
                clip_transcript = "\n".join(
                    f"[{w.start - clip.start:.1f}s] {w.text}"
                    for seg in segments for w in seg.words
                    if clip.start <= w.start <= clip.end
                )
                enhanced_path = final_path + ".enhanced.mp4"
                print(f"   Enhancing clip...")
                enhance_clip(
                    final_path, enhanced_path,
                    title=clip.title,
                    category=clip.category,
                    hook_text=clip.hook_text,
                    score=clip.score,
                    reason=clip.reason,
                    transcript=clip_transcript,
                    user_prompt=enhance_prompt,
                )
                os.replace(enhanced_path, final_path)

        rendered_paths.append(final_path)
        if not montage:
            print(f"   saved -> {final_path}")
        print(f"   reason: {clip.reason}")

    if montage:
        montage_path = os.path.join(output_dir, "montage_best_moments.mp4")
        print(f"\n-> Stitching {len(rendered_paths)} clips into one montage...")
        _concat_montage(rendered_paths, montage_path)
        import shutil
        shutil.rmtree(montage_tmp, ignore_errors=True)
        print(f"   saved -> {montage_path}")

    if upload:
        all_upload_paths = []
        all_upload_clips = []
        if montage:
            all_upload_paths.append(montage_path)
            all_upload_clips.append(None)
        for clip, path in zip(candidates, rendered_paths):
            all_upload_paths.append(path)
            all_upload_clips.append(clip)

        selected = _interactive_upload_select(all_upload_paths)
        if not selected:
            print("   No videos selected for upload.")
            return

        for idx in selected:
            path = all_upload_paths[idx]
            clip = all_upload_clips[idx]

            print(f"\n-> Generating optimized YouTube metadata with AI...")
            if clip is None:
                combined_context = " | ".join(
                    f"{c.title} ({c.category}, score {c.score}): {c.reason}" for c in candidates
                )
                meta = _generate_clip_metadata(
                    title="Best Moments Highlights",
                    category="montage",
                    hook_text=candidates[0].hook_text if candidates else "",
                    reason=combined_context,
                    emoji=candidates[0].emoji if candidates else "",
                    score=max(c.score for c in candidates) if candidates else 90,
                )
            else:
                transcript_snippet = " ".join(
                    w.text for seg in segments for w in seg.words
                    if clip.start <= w.start <= clip.end
                )[:300]
                meta = _generate_clip_metadata(
                    title=clip.title,
                    category=clip.category,
                    hook_text=clip.hook_text,
                    reason=clip.reason,
                    emoji=clip.emoji,
                    score=clip.score,
                    transcript_snippet=transcript_snippet,
                )

            print(f"-> Uploading {os.path.basename(path)} to YouTube Shorts...")
            upload_to_youtube(
                path,
                title=meta["title"],
                description=meta["description"],
                tags=meta["tags"],
                privacy=upload_privacy,
            )


def main():
    parser = argparse.ArgumentParser(
        description="Turn a long video into short, captioned, vertical clips — or create a narrated story video."
    )
    subparsers = parser.add_subparsers(dest="command")

    # ── clip command (default) ───────────────────────────────────────────────
    clip_parser = subparsers.add_parser("clip", help="Extract clips from a long video")
    clip_parser.add_argument("--input", help="Path to local source video file")
    clip_parser.add_argument("--youtube-url", help="YouTube URL to download and process instead of --input")
    clip_parser.add_argument("--num-clips", type=int, default=5)
    clip_parser.add_argument("--output-dir", default=settings.output_dir)
    clip_parser.add_argument("--start", type=float, default=None,
                             help="Start time in seconds (e.g. 120 for 2:00)")
    clip_parser.add_argument("--end", type=float, default=None,
                             help="End time in seconds (e.g. 600 for 10:00)")
    clip_parser.add_argument("--reframe", choices=["crop", "blur"], default="crop",
                             help="crop: center-crop to 9:16. blur: full video with blurred background (default: crop)")
    clip_parser.add_argument("--emoji", action="store_true",
                             help="Add emoji pop-in animation at the punchline moment")
    clip_parser.add_argument("--prompt", type=str, default="",
                             help="Custom prompt to guide clip selection (e.g. 'find funny moments about food')")
    clip_parser.add_argument("--category", type=str, default="auto",
                             choices=["auto", "sports", "comedy", "reaction", "podcast", "gaming",
                                      "music", "educational", "drama", "news", "vlog", "fitness",
                                      "cooking", "asmr"],
                             help="Video category for smarter clip selection (default: auto-detect)")
    clip_parser.add_argument("--interactive", "-i", action="store_true",
                             help="Interactively select which clips to render after LLM suggests them")
    clip_parser.add_argument("--clip-min", type=int, default=None,
                             help=f"Min clip duration for selection in seconds (default: {settings.clip_min_seconds} from .env)")
    clip_parser.add_argument("--clip-max", type=int, default=None,
                             help=f"Max clip duration for selection in seconds (default: {settings.clip_max_seconds} from .env)")
    clip_parser.add_argument("--max-duration", type=float, default=None,
                             help="Max clip duration in seconds (e.g. 60)")
    clip_parser.add_argument("--montage", action="store_true",
                             help="Stitch all rendered clips into one highlights montage with transitions")
    clip_parser.add_argument("--narration", type=str, default=None,
                             help="Text to narrate over the clip using TTS")
    clip_parser.add_argument("--narration-voice", type=str, default="male-en",
                             help="TTS voice (shortcuts: male-en, female-en, male-id, female-id, tiktok)")
    clip_parser.add_argument("--narration-vol", type=float, default=1.0,
                             help="Narration volume (0.0-1.0, default: 1.0)")
    clip_parser.add_argument("--music", type=str, default=None,
                             help="Path to music file to mix over clips")
    clip_parser.add_argument("--music-ai", action="store_true",
                             help="Let AI suggest background music based on clip mood")
    clip_parser.add_argument("--music-genre", type=str, default=None,
                             help="Music genre/style to search for (e.g. 'lofi', 'epic', 'trap', 'acoustic')")
    clip_parser.add_argument("--music-vol", type=float, default=0.05,
                             help="Original audio volume when music is mixed (0.0-1.0, default: 0.05 = 5%%)")
    clip_parser.add_argument("--music-level", type=float, default=1.0,
                             help="Background music volume (0.0-1.0, default: 1.0 = 100%%)")
    clip_parser.add_argument("--sfx", type=str, default=None,
                             choices=["crowd", "whoosh", "impact", "rise", "drop", "whistle", "horn", "buzzer"],
                             help="Add sound effect to all clips (crowd roar, whoosh, impact, etc.)")
    clip_parser.add_argument("--sfx-vol", type=float, default=0.6,
                             help="Sound effect volume (0.0-1.0, default: 0.6)")
    clip_parser.add_argument("--enhance", action="store_true",
                             help="AI-enhance clips after rendering (text overlays, zoom, transitions, pacing)")
    clip_parser.add_argument("--enhance-prompt", type=str, default="",
                             help="Custom instructions for clip enhancement (e.g. 'add dramatic zoom on punchlines')")
    clip_parser.add_argument("--upload", action="store_true",
                             help="Upload rendered clips to YouTube Shorts after rendering")
    clip_parser.add_argument("--upload-privacy", choices=["private", "unlisted", "public"],
                             default="private",
                             help="YouTube upload visibility (default: private)")

    # ── story command ────────────────────────────────────────────────────────
    story_parser = subparsers.add_parser("story", help="Create a narrated video from a script")
    story_parser.add_argument("--script", type=str, required=True,
                              help="Narration script text (or path to .txt file)")
    story_parser.add_argument("--voice", type=str, default="warm",
                              help="TTS voice (dramatic, tension, warm, storyteller, caring, tiktok, etc.)")
    story_parser.add_argument("--voice-rate", type=int, default=None,
                              help="TTS speech rate as number: -30 = 30%% slower, -20 = calm, 0 = normal")
    story_parser.add_argument("--output-dir", default=settings.output_dir)
    story_parser.add_argument("--music", type=str, default=None,
                              help="Path to background music file")
    story_parser.add_argument("--music-ai", action="store_true",
                              help="Let AI suggest background music")
    story_parser.add_argument("--music-genre", type=str, default=None,
                              help="Music genre for AI suggestion")
    story_parser.add_argument("--music-level", type=float, default=0.3,
                              help="Background music volume (0.0-1.0, default: 0.3)")
    story_parser.add_argument("--no-music", action="store_true",
                              help="Disable automatic background music")
    story_parser.add_argument("--visuals", choices=["download", "openai", "sd", "veo"],
                              default="download",
                              help="Visual source: download (stock/YouTube), openai (DALL-E 3), sd (Stable Diffusion local), veo (Google Veo AI video)")
    story_parser.add_argument("--art-style", type=str, default="",
                              choices=["", "pen", "pencil", "watercolor", "anime", "ghibli", "cinematic", "oil",
                                       "comic", "minimal", "pixel", "charcoal", "storybook", "realistic", "stickfigure", "sketch"],
                              help="Art style for AI-generated images (default: auto from category)")
    story_parser.add_argument("--image-category", type=str, default="",
                              choices=["", "meditation", "horror", "fantasy", "romance", "motivational",
                                       "history", "scifi", "nature", "adventure", "comedy", "mystery",
                                       "documentary", "fairytale", "gaming", "zen", "anime"],
                              help="Image category — auto-selects best art style and mood")
    story_parser.add_argument("--animation", type=str, default="ken-burns",
                              choices=["zoom-in", "zoom-out", "pan-left", "pan-right",
                                       "pan-up", "pan-down", "zoom-pan", "ken-burns", "static"],
                              help="Image animation style (default: ken-burns = varies per scene)")
    story_parser.add_argument("--film-grain", type=str, default="",
                              choices=["", "light", "medium", "heavy", "vintage",
                                       "35mm", "gritty", "noise-overlay", "retro"],
                              help="Add film effect: light/medium/heavy grain, vintage, 35mm, gritty, noise-overlay, or retro")
    story_parser.add_argument("--caption-style", type=str, default="default",
                              choices=["default", "bubble"],
                              help="Caption style: default (karaoke text) or bubble (thought bubbles)")
    story_parser.add_argument("--caption-font", type=str, default="",
                              choices=["", "futura", "impact", "arial-black", "georgia",
                                       "trebuchet", "verdana", "din", "chalkduster",
                                       "comic-sans", "times", "croissant-one"],
                              help="Caption font style (default: futura for captions, georgia for bubbles)")
    story_parser.add_argument("--caption-animation", type=str, default="karaoke",
                              choices=["karaoke", "word", "typing"],
                              help="Caption animation: karaoke (highlight active word), word (words appear one by one), typing (character by character)")
    story_parser.add_argument("--hook-text", type=str, default="",
                              help="Add hook/summary text overlay on intro. Use 'auto' for AI-generated, or provide your own text (max 6 words)")
    story_parser.add_argument("--review-images", action="store_true",
                              help="Review generated images and regenerate specific scenes before rendering")
    story_parser.add_argument("--upload", action="store_true",
                              help="Upload to YouTube Shorts after rendering")
    story_parser.add_argument("--upload-privacy", choices=["private", "unlisted", "public"],
                              default="private",
                              help="YouTube upload visibility (default: private)")

    # ── upload command ──────────────────────────────────────────────────────
    upload_parser = subparsers.add_parser("upload", help="Upload an existing video file to YouTube Shorts")
    upload_parser.add_argument("--input", required=True,
                               help="Path to the video file to upload")
    upload_parser.add_argument("--title", type=str, default=None,
                               help="Video title (if omitted, AI generates one)")
    upload_parser.add_argument("--description", type=str, default=None,
                               help="Video description (if omitted, AI generates one)")
    upload_parser.add_argument("--tags", type=str, default=None,
                               help="Comma-separated tags (if omitted, AI generates them)")
    upload_parser.add_argument("--privacy", choices=["private", "unlisted", "public"],
                               default="private",
                               help="YouTube upload visibility (default: private)")
    upload_parser.add_argument("--no-ai", action="store_true",
                               help="Skip AI metadata generation, use provided title/description/tags only")

    # ── enhance command ─────────────────────────────────────────────────────
    enhance_parser = subparsers.add_parser("enhance", help="AI-enhance an existing rendered video")
    enhance_parser.add_argument("--input", required=True,
                                help="Path to the video file to enhance")
    enhance_parser.add_argument("--output", type=str, default=None,
                                help="Output path (default: <input>_enhanced.mp4)")
    enhance_parser.add_argument("--title", type=str, default="",
                                help="Clip title (helps AI understand context)")
    enhance_parser.add_argument("--prompt", type=str, default="",
                                help="Custom enhancement instructions (e.g. 'add zoom on reactions, smooth transitions')")

    # ── scriptgen command ────────────────────────────────────────────────
    scriptgen_parser = subparsers.add_parser("scriptgen", help="Generate a story script with AI")
    scriptgen_parser.add_argument("--topic", required=True,
                                  help="What the story is about (e.g. 'the danger of comfort zones')")
    scriptgen_parser.add_argument("--category", type=str, default="life-lesson",
                                  choices=["stoic", "motivation", "meditation", "horror", "love",
                                           "psychology", "history", "philosophy", "nature", "scifi",
                                           "mystery", "life-lesson", "dark", "faith", "money", "relationship"],
                                  help="Script category/genre (default: life-lesson)")
    scriptgen_parser.add_argument("--art-style", type=str, default="sketch",
                                  help="Art style for visual descriptions (default: sketch)")
    scriptgen_parser.add_argument("--duration", type=int, default=60,
                                  help="Target video duration in seconds (default: 60)")
    scriptgen_parser.add_argument("--tone", type=str, default="reflective and powerful",
                                  help="Narration tone (e.g. 'dark and suspenseful', 'warm and hopeful')")
    scriptgen_parser.add_argument("--character", type=str, default="",
                                  choices=["", "man", "woman", "elder", "youth", "warrior", "monk",
                                           "child", "silhouette", "stickman", "businessman", "artist",
                                           "samurai", "philosopher", "traveler", "robot", "girl"],
                                  help="Character preset for consistent visual appearance across scenes")
    scriptgen_parser.add_argument("--background", type=str, default="",
                                  choices=["", "nature", "urban", "forest", "ocean", "mountain", "temple",
                                           "desert", "space", "minimal", "rain", "night", "countryside",
                                           "underwater", "ruins", "library", "battlefield", "greek"],
                                  help="Background theme for consistent environment across scenes")
    scriptgen_parser.add_argument("--output", type=str, default=None,
                                  help="Output file path (default: prints to stdout)")
    scriptgen_parser.add_argument("--prompt", type=str, default="",
                                  help="Extra instructions for the AI (e.g. 'include a plot twist at the end')")
    scriptgen_parser.add_argument("--run", action="store_true",
                                  help="Generate script AND immediately render it as a story video")

    # Check if first arg is a subcommand
    import sys
    if len(sys.argv) > 1 and sys.argv[1] in ("clip", "story", "upload", "enhance", "scriptgen"):
        args = parser.parse_args()
    else:
        # No subcommand — use backward-compatible clip mode
        parser_compat = argparse.ArgumentParser(
            description="Turn a long video into short, captioned, vertical clips."
        )
        parser_compat.add_argument("--input", help="Path to local source video file")
        parser_compat.add_argument("--youtube-url", help="YouTube URL")
        parser_compat.add_argument("--num-clips", type=int, default=5)
        parser_compat.add_argument("--output-dir", default=settings.output_dir)
        parser_compat.add_argument("--start", type=float, default=None)
        parser_compat.add_argument("--end", type=float, default=None)
        parser_compat.add_argument("--reframe", choices=["crop", "blur"], default="crop")
        parser_compat.add_argument("--emoji", action="store_true")
        parser_compat.add_argument("--prompt", type=str, default="")
        parser_compat.add_argument("--category", type=str, default="auto")
        parser_compat.add_argument("--interactive", "-i", action="store_true")
        parser_compat.add_argument("--clip-min", type=int, default=None)
        parser_compat.add_argument("--clip-max", type=int, default=None)
        parser_compat.add_argument("--max-duration", type=float, default=None)
        parser_compat.add_argument("--montage", action="store_true")
        parser_compat.add_argument("--narration", type=str, default=None)
        parser_compat.add_argument("--narration-voice", type=str, default="male-en")
        parser_compat.add_argument("--narration-vol", type=float, default=1.0)
        parser_compat.add_argument("--music", type=str, default=None)
        parser_compat.add_argument("--music-ai", action="store_true")
        parser_compat.add_argument("--music-genre", type=str, default=None)
        parser_compat.add_argument("--music-vol", type=float, default=0.05)
        parser_compat.add_argument("--music-level", type=float, default=1.0)
        parser_compat.add_argument("--translate", type=str, default=None,
                                   help="Translate captions to another language (e.g. 'indonesian', 'spanish', 'japanese')")
        parser_compat.add_argument("--sfx", type=str, default=None)
        parser_compat.add_argument("--sfx-vol", type=float, default=0.6)
        parser_compat.add_argument("--enhance", action="store_true")
        parser_compat.add_argument("--enhance-prompt", type=str, default="")
        parser_compat.add_argument("--upload", action="store_true")
        parser_compat.add_argument("--upload-privacy", choices=["private", "unlisted", "public"],
                                   default="private")
        args = parser_compat.parse_args()
        args.command = "clip"

    if args.command == "scriptgen":
        from .scriptgen import generate_script

        output_path = args.output
        if not output_path and args.run:
            output_path = os.path.join(settings.output_dir, "generated_script.txt")

        script = generate_script(
            topic=args.topic,
            category=args.category,
            art_style=getattr(args, 'art_style', 'sketch'),
            duration=args.duration,
            tone=args.tone,
            character=getattr(args, 'character', ''),
            background=getattr(args, 'background', ''),
            extra_instructions=args.prompt,
            output_path=output_path,
        )

        if not output_path:
            print("\n" + "=" * 60)
            print(script)
            print("=" * 60)

        if args.run:
            print(f"\n-> Rendering generated script...")
            from .story import create_story
            create_story(
                script=script,
                output_dir=settings.output_dir,
                voice="warm",
                visuals="sd",
                art_style=getattr(args, 'art_style', 'sketch'),
            )

        return

    if args.command == "story":
        from .story import create_story

        # Load script from file if path given
        script = args.script
        if os.path.isfile(script):
            with open(script) as f:
                script = f.read()

        music_path = args.music
        auto_music = not args.no_music and not args.music

        if args.music_ai and not music_path:
            from .music import suggest_and_pick_music
            music_path = suggest_and_pick_music(
                "cinematic", "narrated story", args.output_dir, genre=args.music_genre
            )
            auto_music = False

        voice_rate = f"{args.voice_rate:+d}%" if args.voice_rate is not None else None

        final_path = create_story(
            script=script,
            output_dir=args.output_dir,
            voice=args.voice,
            voice_rate=voice_rate,
            music_path=music_path,
            music_volume=args.music_level,
            auto_music=auto_music,
            visuals=args.visuals,
            art_style=getattr(args, 'art_style', ''),
            image_category=getattr(args, 'image_category', ''),
            animation=getattr(args, 'animation', 'ken-burns'),
            film_grain=getattr(args, 'film_grain', ''),
            caption_style=getattr(args, 'caption_style', 'default'),
            caption_font=getattr(args, 'caption_font', ''),
            caption_animation=getattr(args, 'caption_animation', 'karaoke'),
            hook_text=getattr(args, 'hook_text', ''),
            review_images=getattr(args, 'review_images', False),
        )

        if args.upload and final_path:
            selected = _interactive_upload_select([final_path])
            if selected:
                print("\n-> Generating optimized YouTube metadata with AI...")
                meta = _generate_story_metadata(script)
                print("\n-> Uploading story to YouTube Shorts...")
                upload_to_youtube(
                    final_path,
                    title=meta["title"],
                    description=meta["description"],
                    tags=meta["tags"],
                    privacy=args.upload_privacy,
                )
            else:
                print("   Upload skipped.")

        return

    # upload command
    if args.command == "upload":
        if not os.path.exists(args.input):
            parser.error(f"File not found: {args.input}")

        title = args.title or ""
        description = args.description or ""
        tags = [t.strip() for t in args.tags.split(",")] if args.tags else []

        if not args.no_ai and (not args.title or not args.description):
            print("-> Generating optimized YouTube metadata with AI...")
            meta = _generate_clip_metadata(
                title=args.title or os.path.splitext(os.path.basename(args.input))[0],
                category="general",
                hook_text="",
                reason="Direct upload",
                emoji="",
                score=90,
            )
            if not args.title:
                title = meta["title"]
            if not args.description:
                description = meta["description"]
            if not tags:
                tags = meta["tags"]

        print(f"\n-> Uploading to YouTube Shorts...")
        upload_to_youtube(
            args.input,
            title=title,
            description=description,
            tags=tags,
            privacy=args.privacy,
        )
        return

    # enhance command
    if args.command == "enhance":
        if not os.path.exists(args.input):
            parser.error(f"File not found: {args.input}")

        if args.output:
            output = args.output
        else:
            base, ext = os.path.splitext(args.input)
            output = f"{base}_enhanced{ext}"

        print(f"-> Enhancing {os.path.basename(args.input)}...")
        enhance_clip(
            args.input, output,
            title=args.title,
            user_prompt=args.prompt,
        )
        print(f"   saved -> {output}")
        return

    # clip command
    if not args.input and not args.youtube_url:
        parser.error("Provide either --input <file> or --youtube-url <url>")

    input_path = args.input
    if args.youtube_url:
        print("-> Downloading from YouTube...")
        os.makedirs(args.output_dir, exist_ok=True)
        input_path = download_youtube(
            args.youtube_url,
            os.path.join(args.output_dir, "input.mp4"),
        )

    # Override clip duration settings from CLI if provided
    if getattr(args, 'clip_min', None) is not None:
        settings.clip_min_seconds = args.clip_min
    if getattr(args, 'clip_max', None) is not None:
        settings.clip_max_seconds = args.clip_max

    process_video(input_path, args.num_clips, args.output_dir,
                  start=args.start, end=args.end, reframe=args.reframe,
                  emoji=args.emoji, user_prompt=args.prompt,
                  video_category=args.category,
                  interactive=args.interactive, max_duration=args.max_duration,
                  narration=args.narration, narration_voice=args.narration_voice,
                  narration_vol=args.narration_vol, montage=args.montage,
                  music=args.music, music_ai=args.music_ai,
                  music_vol=args.music_vol, music_level=args.music_level,
                  music_genre=args.music_genre, translate=args.translate,
                  sfx=args.sfx, sfx_vol=getattr(args, 'sfx_vol', 0.6),
                  enhance=args.enhance, enhance_prompt=getattr(args, 'enhance_prompt', ''),
                  upload=args.upload, upload_privacy=args.upload_privacy)


if __name__ == "__main__":
    main()
