"""ASS subtitle generation with word-by-word highlight animation."""
from .style import (
    WORDS_PER_CHUNK, FONT_NAME, FONT_SIZE, MARGIN_V,
    CAPTION_FONTS, CAPTION_FONT_CHOICES, CAPTION_ANIMATIONS,
    PRIMARY_COLOR, HIGHLIGHT_COLOR, OUTLINE_COLOR, BACK_COLOR, TENSION_COLORS,
)
from .utils import _fmt_time, _group_words, _word_tension, _tension_color
from .animations import _build_karaoke, _build_smooth_karaoke, _build_word_typing, _build_char_typing
from .builder import build_ass

__all__ = [
    "WORDS_PER_CHUNK", "FONT_NAME", "FONT_SIZE", "MARGIN_V",
    "CAPTION_FONTS", "CAPTION_FONT_CHOICES", "CAPTION_ANIMATIONS",
    "PRIMARY_COLOR", "HIGHLIGHT_COLOR", "OUTLINE_COLOR", "BACK_COLOR", "TENSION_COLORS",
    "_fmt_time", "_group_words", "_word_tension", "_tension_color",
    "_build_karaoke", "_build_smooth_karaoke", "_build_word_typing", "_build_char_typing",
    "build_ass",
]
