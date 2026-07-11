"""AI script generator — produces timeline-format scripts for story mode rendering."""
from .generator import generate_script
from .presets import CATEGORY_GUIDANCE, CHARACTER_PRESETS, BACKGROUND_THEMES, ART_STYLE_TEMPLATES

__all__ = [
    "generate_script",
    "CATEGORY_GUIDANCE",
    "CHARACTER_PRESETS",
    "BACKGROUND_THEMES",
    "ART_STYLE_TEMPLATES",
]
