"""Data model for clip candidates."""
from dataclasses import dataclass

from .presets import CATEGORY_EMOJI


@dataclass
class ClipCandidate:
    start: float
    end: float
    title: str
    hook_text: str
    category: str
    score: int
    reason: str
    emoji: str = ""

    def __post_init__(self):
        if not self.emoji:
            self.emoji = CATEGORY_EMOJI.get(self.category, "\U0001F525")
