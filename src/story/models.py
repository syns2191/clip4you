"""Data models for story pipeline."""
from dataclasses import dataclass, field
from typing import List, Optional

from ..narration import SentenceTiming
from ..transcribe import Word


@dataclass
class Scene:
    text: str
    search_query: str
    visual_type: str = "video"  # "video" or "image"
    duration: float = 0.0
    start_time: float = 0.0
    visual_path: Optional[str] = None
    audio_path: Optional[str] = None
    voice: Optional[str] = None
    rate: Optional[str] = None
    mood: Optional[str] = None
    timings: List[SentenceTiming] = field(default_factory=list)
    words: List[Word] = field(default_factory=list)
    head_pos: Optional[tuple] = None


@dataclass
class BubbleGroup:
    group_idx: int
    side: str
    chunks: list
    group_start: float
    group_end: float
    head_pos: Optional[tuple] = None
