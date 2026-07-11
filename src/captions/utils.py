"""Shared helpers used across animation builders."""
from typing import List

from ..transcribe import Word
from .style import TENSION_COLORS, WORDS_PER_CHUNK


def _fmt_time(t: float) -> str:
    t = max(t, 0.0)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:01d}:{m:02d}:{s:05.2f}"


def _group_words(words: List[Word]) -> List[List[Word]]:
    return [words[i:i + WORDS_PER_CHUNK] for i in range(0, len(words), WORDS_PER_CHUNK)]


def _word_tension(word: Word, all_words: List[Word]) -> float:
    """Score 0–1 based on how fast this word is spoken relative to the clip average."""
    duration = word.end - word.start
    if duration <= 0:
        return 0.5
    rates = [len(w.text) / (w.end - w.start) for w in all_words if (w.end - w.start) > 0]
    if not rates:
        return 0.5
    avg = sum(rates) / len(rates)
    return max(0.0, min(1.0, (len(word.text) / duration / avg - 0.5) / 1.5))


def _tension_color(tension: float) -> str:
    idx = min(int(tension * len(TENSION_COLORS)), len(TENSION_COLORS) - 1)
    return TENSION_COLORS[idx]
