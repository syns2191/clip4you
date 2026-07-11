"""ASS dialogue line builders for each caption animation style."""
from typing import List

from ..transcribe import Word
from .style import PRIMARY_COLOR, HIGHLIGHT_COLOR
from .utils import _fmt_time, _word_tension, _tension_color


def _highlight(w: Word, all_words: List[Word], tension_colors: bool) -> str:
    color = _tension_color(_word_tension(w, all_words)) if tension_colors else HIGHLIGHT_COLOR
    return (
        f"{{\\c{color}\\fscx120\\fscy120\\bord5\\3c&H004080FF"
        f"\\t(0,150,\\fscx100\\fscy100\\bord3\\3c&H00000000)}}"
    )


def _safe(w: Word, capitalize: bool = False) -> str:
    t = w.text.replace("{", "(").replace("}", ")")
    return (t[:1].upper() + t[1:]) if capitalize and t else t


def _fad(is_first: bool, is_last: bool, fade_in: int = 150, fade_out: int = 150) -> str:
    fi = fade_in if is_first else 0
    fo = fade_out if is_last else 0
    return f"{{\\fad({fi},{fo})}}"


def _build_karaoke(chunk, clip_start, chunk_end, all_words, tension_colors, lines, pos_tag=""):
    """Full chunk visible; active word scales up and changes color."""
    for active_idx, active_word in enumerate(chunk):
        seg_start = active_word.start - clip_start
        seg_end = active_word.end - clip_start
        if seg_end <= seg_start:
            continue

        rendered = []
        for i, w in enumerate(chunk):
            text = _safe(w, capitalize=(i == 0))
            if i == active_idx:
                rendered.append(_highlight(w, all_words, tension_colors) + text)
            else:
                rendered.append(f"{{\\c{PRIMARY_COLOR}}}{text}")

        is_first, is_last = active_idx == 0, active_idx == len(chunk) - 1
        line = pos_tag + _fad(is_first, is_last) + " ".join(rendered)
        lines.append(f"Dialogue: 0,{_fmt_time(seg_start)},{_fmt_time(seg_end)},Default,,0,0,0,,{line}\n")


def _build_smooth_karaoke(chunk, clip_start, chunk_end, all_words, tension_colors, lines, pos_tag=""):
    """Chunk fades in once; active word highlights smoothly in place."""
    FADE_IN, FADE_OUT = 200, 150
    for active_idx, active_word in enumerate(chunk):
        seg_start = active_word.start - clip_start
        seg_end = active_word.end - clip_start
        if seg_end <= seg_start:
            continue

        rendered = []
        for i, w in enumerate(chunk):
            text = _safe(w, capitalize=(i == 0))
            if i == active_idx:
                color = _tension_color(_word_tension(w, all_words)) if tension_colors else HIGHLIGHT_COLOR
                rendered.append(f"{{\\c{color}\\fscx115\\fscy115\\t(0,120,\\fscx100\\fscy100)}}{text}")
            else:
                rendered.append(f"{{\\c{PRIMARY_COLOR}}}{text}")

        is_first, is_last = active_idx == 0, active_idx == len(chunk) - 1
        line = pos_tag + _fad(is_first, is_last, FADE_IN, FADE_OUT) + " ".join(rendered)
        lines.append(f"Dialogue: 0,{_fmt_time(seg_start)},{_fmt_time(seg_end)},Default,,0,0,0,,{line}\n")


def _build_word_typing(chunk, clip_start, chunk_end, all_words, tension_colors, lines, pos_tag=""):
    """Words appear one by one, building up to the full chunk."""
    for word_idx in range(len(chunk)):
        seg_start = chunk[word_idx].start - clip_start
        seg_end = chunk[word_idx + 1].start - clip_start if word_idx + 1 < len(chunk) else chunk_end
        if seg_end <= seg_start:
            continue

        rendered = []
        for i in range(word_idx + 1):
            w = chunk[i]
            text = _safe(w, capitalize=(i == 0))
            if i == word_idx:
                rendered.append(_highlight(w, all_words, tension_colors) + text)
            else:
                rendered.append(f"{{\\c{PRIMARY_COLOR}}}{text}")

        is_first, is_last = word_idx == 0, word_idx == len(chunk) - 1
        line = pos_tag + _fad(is_first, is_last) + " ".join(rendered)
        lines.append(f"Dialogue: 0,{_fmt_time(seg_start)},{_fmt_time(seg_end)},Default,,0,0,0,,{line}\n")


def _build_char_typing(chunk, clip_start, chunk_end, all_words, tension_colors, lines, pos_tag=""):
    """Character-by-character typing animation."""
    typed_frames = []

    for word_idx, word in enumerate(chunk):
        w_start = word.start - clip_start
        w_end = word.end - clip_start
        if w_end <= w_start:
            continue

        safe_word = _safe(word, capitalize=(word_idx == 0))
        prefix_parts = [_safe(chunk[pi], capitalize=(pi == 0)) for pi in range(word_idx)]
        prefix = " ".join(prefix_parts)
        color = _tension_color(_word_tension(word, all_words)) if tension_colors else HIGHLIGHT_COLOR
        n = len(safe_word)
        char_dur = (w_end - w_start) / max(n, 1)

        for ci in range(1, n + 1):
            partial = safe_word[:ci]
            t_start = w_start + (ci - 1) * char_dur
            t_end = w_start + ci * char_dur if ci < n else w_end
            parts = []
            if prefix:
                parts.append(f"{{\\c{PRIMARY_COLOR}}}{prefix}")
            parts.append(
                f"{{\\c{color}\\fscx120\\fscy120\\bord5\\3c&H004080FF"
                f"\\t(0,80,\\fscx100\\fscy100\\bord3\\3c&H00000000)}}{partial}"
            )
            typed_frames.append((t_start, t_end, " ".join(parts)))

    if typed_frames:
        last = typed_frames[-1]
        typed_frames[-1] = (last[0], chunk_end, last[2])

    for fi, (t_start, t_end, display) in enumerate(typed_frames):
        if t_end <= t_start:
            continue
        is_first, is_last = fi == 0, fi == len(typed_frames) - 1
        line = pos_tag + _fad(is_first, is_last) + display
        lines.append(f"Dialogue: 0,{_fmt_time(t_start)},{_fmt_time(t_end)},Default,,0,0,0,,{line}\n")
