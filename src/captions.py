"""
Builds .ass subtitle files with word-by-word highlight animation.
Words are grouped into short on-screen chunks (2-4 words) so captions
stay readable on a vertical phone screen. The active word scales up
briefly and changes color. Each chunk fades in and out.

Uses BorderStyle=4 (opaque background box) for a pill/textbox look.
"""
import os
from typing import List

from .transcribe import Word

WORDS_PER_CHUNK = 3
FONT_NAME = "Futura Medium"
FONT_SIZE = 82

_FONTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")

CAPTION_FONTS = {
    "futura":      {"ass_name": "Futura Medium",     "file": "/System/Library/Fonts/Supplemental/Futura.ttc",         "fallback": "/System/Library/Fonts/Supplemental/Arial Bold.ttf"},
    "impact":      {"ass_name": "Impact",            "file": "/System/Library/Fonts/Supplemental/Impact.ttf",         "fallback": "/System/Library/Fonts/Supplemental/Arial Black.ttf"},
    "arial-black": {"ass_name": "Arial Black",       "file": "/System/Library/Fonts/Supplemental/Arial Black.ttf",    "fallback": "/System/Library/Fonts/Supplemental/Arial Bold.ttf"},
    "georgia":     {"ass_name": "Georgia Bold",      "file": "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",   "fallback": "/System/Library/Fonts/Supplemental/Georgia.ttf"},
    "trebuchet":   {"ass_name": "Trebuchet MS Bold",  "file": "/System/Library/Fonts/Supplemental/Trebuchet MS Bold.ttf", "fallback": "/System/Library/Fonts/Supplemental/Trebuchet MS.ttf"},
    "verdana":     {"ass_name": "Verdana Bold",      "file": "/System/Library/Fonts/Supplemental/Verdana Bold.ttf",   "fallback": "/System/Library/Fonts/Supplemental/Verdana.ttf"},
    "din":         {"ass_name": "DIN Alternate Bold", "file": "/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf", "fallback": "/System/Library/Fonts/Supplemental/Arial Bold.ttf"},
    "chalkduster": {"ass_name": "Chalkduster",       "file": "/System/Library/Fonts/Supplemental/Chalkduster.ttf",   "fallback": "/System/Library/Fonts/Supplemental/Comic Sans MS Bold.ttf"},
    "comic-sans":  {"ass_name": "Comic Sans MS Bold", "file": "/System/Library/Fonts/Supplemental/Comic Sans MS Bold.ttf", "fallback": "/System/Library/Fonts/Supplemental/Comic Sans MS.ttf"},
    "times":       {"ass_name": "Times New Roman Bold", "file": "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf", "fallback": "/System/Library/Fonts/Supplemental/Times New Roman.ttf"},
    "croissant-one":   {"ass_name": "Croissant One",      "file": os.path.join(_FONTS_DIR, "CroissantOne-Regular.ttf"),    "fallback": "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"},
}
CAPTION_FONT_CHOICES = list(CAPTION_FONTS.keys())

CAPTION_ANIMATIONS = ["karaoke", "word", "typing"]
# ASS colors are &HAABBGGRR
PRIMARY_COLOR = "&H00FFFFFF"       # white
HIGHLIGHT_COLOR = "&H0000CFFF"     # golden yellow
OUTLINE_COLOR = "&H00000000"       # black
BACK_COLOR = "&H80000000"          # semi-transparent shadow
MARGIN_V = 380

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
    canvas_w: int = None,
    canvas_h: int = None,
    tension_colors: bool = True,
    caption_font: str = "",
    caption_animation: str = "karaoke",
) -> None:
    from .config import settings
    if canvas_w is None:
        canvas_w = settings.vertical_width
    if canvas_h is None:
        canvas_h = settings.vertical_height

    font_name = FONT_NAME
    if caption_font and caption_font in CAPTION_FONTS:
        font_name = CAPTION_FONTS[caption_font]["ass_name"]

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {canvas_w}
PlayResY: {canvas_h}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{FONT_SIZE},{PRIMARY_COLOR},{PRIMARY_COLOR},{OUTLINE_COLOR},{BACK_COLOR},1,0,0,0,100,100,6,0,1,3,3,2,40,40,{MARGIN_V},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]

    for chunk in _group_words(words):
        if not chunk:
            continue

        chunk_end = chunk[-1].end - clip_start
        if chunk_end <= 0:
            continue

        if caption_animation == "karaoke":
            _build_karaoke(chunk, clip_start, chunk_end, words, tension_colors, lines)
        elif caption_animation == "word":
            _build_word_typing(chunk, clip_start, chunk_end, words, tension_colors, lines)
        else:
            _build_char_typing(chunk, clip_start, chunk_end, words, tension_colors, lines)

    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def _build_karaoke(chunk, clip_start, chunk_end, all_words, tension_colors, lines):
    """Original style: full chunk visible, active word highlighted."""
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
            if i == 0 and active_idx == 0:
                safe_text = safe_text[:1].upper() + safe_text[1:] if safe_text else safe_text
            if i == active_idx:
                if tension_colors:
                    t = _word_tension(w, all_words)
                    color = _tension_color(t)
                else:
                    color = HIGHLIGHT_COLOR
                rendered.append(
                    f"{{\\c{color}\\fscx120\\fscy120\\bord5\\3c&H004080FF"
                    f"\\t(0,150,\\fscx100\\fscy100\\bord3\\3c&H00000000)}}{safe_text}"
                )
            else:
                rendered.append(f"{{\\c{PRIMARY_COLOR}}}{safe_text}")

        text = " ".join(rendered)

        if is_first and is_last:
            text = r"{\fad(150,150)}" + text
        elif is_first:
            text = r"{\fad(150,0)}" + text
        elif is_last:
            text = r"{\fad(0,150)}" + text

        lines.append(
            f"Dialogue: 0,{_fmt_time(seg_start)},{_fmt_time(seg_end)},Default,,0,0,0,,{text}\n"
        )


def _build_word_typing(chunk, clip_start, chunk_end, all_words, tension_colors, lines):
    """Words appear one by one as spoken, building up to the full chunk."""
    for word_idx in range(len(chunk)):
        seg_start = chunk[word_idx].start - clip_start
        if word_idx + 1 < len(chunk):
            seg_end = chunk[word_idx + 1].start - clip_start
        else:
            seg_end = chunk_end
        if seg_end <= seg_start:
            continue

        rendered = []
        for i in range(word_idx + 1):
            w = chunk[i]
            safe_text = w.text.replace("{", "(").replace("}", ")")
            if i == 0:
                safe_text = safe_text[:1].upper() + safe_text[1:] if safe_text else safe_text
            if i == word_idx:
                if tension_colors:
                    t = _word_tension(w, all_words)
                    color = _tension_color(t)
                else:
                    color = HIGHLIGHT_COLOR
                rendered.append(
                    f"{{\\c{color}\\fscx120\\fscy120\\bord5\\3c&H004080FF"
                    f"\\t(0,150,\\fscx100\\fscy100\\bord3\\3c&H00000000)}}{safe_text}"
                )
            else:
                rendered.append(f"{{\\c{PRIMARY_COLOR}}}{safe_text}")

        text = " ".join(rendered)

        is_first = (word_idx == 0)
        is_last = (word_idx == len(chunk) - 1)
        if is_first and is_last:
            text = r"{\fad(150,150)}" + text
        elif is_first:
            text = r"{\fad(150,0)}" + text
        elif is_last:
            text = r"{\fad(0,150)}" + text

        lines.append(
            f"Dialogue: 0,{_fmt_time(seg_start)},{_fmt_time(seg_end)},Default,,0,0,0,,{text}\n"
        )


def _build_char_typing(chunk, clip_start, chunk_end, all_words, tension_colors, lines):
    """Character-by-character typing animation like human writing."""
    typed_frames = []

    for word_idx, word in enumerate(chunk):
        w_start = word.start - clip_start
        w_end = word.end - clip_start
        if w_end <= w_start:
            continue

        safe_word = word.text.replace("{", "(").replace("}", ")")
        if word_idx == 0:
            safe_word = safe_word[:1].upper() + safe_word[1:] if safe_word else safe_word
        prev_words = []
        for pi, pw in enumerate(chunk[:word_idx]):
            pt = pw.text.replace("{", "(").replace("}", ")")
            if pi == 0:
                pt = pt[:1].upper() + pt[1:] if pt else pt
            prev_words.append(pt)
        prefix = " ".join(prev_words)

        if tension_colors:
            t = _word_tension(word, all_words)
            color = _tension_color(t)
        else:
            color = HIGHLIGHT_COLOR

        n_chars = len(safe_word)
        char_dur = (w_end - w_start) / max(n_chars, 1)

        for ci in range(1, n_chars + 1):
            partial = safe_word[:ci]
            t_start = w_start + (ci - 1) * char_dur
            t_end = w_start + ci * char_dur if ci < n_chars else w_end

            parts = []
            if prefix:
                parts.append(f"{{\\c{PRIMARY_COLOR}}}{prefix}")
            parts.append(
                f"{{\\c{color}\\fscx120\\fscy120\\bord5\\3c&H004080FF"
                f"\\t(0,80,\\fscx100\\fscy100\\bord3\\3c&H00000000)}}{partial}"
            )
            display = " ".join(parts)
            typed_frames.append((t_start, t_end, display))

    if typed_frames:
        last_start, _, last_display = typed_frames[-1]
        typed_frames[-1] = (last_start, chunk_end, last_display)

    for fi, (t_start, t_end, display) in enumerate(typed_frames):
        if t_end <= t_start:
            continue
        text = display
        if fi == 0 and fi == len(typed_frames) - 1:
            text = r"{\fad(150,150)}" + text
        elif fi == 0:
            text = r"{\fad(150,0)}" + text
        elif fi == len(typed_frames) - 1:
            text = r"{\fad(0,150)}" + text

        lines.append(
            f"Dialogue: 0,{_fmt_time(t_start)},{_fmt_time(t_end)},Default,,0,0,0,,{text}\n"
        )
