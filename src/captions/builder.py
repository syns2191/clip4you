"""Public build_ass entry point — assembles the ASS header and dispatches to animation builders."""
from typing import List, Optional

from ..transcribe import Word
from .style import FONT_NAME, FONT_SIZE, PRIMARY_COLOR, OUTLINE_COLOR, BACK_COLOR, MARGIN_V, CAPTION_FONTS
from .utils import _group_words
from .animations import _build_karaoke, _build_smooth_karaoke, _build_word_typing, _build_char_typing


def build_ass(
    words: List[Word],
    clip_start: float,
    output_path: str,
    canvas_w: Optional[int] = None,
    canvas_h: Optional[int] = None,
    tension_colors: bool = True,
    caption_font: str = "",
    caption_animation: str = "karaoke",
    margin_v_override: Optional[int] = None,
    pos_y: Optional[int] = None,
) -> None:
    """Write an ASS subtitle file with word-by-word caption animation.

    pos_y: pins captions to an absolute Y pixel (bottom of text block).
    margin_v_override: fallback margin shift when pos_y is not set.
    """
    from ..config import settings
    if canvas_w is None:
        canvas_w = settings.vertical_width
    if canvas_h is None:
        canvas_h = settings.vertical_height

    font_name = CAPTION_FONTS[caption_font]["ass_name"] if caption_font in CAPTION_FONTS else FONT_NAME
    margin_v = margin_v_override if margin_v_override is not None else MARGIN_V
    cx = canvas_w // 2
    pos_tag = f"{{\\pos({cx},{pos_y})}}" if pos_y is not None else ""

    header = (
        f"[Script Info]\nScriptType: v4.00+\nPlayResX: {canvas_w}\nPlayResY: {canvas_h}\n\n"
        f"[V4+ Styles]\n"
        f"Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        f"Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        f"Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_name},{FONT_SIZE},{PRIMARY_COLOR},{PRIMARY_COLOR},{OUTLINE_COLOR},{BACK_COLOR},"
        f"1,0,0,0,100,100,6,0,1,3,3,2,40,40,{margin_v},1\n\n"
        f"[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = [header]

    dispatch = {
        "karaoke":        _build_karaoke,
        "smooth-karaoke": _build_smooth_karaoke,
        "word":           _build_word_typing,
        "typing":         _build_char_typing,
    }
    builder = dispatch.get(caption_animation, _build_char_typing)

    for chunk in _group_words(words):
        if not chunk:
            continue
        chunk_end = chunk[-1].end - clip_start
        if chunk_end <= 0:
            continue
        builder(chunk, clip_start, chunk_end, words, tension_colors, lines, pos_tag=pos_tag)

    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
