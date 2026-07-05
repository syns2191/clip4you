"""Wraps clip extraction pipeline for GUI use."""

import os
import tempfile
import shutil
from dataclasses import dataclass, field
from typing import List, Optional

from ...transcribe import transcribe, Word
from ...clip_selector import select_clips, ClipCandidate
from ...render import (
    cut_clip, reframe_vertical, burn_captions, add_text_hook,
    add_emoji_overlay, mix_music, mix_sfx,
    generate_crowd_roar, generate_sfx,
)
from ...narration import generate_narration, mix_narration, POPULAR_VOICES
from ...captions import build_ass
from ...enhance import enhance_clip
from ...music import suggest_and_pick_music
from ...download import download_youtube


@dataclass
class ClipSession:
    input_path: str
    output_dir: str
    num_clips: int = 5
    start: Optional[float] = None
    end: Optional[float] = None
    reframe: str = "crop"
    emoji: bool = False
    user_prompt: str = ""
    video_category: str = "auto"
    max_duration: Optional[float] = None
    narration: Optional[str] = None
    narration_voice: str = "male-en"
    narration_vol: float = 1.0
    music: Optional[str] = None
    music_ai: bool = False
    music_vol: float = 0.05
    music_level: float = 1.0
    music_genre: Optional[str] = None
    translate: Optional[str] = None
    sfx: Optional[str] = None
    sfx_vol: float = 0.6
    enhance: bool = False
    enhance_prompt: str = ""
    montage: bool = False

    segments: list = field(default_factory=list)
    candidates: List[ClipCandidate] = field(default_factory=list)
    rendered_paths: List[str] = field(default_factory=list)


def step1_transcribe(session: ClipSession):
    """Transcribe video and find clips. Returns list of ClipCandidate."""
    os.makedirs(session.output_dir, exist_ok=True)

    if session.start is not None or session.end is not None:
        from ...render import FFMPEG
        import subprocess
        trim_start = session.start or 0
        trimmed_path = os.path.join(session.output_dir, "trimmed_source.mp4")
        cmd = [FFMPEG, "-y", "-i", session.input_path, "-ss", str(trim_start)]
        if session.end:
            cmd += ["-to", str(session.end)]
        cmd += ["-c", "copy", trimmed_path]
        subprocess.run(cmd, capture_output=True)
        session.input_path = trimmed_path

    print("-> Transcribing...")
    session.segments = transcribe(session.input_path)

    print(f"-> Finding best {session.num_clips} moments...")
    session.candidates = select_clips(
        session.segments, num_clips=session.num_clips,
        user_prompt=session.user_prompt, video_category=session.video_category,
        video_path=session.input_path,
    )
    return session.candidates


def step2_render(session: ClipSession, selected_indices: List[int] = None):
    """Render selected clips. If selected_indices is None, render all."""
    candidates = session.candidates
    if selected_indices is not None:
        candidates = [candidates[i] for i in selected_indices if 0 <= i < len(candidates)]
    if not candidates:
        print("No clips selected.")
        return []

    if session.max_duration:
        for clip in candidates:
            if clip.end - clip.start > session.max_duration:
                clip.end = clip.start + session.max_duration

    music = session.music
    if session.music_ai and not music and candidates:
        top = candidates[0]
        music = suggest_and_pick_music(top.category, top.title, session.output_dir, genre=session.music_genre)

    montage_tmp = tempfile.mkdtemp() if session.montage else None
    session.rendered_paths = []

    for i, clip in enumerate(candidates, start=1):
        print(f"-> Rendering clip {i}/{len(candidates)}: {clip.title}")
        with tempfile.TemporaryDirectory() as tmp:
            cut_path = os.path.join(tmp, "cut.mp4")
            vertical_path = os.path.join(tmp, "vertical.mp4")
            ass_path = os.path.join(tmp, "captions.ass")
            captioned_path = os.path.join(tmp, "captioned.mp4")
            hooked_path = os.path.join(tmp, "hooked.mp4")

            if montage_tmp:
                final_path = os.path.join(montage_tmp, f"part_{i:02d}.mp4")
            else:
                final_path = os.path.join(
                    session.output_dir, f"clip_{i:02d}_{clip.category}_{clip.score}.mp4",
                )

            cut_clip(session.input_path, clip.start, clip.end, cut_path)
            reframe_vertical(cut_path, vertical_path, mode=session.reframe)

            clip_words = [
                Word(w.text, w.start, w.end)
                for seg in session.segments for w in seg.words
                if clip.start <= w.start <= clip.end
            ]
            if session.translate:
                from ...translate import translate_words
                clip_words = translate_words(clip_words, session.translate)
            clip_duration = clip.end - clip.start
            build_ass(clip_words, clip.start, ass_path)
            burn_captions(vertical_path, ass_path, captioned_path)
            add_text_hook(captioned_path, clip.hook_text, hooked_path, clip_duration=clip_duration)

            if session.emoji:
                add_emoji_overlay(hooked_path, clip.emoji, clip_duration, final_path)
            else:
                os.rename(hooked_path, final_path)

            if music:
                music_out = final_path + ".music.mp4"
                mix_music(final_path, music, music_out,
                          original_volume=session.music_vol, music_volume=session.music_level)
                os.replace(music_out, final_path)

            if session.narration:
                voice = POPULAR_VOICES.get(session.narration_voice, session.narration_voice)
                narr_audio = final_path + ".narr.mp3"
                generate_narration(session.narration, narr_audio, voice=voice)
                narr_out = final_path + ".narr.mp4"
                mix_narration(final_path, narr_audio, narr_out,
                              original_volume=0.3, narration_volume=session.narration_vol)
                os.replace(narr_out, final_path)
                os.unlink(narr_audio)

            if session.sfx:
                sfx_audio = final_path + ".sfx.m4a"
                if session.sfx == "crowd":
                    generate_crowd_roar(sfx_audio, clip_duration)
                else:
                    generate_sfx(sfx_audio, session.sfx)
                sfx_out = final_path + ".sfx.mp4"
                mix_sfx(final_path, sfx_audio, sfx_out, offset=0.0, volume=session.sfx_vol)
                os.replace(sfx_out, final_path)
                os.unlink(sfx_audio)

            if session.enhance:
                clip_transcript = "\n".join(
                    f"[{w.start - clip.start:.1f}s] {w.text}"
                    for seg in session.segments for w in seg.words
                    if clip.start <= w.start <= clip.end
                )
                enhanced_path = final_path + ".enhanced.mp4"
                enhance_clip(
                    final_path, enhanced_path, title=clip.title,
                    category=clip.category, hook_text=clip.hook_text,
                    score=clip.score, reason=clip.reason,
                    transcript=clip_transcript, user_prompt=session.enhance_prompt,
                )
                os.replace(enhanced_path, final_path)

        session.rendered_paths.append(final_path)
        print(f"   Saved: {final_path}")

    if montage_tmp and session.rendered_paths:
        from ...story import _concat_with_transitions
        montage_path = os.path.join(session.output_dir, "montage_best_moments.mp4")
        print(f"\n-> Stitching {len(session.rendered_paths)} clips into montage...")
        _concat_with_transitions(session.rendered_paths, montage_path)
        shutil.rmtree(montage_tmp, ignore_errors=True)
        session.rendered_paths = [montage_path]
        print(f"   Saved: {montage_path}")

    return session.rendered_paths
