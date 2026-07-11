"""Story module — create narrated short videos from scripts."""
from .models import Scene, BubbleGroup
from .presets import MOOD_PRESETS, VOICE_MUSIC_MAP
from .pipeline import create_story
from .script_parser import _split_into_scenes, _generate_hook_text
from .visuals import _download_scene_image, _download_pexels_video, _download_youtube_clip
from .video_utils import (
    ANIMATION_PRESETS,
    _pad_audio_to_duration,
    _concat_audios,
    _get_audio_duration,
    _image_to_video,
    _trim_video_to_duration,
    _concat_with_transitions,
    _concat_scenes_with_audio,
    _merge_audio_video,
    _make_text_card,
)

__all__ = [
    "Scene",
    "BubbleGroup",
    "create_story",
    "MOOD_PRESETS",
    "VOICE_MUSIC_MAP",
    "ANIMATION_PRESETS",
    "_split_into_scenes",
    "_generate_hook_text",
    "_download_scene_image",
    "_download_pexels_video",
    "_download_youtube_clip",
    "_pad_audio_to_duration",
    "_concat_audios",
    "_get_audio_duration",
    "_image_to_video",
    "_trim_video_to_duration",
    "_concat_with_transitions",
    "_concat_scenes_with_audio",
    "_merge_audio_video",
    "_make_text_card",
]
