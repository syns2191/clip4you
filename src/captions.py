"""
Builds .ass subtitle files with word-by-word highlight animation.
Words are grouped into short on-screen chunks (2-4 words) so captions
stay readable on a vertical phone screen. The active word scales up
briefly and changes color. Each chunk fades in and out.

Uses BorderStyle=4 (opaque background box) for a pill/textbox look.
"""
from typing import List

from .transcribe import Word

WORDS_PER_CHUNK = 3
FONT_NAME = "Impact"
FONT_SIZE = 78
# ASS colors are &HAABBGGRR
PRIMARY_COLOR = "&H00FFFFFF"       # white
HIGHLIGHT_COLOR = "&H0000CFFF"     # golden yellow
OUTLINE_COLOR = "&H00000000"       # black
BACK_COLOR = "&HB0000000"          # semi-transparent black box
MARGIN_V = 400

# Tension-based highlight colors (low tension -> high tension)
# ASS format: &H00BBGGRR
TENSION_COLORS = [
    "&H00FFCC33",   # calm blue
    "&H0000CFFF",   # golden yellow (default)
    "&H000099FF",   # orange
    "&H000055FF",   # red-orange
    "&H000000FF",   # red (peak tension)
]


def _word_tension(word: "Word", all_words: List["Word"]) -> float:
    """Score 0.0-1.0 based on how fast this word is spoken relative to the clip average.
    Faster speech = higher tension."""
    duration = word.end - word.start
    if duration <= 0:
        return 0.5
    chars_per_sec = len(word.text) / duration

    durations = [w.end - w.start for w in all_words if (w.end - w.start) > 0]
    if not durations:
        return 0.5
    rates = [len(w.text) / (w.end - w.start) for w in all_words if (w.end - w.start) > 0]
    avg_rate = sum(rates) / len(rates)
    if avg_rate <= 0:
        return 0.5

    ratio = chars_per_sec / avg_rate
    # ratio > 1 = faster than average = more tension
    # Map ratio 0.5..2.0 to tension 0.0..1.0
    tension = max(0.0, min(1.0, (ratio - 0.5) / 1.5))
    return tension


def _tension_color(tension: float) -> str:
    """Pick a highlight color from the tension gradient."""
    idx = min(int(tension * len(TENSION_COLORS)), len(TENSION_COLORS) - 1)
    return TENSION_COLORS[idx]


def _fmt_time(t: float) -> str:
    t = max(t, 0.0)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:01d}:{m:02d}:{s:05.2f}"


def _group_words(words: List[Word]) -> List[List[Word]]:
    return [words[i : i + WORDS_PER_CHUNK] for i in range(0, len(words), WORDS_PER_CHUNK)]


def build_ass(
    words: List[Word],
    clip_start: float,
    output_path: str,
    canvas_w: int = 1080,
    canvas_h: int = 1920,
    tension_colors: bool = True,
) -> None:
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {canvas_w}
PlayResY: {canvas_h}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{FONT_NAME},{FONT_SIZE},{PRIMARY_COLOR},{PRIMARY_COLOR},{OUTLINE_COLOR},{BACK_COLOR},1,0,0,0,100,100,3,0,4,4,0,2,40,40,{MARGIN_V},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]

    for chunk in _group_words(words):
        if not chunk:
            continue

        chunk_start = chunk[0].start - clip_start
        chunk_end = chunk[-1].end - clip_start
        if chunk_end <= chunk_start:
            continue

        for active_idx, active_word in enumerate(chunk):
            seg_start = active_word.start - clip_start
            seg_end = active_word.end - clip_start
            if seg_end <= seg_start:
                continue

            rendered = []
            is_first = (active_idx == 0)
            is_last = (active_idx == len(chunk) - 1)

            for i, w in enumerate(chunk):
                safe_text = w.text.replace("{", "(").replace("}", ")")
                if i == active_idx:
                    if tension_colors:
                        t = _word_tension(w, words)
                        color = _tension_color(t)
                    else:
                        color = HIGHLIGHT_COLOR
                    rendered.append(
                        f"{{\\c{color}\\fscx110\\fscy110"
                        f"\\t(0,80,\\fscx100\\fscy100)}}{safe_text}"
                    )
                else:
                    rendered.append(f"{{\\c{PRIMARY_COLOR}}}{safe_text}")

            text = " ".join(rendered)

            # Fade in on first word of chunk, fade out on last
            if is_first and is_last:
                text = r"{\fad(100,100)}" + text
            elif is_first:
                text = r"{\fad(100,0)}" + text
            elif is_last:
                text = r"{\fad(0,100)}" + text

            lines.append(
                f"Dialogue: 0,{_fmt_time(seg_start)},{_fmt_time(seg_end)},Default,,0,0,0,,{text}\n"
            )

    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
