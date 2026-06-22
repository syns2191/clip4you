"""
ffmpeg-based rendering: cuts the source video down to a clip, reframes it
to vertical 9:16, burns in the animated captions, and overlays the text
hook -- the output side of the pipeline (the "Custom Presets" feature is
really just parameterizing the functions below).
"""
import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

from .config import settings

EMOJI_FONT_PATH = "/System/Library/Fonts/Apple Color Emoji.ttc"
EMOJI_FONT_FALLBACK = None


FFMPEG = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"


def _run(cmd: list, cwd: str = None) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr[-2000:]}")


def cut_clip(source_path: str, start: float, end: float, output_path: str) -> None:
    duration = end - start
    _run(
        [
            FFMPEG, "-y",
            "-ss", str(start),
            "-i", source_path,
            "-t", str(duration),
            "-c:v", "libx264", "-c:a", "aac",
            "-avoid_negative_ts", "make_zero",
            output_path,
        ]
    )


def reframe_vertical(
    input_path: str,
    output_path: str,
    width: int = settings.vertical_width,
    height: int = settings.vertical_height,
    mode: str = "crop",
) -> None:
    if mode == "blur":
        _reframe_blur(input_path, output_path, width, height)
    else:
        vf = f"crop=ih*9/16:ih,scale={width}:{height}:flags=lanczos"
        _run(
            [
                FFMPEG, "-y", "-i", input_path,
                "-vf", vf,
                "-c:v", "libx264", "-crf", "18", "-preset", "slow",
                "-c:a", "copy",
                output_path,
            ]
        )


def _reframe_blur(
    input_path: str,
    output_path: str,
    width: int,
    height: int,
) -> None:
    """Full horizontal video centered on a 9:16 canvas with a blurred
    version of itself as the background filling the empty space."""
    vf = (
        f"split[bg][fg];"
        f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={width}:{height},boxblur=20:5[blurred];"
        f"[fg]scale={width}:-2:force_original_aspect_ratio=decrease:flags=lanczos[scaled];"
        f"[blurred][scaled]overlay=(W-w)/2:(H-h)/2"
    )
    _run(
        [
            FFMPEG, "-y", "-i", input_path,
            "-vf", vf,
            "-c:v", "libx264", "-crf", "18", "-preset", "slow",
            "-c:a", "copy",
            output_path,
        ]
    )


def burn_captions(input_path: str, ass_path: str, output_path: str) -> None:
    import os
    cwd = os.path.dirname(os.path.abspath(ass_path))
    ass_filename = os.path.basename(ass_path)
    _run(
        [
            FFMPEG, "-y", "-i", os.path.abspath(input_path),
            "-vf", f"ass={ass_filename}",
            "-c:a", "copy",
            os.path.abspath(output_path),
        ],
        cwd=cwd,
    )


HOOK_FONT_PATH = "/System/Library/Fonts/Supplemental/Arial Black.ttf"
HOOK_FONT_FALLBACK = "/System/Library/Fonts/Supplemental/Impact.ttf"


def _render_hook_png(text: str, output_path: str, canvas_w: int = 1080) -> None:
    """Render hook text as a styled pill/badge on a transparent PNG."""
    try:
        font = ImageFont.truetype(HOOK_FONT_PATH, size=52)
    except (OSError, IOError):
        try:
            font = ImageFont.truetype(HOOK_FONT_FALLBACK, size=52)
        except (OSError, IOError):
            font = ImageFont.load_default()

    dummy = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy)
    bbox = draw.textbbox((0, 0), text.upper(), font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    pad_x, pad_y = 40, 20
    box_w = tw + pad_x * 2
    box_h = th + pad_y * 2
    img_w = min(box_w + 40, canvas_w)
    img_h = box_h + 20

    img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded rectangle background
    x0 = (img_w - box_w) // 2
    y0 = (img_h - box_h) // 2
    draw.rounded_rectangle(
        [x0, y0, x0 + box_w, y0 + box_h],
        radius=20,
        fill=(0, 0, 0, 200),
    )

    # Text centered in box
    tx = x0 + pad_x - bbox[0]
    ty = y0 + pad_y - bbox[1]
    draw.text((tx, ty), text.upper(), font=font, fill=(255, 255, 255, 255))

    img.save(output_path, "PNG")


def add_text_hook(
    input_path: str,
    hook_text: str,
    output_path: str,
    clip_duration: float = 0,
    **_kwargs,
) -> None:
    hook_png = output_path + ".hook.png"
    try:
        _render_hook_png(hook_text, hook_png)
    except Exception:
        import shutil
        shutil.copy2(input_path, output_path)
        return

    # Slide down from above (y: -h -> 100) over 0.4s, hold, fade out in last 0.5s
    fade_out = max(0, clip_duration - 0.5) if clip_duration > 0 else 999
    vf = (
        f"[1:v]format=rgba[hook];"
        f"[0:v][hook]overlay="
        f"x=(W-w)/2:"
        f"y='if(lt(t,0.4),-h+(h+120)*t/0.4,120)':"
        f"enable='lte(t,{fade_out + 0.5:.2f})'"
    )
    _run(
        [
            FFMPEG, "-y",
            "-i", input_path,
            "-i", hook_png,
            "-filter_complex", vf,
            "-c:a", "copy",
            output_path,
        ]
    )
    os.unlink(hook_png)


def _render_emoji_png(emoji: str, output_path: str, size: int = 200) -> None:
    """Render a single emoji to a transparent PNG using macOS native text rendering."""
    swift_code = f'''
import AppKit
let emoji = "{emoji}"
let font = NSFont.systemFont(ofSize: {int(size * 0.75)})
let attrs: [NSAttributedString.Key: Any] = [.font: font]
let astr = NSAttributedString(string: emoji, attributes: attrs)
let textSize = astr.size()
let canvas = NSSize(width: {size}, height: {size})
let img = NSImage(size: canvas)
img.lockFocus()
let x = (canvas.width - textSize.width) / 2
let y = (canvas.height - textSize.height) / 2
astr.draw(at: NSPoint(x: x, y: y))
img.unlockFocus()
guard let tiff = img.tiffRepresentation,
      let rep = NSBitmapImageRep(data: tiff),
      let png = rep.representation(using: .png, properties: [:]) else {{ exit(1) }}
try! png.write(to: URL(fileURLWithPath: "{output_path}"))
'''
    result = subprocess.run(
        ["swift", "-e", swift_code],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Swift emoji render failed: {result.stderr[:500]}")


def mix_music(
    input_path: str,
    music_path: str,
    output_path: str,
    original_volume: float = 0.05,
    music_volume: float = 1.0,
) -> None:
    """Mix a music track over the video, keeping original audio at low volume."""
    filter_complex = (
        f"[0:a]volume={original_volume}[voice];"
        f"[1:a]aloop=loop=-1:size=2e+09,volume={music_volume}[looped];"
        f"[voice][looped]amix=inputs=2:duration=first:normalize=0"
    )
    _run(
        [
            FFMPEG, "-y",
            "-i", input_path,
            "-i", music_path,
            "-filter_complex", filter_complex,
            "-c:v", "copy",
            "-shortest",
            output_path,
        ]
    )


def add_emoji_overlay(
    input_path: str,
    emoji: str,
    clip_duration: float,
    output_path: str,
) -> None:
    """Overlay an emoji with a pop-in animation near the punchline (last 3s)."""
    emoji_png = output_path + ".emoji.png"
    try:
        _render_emoji_png(emoji, emoji_png)
    except Exception:
        # If emoji rendering fails, skip silently
        import shutil
        shutil.copy2(input_path, output_path)
        return

    show_at = max(0, clip_duration - 3.0)
    # Pop-in: scale from 0 to 100% in 0.3s, hold for the rest
    vf = (
        f"[1:v]scale=-1:200[em];"
        f"[0:v][em]overlay="
        f"x=(W-w)/2:y=H*0.35:"
        f"enable='between(t,{show_at:.2f},{clip_duration:.2f})'"
    )
    _run(
        [
            FFMPEG, "-y",
            "-i", input_path,
            "-i", emoji_png,
            "-filter_complex", vf,
            "-c:a", "copy",
            output_path,
        ]
    )
    os.unlink(emoji_png)
