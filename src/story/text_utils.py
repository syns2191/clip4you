"""Text processing utilities for subtitle and drawtext generation."""
import os
import shutil
import subprocess
from typing import List, Optional

from ..render import FFMPEG


def _escape_drawtext(text: str) -> str:
    """Escape text for ffmpeg drawtext filter."""
    t = text
    t = t.replace("\\", "\\\\")
    t = t.replace("'", "\\'")
    t = t.replace(":", "\\:")
    t = t.replace("%", "%%")
    t = t.replace('"', '\\"')
    return t


def _wrap_text(text: str, max_chars: int = 25) -> str:
    """Word-wrap text for subtitle display."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 > max_chars:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        lines.append(current)
    return "\n".join(lines)


def _build_typewriter_filters(
    words: List[str],
    start: float,
    end: float,
    fontfile: str,
    y_base: str = "h-text_h-180",
) -> List[str]:
    """Build drawtext filters that reveal words one by one (typewriter effect).
    Each word appears at a staggered time within the sentence duration."""
    if not words:
        return []

    total_dur = end - start
    fade_out_dur = 0.4
    # Time per word reveal — spread words evenly across ~70% of duration
    typing_window = total_dur * 0.7
    delay_per_word = typing_window / max(len(words), 1)

    filters = []
    for i in range(len(words)):
        # Show accumulated words up to this point
        partial_text = " ".join(words[:i + 1])
        escaped = _escape_drawtext(partial_text)
        wrapped = _wrap_text(escaped)

        word_start = start + (i * delay_per_word)
        # Next word replaces this one, or this is the last
        if i < len(words) - 1:
            word_end = start + ((i + 1) * delay_per_word)
        else:
            word_end = end

        # Alpha: appear instantly, hold, fade out at sentence end (only last word fades)
        if i < len(words) - 1:
            alpha = (
                f"if(between(t\\,{word_start:.2f}\\,{word_end:.2f})\\,1\\,0)"
            )
        else:
            alpha = (
                f"if(lt(t\\,{word_start:.2f})\\,0\\,"
                f"if(lt(t\\,{end - fade_out_dur:.2f})\\,1\\,"
                f"if(lt(t\\,{end:.2f})\\,({end:.2f}-t)/{fade_out_dur:.2f}\\,"
                f"0)))"
            )

        filters.append(
            f"drawtext=text='{wrapped}':"
            f"fontfile={fontfile}:"
            f"fontsize=46:fontcolor=white:"
            f"shadowcolor=black@0.8:shadowx=3:shadowy=3:"
            f"borderw=1:bordercolor=black@0.3:"
            f"x=(w-text_w)/2:y={y_base}:"
            f"alpha='{alpha}'"
        )

    # Blinking cursor after last word
    cursor_start = start
    cursor_end = end - fade_out_dur
    # Cursor x position: after the text. Use a fixed offset since we can't measure dynamically.
    # Blink every 0.5s using mod
    cursor_alpha = (
        f"if(between(t\\,{cursor_start:.2f}\\,{cursor_end:.2f})\\,"
        f"if(lt(mod(t\\,0.8)\\,0.5)\\,1\\,0)\\,0)"
    )
    filters.append(
        f"drawtext=text='|':"
        f"fontfile={fontfile}:"
        f"fontsize=46:fontcolor=white@0.9:"
        f"x=(w/2)+30:y={y_base}:"
        f"alpha='{cursor_alpha}'"
    )

    return filters


def _burn_subtitle(input_path: str, text: str, duration: float, output_path: str,
                   timings: Optional[List] = None) -> None:
    """Burn cinematic typewriter subtitles synced to speech timing.
    Words appear one by one as they are spoken, with a blinking cursor."""
    from ..narration import is_silent_scene
    if is_silent_scene(text):
        shutil.copy2(input_path, output_path)
        return

    font_primary = "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"
    font_fallback = "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf"
    font_last = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    fontfile = font_primary
    if not os.path.exists(fontfile):
        fontfile = font_fallback if os.path.exists(font_fallback) else font_last

    all_filters = []

    if timings and len(timings) > 0:
        for st in timings:
            words = st.text.split()
            start = st.start
            end = st.start + st.duration
            all_filters.extend(
                _build_typewriter_filters(words, start, end, fontfile)
            )
    else:
        words = text.split()
        start = 0.3
        end = duration - 0.2
        all_filters.extend(
            _build_typewriter_filters(words, start, end, fontfile)
        )

    if not all_filters:
        shutil.copy2(input_path, output_path)
        return

    vf = ",".join(all_filters)

    cmd = [
        FFMPEG, "-y",
        "-i", input_path,
        "-vf", vf,
        "-c:a", "copy",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        shutil.copy2(input_path, output_path)
