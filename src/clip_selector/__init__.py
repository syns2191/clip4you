"""LLM-powered clip selector — picks the best short-form segments from long-form transcripts."""
from .models import ClipCandidate
from .selector import select_clips

__all__ = ["ClipCandidate", "select_clips"]
