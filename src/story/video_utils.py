"""Video processing utilities (ffmpeg wrappers)."""
import os
import shutil
import subprocess
from typing import List

from ..render import FFMPEG
from ..config import settings

ANIMATION_PRESETS = [
    "zoom-in", "zoom-out", "pan-left", "pan-right",
    "pan-up", "pan-down", "zoom-pan", "ken-burns", "static",
]

_KEN_BURNS_CYCLE = ["zoom-in", "pan-right", "zoom-out", "pan-left", "zoom-pan", "pan-up"]
_ken_burns_idx = 0


def _get_zoompan_expr(animation: str, frames: int, w: int, h: int) -> str:
    """Build the zoompan filter expression for a given animation preset."""
    d = frames
    zoom_in_step = 0.2 / max(d, 1)
    zoom_out_step = 0.3 / max(d, 1)
    if animation == "zoom-in":
        return f"zoompan=z='min(zoom+{zoom_in_step:.6f},1.2)':d={d}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps=25"
    elif animation == "zoom-out":
        return f"zoompan=z='if(eq(on,1),1.3,max(zoom-{zoom_out_step:.6f},1.0))':d={d}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps=25"
    elif animation == "pan-left":
        return f"zoompan=z=1.1:d={d}:x='iw*0.15*(1-on/{d})':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps=25"
    elif animation == "pan-right":
        return f"zoompan=z=1.1:d={d}:x='iw*0.15*on/{d}':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps=25"
    elif animation == "pan-up":
        return f"zoompan=z=1.1:d={d}:x='iw/2-(iw/zoom/2)':y='ih*0.15*(1-on/{d})':s={w}x{h}:fps=25"
    elif animation == "pan-down":
        return f"zoompan=z=1.1:d={d}:x='iw/2-(iw/zoom/2)':y='ih*0.15*on/{d}':s={w}x{h}:fps=25"
    elif animation == "zoom-pan":
        return f"zoompan=z='min(zoom+{zoom_in_step:.6f},1.2)':d={d}:x='iw*0.1*on/{d}':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps=25"
    else:  # static
        return f"zoompan=z=1:d={d}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps=25"


def _image_to_video(image_path: str, duration: float, output_path: str, animation: str = "ken-burns") -> None:
    """Convert a static image to a video with selectable animation effect."""
    global _ken_burns_idx
    w = settings.vertical_width
    h = settings.vertical_height
    frames = int(duration * 25)

    # Ken Burns mode cycles through different effects per scene
    if animation == "ken-burns":
        actual = _KEN_BURNS_CYCLE[_ken_burns_idx % len(_KEN_BURNS_CYCLE)]
        _ken_burns_idx += 1
    else:
        actual = animation

    zoompan_expr = _get_zoompan_expr(actual, frames, w, h)

    vf = (
        f"split[bg][fg];"
        f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},boxblur=25:5[blurred];"
        f"[fg]scale={w}:{h}:force_original_aspect_ratio=decrease[scaled];"
        f"[blurred][scaled]overlay=(W-w)/2:(H-h)/2[composed];"
        f"[composed]{zoompan_expr},"
        f"format=yuv420p"
    )
    cmd = [
        FFMPEG, "-y",
        "-loop", "1",
        "-i", image_path,
        "-filter_complex", vf,
        "-t", str(duration),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        vf_simple = (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,"
            f"format=yuv420p"
        )
        cmd2 = [
            FFMPEG, "-y",
            "-loop", "1",
            "-i", image_path,
            "-vf", vf_simple,
            "-t", str(duration),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            output_path,
        ]
        result2 = subprocess.run(cmd2, capture_output=True, text=True)
        if result2.returncode != 0:
            raise RuntimeError(f"Image to video failed:\n{result2.stderr[-1000:]}")


def _trim_video_to_duration(input_path: str, duration: float, output_path: str) -> None:
    """Trim a video to exact duration."""
    cmd = [
        FFMPEG, "-y",
        "-i", input_path,
        "-t", str(duration),
        "-c:v", "libx264", "-c:a", "aac",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Trim failed:\n{result.stderr[-1000:]}")


def _get_audio_duration(path: str) -> float:
    """Get audio file duration."""
    ffprobe = os.path.join(os.path.dirname(FFMPEG), "ffprobe")
    cmd = [
        ffprobe, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 5.0


def _concat_scenes(scene_videos: List[str], output_path: str) -> None:
    """Concatenate scene videos into one (no transitions)."""
    if len(scene_videos) == 1:
        shutil.copy2(scene_videos[0], output_path)
        return

    list_file = output_path + ".txt"
    with open(list_file, "w") as f:
        for path in scene_videos:
            f.write(f"file '{os.path.abspath(path)}'\n")
    cmd = [
        FFMPEG, "-y", "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-an",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    os.unlink(list_file)
    if result.returncode != 0:
        raise RuntimeError(f"Concat failed:\n{result.stderr[-1000:]}")


def _concat_scenes_with_audio(scene_videos: List[str], output_path: str) -> None:
    """Concatenate scene videos keeping their audio tracks (for Veo)."""
    if len(scene_videos) == 1:
        shutil.copy2(scene_videos[0], output_path)
        return

    list_file = output_path + ".txt"
    with open(list_file, "w") as f:
        for path in scene_videos:
            f.write(f"file '{os.path.abspath(path)}'\n")
    cmd = [
        FFMPEG, "-y", "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    os.unlink(list_file)
    if result.returncode != 0:
        raise RuntimeError(f"Concat with audio failed:\n{result.stderr[-1000:]}")


def _concat_with_transitions(scene_videos: List[str], output_path: str, fade_duration: float = 0.8) -> None:
    """Concatenate scene videos with crossfade transitions between each scene."""
    if len(scene_videos) == 1:
        shutil.copy2(scene_videos[0], output_path)
        return

    if len(scene_videos) == 2:
        dur = _get_audio_duration(scene_videos[0])
        offset = max(0, dur - fade_duration)
        cmd = [
            FFMPEG, "-y",
            "-i", scene_videos[0], "-i", scene_videos[1],
            "-filter_complex",
            f"[0:v][1:v]xfade=transition=fade:duration={fade_duration}:offset={offset}[v]",
            "-map", "[v]", "-an",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            _concat_scenes(scene_videos, output_path)
        return

    # For 3+ scenes: chain xfade filters
    inputs = []
    for path in scene_videos:
        inputs += ["-i", path]

    durations = [_get_audio_duration(p) for p in scene_videos]

    # Build xfade chain
    n = len(scene_videos)
    filter_parts = []
    offset = durations[0] - fade_duration

    # First xfade
    filter_parts.append(
        f"[0:v][1:v]xfade=transition=fade:duration={fade_duration}:offset={offset:.3f}[v1]"
    )

    for i in range(2, n):
        prev = f"[v{i-1}]"
        # Cumulative offset: previous accumulated duration + current scene - fade overlap
        offset += durations[i-1] - fade_duration
        out = f"[v{i}]" if i < n - 1 else "[v]"
        filter_parts.append(
            f"{prev}[{i}:v]xfade=transition=fade:duration={fade_duration}:offset={offset:.3f}{out}"
        )

    filter_complex = ";".join(filter_parts)
    cmd = [FFMPEG, "-y"] + inputs + [
        "-filter_complex", filter_complex,
        "-map", "[v]", "-an",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Fallback to simple concat if xfade fails
        print("   Transitions failed, using simple concat...")
        _concat_scenes(scene_videos, output_path)


def _merge_audio_video(video_path: str, audio_path: str, output_path: str) -> None:
    """Merge final narration audio with the visual track. Video duration wins."""
    cmd = [
        FFMPEG, "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-map", "0:v:0", "-map", "1:a:0",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Merge failed:\n{result.stderr[-1000:]}")


def _pad_audio_to_duration(input_path: str, target_duration: float, output_path: str) -> None:
    """Pad an audio file with silence to reach target duration."""
    current_duration = _get_audio_duration(input_path)
    if current_duration >= target_duration:
        # Just trim to target
        cmd = [
            FFMPEG, "-y", "-i", input_path,
            "-t", str(target_duration),
            "-c:a", "libmp3lame",
            output_path,
        ]
    else:
        # Add silence padding after the speech
        pad_duration = target_duration - current_duration
        cmd = [
            FFMPEG, "-y", "-i", input_path,
            "-af", f"apad=pad_dur={pad_duration:.3f},atrim=0:{target_duration:.3f}",
            "-c:a", "libmp3lame",
            output_path,
        ]
    subprocess.run(cmd, capture_output=True, text=True)


def _concat_audios(audio_paths: List[str], output_path: str) -> None:
    """Concatenate multiple audio files into one."""
    list_file = output_path + ".txt"
    with open(list_file, "w") as f:
        for path in audio_paths:
            f.write(f"file '{os.path.abspath(path)}'\n")
    cmd = [
        FFMPEG, "-y", "-f", "concat", "-safe", "0",
        "-i", list_file, "-c:a", "libmp3lame", output_path,
    ]
    subprocess.run(cmd, capture_output=True, text=True)
    os.unlink(list_file)


def _make_text_card(text: str, duration: float, output_path: str) -> None:
    """Create a simple text-on-black video as fallback."""
    # Escape special chars for ffmpeg drawtext
    escaped = text.replace("'", "\\'").replace(":", "\\:")
    w = settings.vertical_width
    h = settings.vertical_height
    vf = (
        f"color=c=black:s={w}x{h}:d={duration},"
        f"drawtext=text='{escaped}':"
        f"fontcolor=white:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2:"
        f"fontfile=/System/Library/Fonts/Supplemental/Arial.ttf"
    )
    cmd = [
        FFMPEG, "-y",
        "-f", "lavfi", "-i", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-t", str(duration),
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        cmd2 = [
            FFMPEG, "-y",
            "-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:d={duration}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-t", str(duration),
            output_path,
        ]
        subprocess.run(cmd2, capture_output=True, text=True)
