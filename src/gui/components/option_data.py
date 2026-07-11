"""All dropdown choices for the GUI, extracted from existing modules."""

from ...narration import POPULAR_VOICES, ELEVENLABS_VOICES
from ...imagegen import ART_STYLES, CATEGORY_STYLES
from ...scriptgen import CATEGORY_GUIDANCE, CHARACTER_PRESETS, BACKGROUND_THEMES
from ...captions import CAPTION_FONTS, CAPTION_FONT_CHOICES, CAPTION_ANIMATIONS
from ...story import ANIMATION_PRESETS

VOICE_CHOICES = [""] + sorted(POPULAR_VOICES.keys())

ELEVENLABS_VOICE_CHOICES = sorted(ELEVENLABS_VOICES.keys())

VOICE_PROVIDER_CHOICES = ["edge-tts (free)", "elevenlabs"]

ART_STYLE_CHOICES = [""] + sorted(ART_STYLES.keys())

IMAGE_CATEGORY_CHOICES = [""] + sorted(CATEGORY_STYLES.keys())

ANIMATION_CHOICES = [
    "ken-burns", "zoom-in", "zoom-out", "pan-left", "pan-right",
    "pan-up", "pan-down", "zoom-pan", "static",
]

FILM_GRAIN_CHOICES = [
    "", "light", "medium", "heavy", "vintage", "35mm", "gritty",
    "noise-overlay", "retro",
]

VISUAL_SOURCE_CHOICES = ["download", "openai", "sd", "veo", "gallery"]

CAPTION_STYLE_CHOICES = ["default", "head", "bubble"]

CAPTION_FONT_CHOICES_GUI = [""] + CAPTION_FONT_CHOICES

CAPTION_ANIMATION_CHOICES = CAPTION_ANIMATIONS

SCRIPTGEN_CATEGORY_CHOICES = sorted(CATEGORY_GUIDANCE.keys())

CHARACTER_CHOICES = [""] + sorted(CHARACTER_PRESETS.keys())

BACKGROUND_CHOICES = [""] + sorted(BACKGROUND_THEMES.keys())

CLIP_CATEGORY_CHOICES = [
    "auto", "sports", "comedy", "reaction", "podcast", "gaming",
    "music", "educational", "drama", "news", "vlog", "fitness",
    "cooking", "asmr",
]

ORIENTATION_CHOICES = ["portrait", "landscape", "square"]

REFRAME_CHOICES = ["crop", "blur"]

SFX_CHOICES = [
    "", "crowd", "whoosh", "impact", "rise", "drop", "whistle",
    "horn", "buzzer",
]

PRIVACY_CHOICES = ["private", "unlisted", "public"]
