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


def _render_hook_png(text: str, output_path: str, canvas_w: int = 1080, caption_font: str = "") -> None:
    """Render hook text as a styled pill/badge on a transparent PNG."""
    font_path = HOOK_FONT_PATH
    font_fallback = HOOK_FONT_FALLBACK
    if caption_font:
        from .captions import CAPTION_FONTS
        if caption_font in CAPTION_FONTS:
            font_path = CAPTION_FONTS[caption_font]["file"]
            font_fallback = CAPTION_FONTS[caption_font]["fallback"]

    try:
        font = ImageFont.truetype(font_path, size=52)
    except (OSError, IOError):
        try:
            font = ImageFont.truetype(font_fallback, size=52)
        except (OSError, IOError):
            font = ImageFont.load_default()

    display_text = text[:1].upper() + text[1:] if text else text

    dummy = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy)
    bbox = draw.textbbox((0, 0), display_text, font=font)
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
    draw.text((tx, ty), display_text, font=font, fill=(255, 255, 255, 255))

    img.save(output_path, "PNG")


def add_text_hook(
    input_path: str,
    hook_text: str,
    output_path: str,
    clip_duration: float = 0,
    caption_font: str = "",
    **_kwargs,
) -> None:
    hook_png = output_path + ".hook.png"
    try:
        _render_hook_png(hook_text, hook_png, caption_font=caption_font)
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


def generate_crowd_roar(output_path: str, duration: float) -> None:
    """Generate a stadium crowd roar sound effect using ffmpeg synthesis."""
    fade_in = min(0.5, duration * 0.2)
    fade_out = min(1.0, duration * 0.3)
    af = (
        f"anoisesrc=d={duration:.2f}:c=pink:a=0.4,"
        f"bandpass=f=800:width_type=o:w=2,"
        f"bandpass=f=1200:width_type=o:w=3,"
        f"afade=t=in:st=0:d={fade_in:.2f},"
        f"afade=t=out:st={duration - fade_out:.2f}:d={fade_out:.2f}"
    )
    _run([
        FFMPEG, "-y",
        "-f", "lavfi", "-i", af,
        "-t", str(duration),
        "-c:a", "aac", "-b:a", "128k",
        output_path,
    ])


def generate_sfx(output_path: str, effect: str) -> None:
    """Generate a short sound effect using ffmpeg synthesis.
    Effects: whoosh, impact, rise, drop, whistle, horn, buzzer."""
    effects = {
        "whoosh": (
            "anoisesrc=d=0.4:c=pink:a=0.3,"
            "bandpass=f=2000:width_type=o:w=4,"
            "afade=t=in:st=0:d=0.1,"
            "afade=t=out:st=0.2:d=0.2,"
            "asetrate=44100*1.5,atempo=0.67"
        ),
        "impact": (
            "anoisesrc=d=0.3:c=brown:a=0.6,"
            "lowpass=f=200,"
            "afade=t=out:st=0.05:d=0.25"
        ),
        "rise": (
            "anoisesrc=d=1.5:c=pink:a=0.2,"
            "bandpass=f=1000:width_type=o:w=2,"
            "afade=t=in:st=0:d=1.2,"
            "afade=t=out:st=1.3:d=0.2,"
            "asetrate=44100*0.5,atempo=2.0"
        ),
        "drop": (
            "anoisesrc=d=0.5:c=brown:a=0.5,"
            "lowpass=f=150,"
            "afade=t=in:st=0:d=0.05,"
            "afade=t=out:st=0.1:d=0.4"
        ),
        "whistle": (
            "sine=f=3200:d=1.0,"
            "afade=t=in:st=0:d=0.05,"
            "afade=t=out:st=0.6:d=0.4,"
            "tremolo=f=6:d=0.4"
        ),
        "horn": (
            "sine=f=440:d=1.5,"
            "afade=t=in:st=0:d=0.1,"
            "afade=t=out:st=1.0:d=0.5,"
            "lowpass=f=600"
        ),
        "buzzer": (
            "sine=f=200:d=0.8,"
            "afade=t=in:st=0:d=0.02,"
            "afade=t=out:st=0.5:d=0.3,"
            "tremolo=f=15:d=0.7"
        ),
    }
    af = effects.get(effect, effects["whoosh"])
    _run([
        FFMPEG, "-y",
        "-f", "lavfi", "-i", af,
        "-c:a", "aac", "-b:a", "128k",
        output_path,
    ])


def mix_sfx(
    input_path: str,
    sfx_path: str,
    output_path: str,
    offset: float = 0.0,
    volume: float = 0.6,
) -> None:
    """Mix a sound effect into the video at a given offset (seconds)."""
    delay_ms = int(offset * 1000)
    af = (
        f"[1:a]volume={volume},adelay={delay_ms}|{delay_ms},apad[sfx];"
        f"[0:a][sfx]amix=inputs=2:duration=first:normalize=0"
    )
    _run([
        FFMPEG, "-y",
        "-i", input_path,
        "-i", sfx_path,
        "-filter_complex", af,
        "-map", "0:v", "-c:v", "copy",
        output_path,
    ])


def add_film_grain(
    input_path: str,
    output_path: str,
    intensity: str = "medium",
) -> None:
    """Add film grain/noise effect.
    Styles: light, medium, heavy, vintage, 35mm, gritty, noise-overlay, retro."""
    if intensity == "vintage":
        vf = (
            "noise=alls=20:allf=t+u,"
            "eq=saturation=0.4:contrast=1.15:brightness=0.03:gamma=1.1,"
            "colorbalance=rs=0.18:gs=0.06:bs=-0.12:rm=0.12:gm=0.03:bm=-0.10,"
            "curves=vintage,"
            "vignette=PI/3.5,"
            "noise=c0s=8:c0f=t,"
            "drawbox=x=iw*random(1):y=0:w=1:h=ih:color=white@0.03:t=fill,"
            "drawbox=x=iw*random(2):y=0:w=1:h=ih:color=white@0.05:t=fill,"
            "drawbox=x=iw*random(3):y=0:w=2:h=ih:color=white@0.02:t=fill"
        )
    elif intensity == "35mm":
        # 35mm film texture: fine organic grain, slight halation bloom,
        # warm highlight shift, subtle vignette, filmic contrast curve
        vf = (
            "noise=alls=12:allf=t+u,"
            "eq=saturation=0.82:contrast=1.2:brightness=0.02:gamma=1.05,"
            "colorbalance=rs=0.08:gs=0.03:bs=-0.05:rh=0.06:gh=0.02:bh=-0.03,"
            "unsharp=3:3:-0.5:3:3:-0.5,"
            "vignette=PI/4.5,"
            "noise=c0s=5:c0f=t"
        )
    elif intensity == "gritty":
        # Gritty cinematic: crushed blacks, heavy grain, desaturated,
        # teal-orange color grade, strong vignette, harsh contrast
        vf = (
            "noise=alls=25:allf=t+u,"
            "eq=saturation=0.5:contrast=1.35:brightness=-0.03:gamma=0.9,"
            "colorbalance=rs=-0.05:gs=-0.08:bs=0.12:rm=0.10:gm=0.02:bm=-0.08,"
            "curves=preset=cross_process,"
            "vignette=PI/3,"
            "noise=c0s=10:c0f=t,"
            "drawbox=x=iw*random(1):y=0:w=1:h=ih:color=white@0.04:t=fill,"
            "drawbox=x=iw*random(2):y=0:w=2:h=ih:color=black@0.06:t=fill"
        )
    elif intensity == "noise-overlay":
        # Heavy noise overlay: dense visible grain across all channels,
        # slight desaturation, subtle contrast boost, no color shift
        vf = (
            "noise=alls=30:allf=t+u,"
            "noise=c0s=15:c0f=t,"
            "eq=saturation=0.75:contrast=1.1,"
            "vignette=PI/5"
        )
    elif intensity == "retro":
        # Retro look: warm amber tint, faded blacks, heavy grain,
        # film scratches, projector flicker, strong vignette
        vf = (
            "noise=alls=22:allf=t+u,"
            "eq=saturation=0.35:contrast=1.25:brightness=0.05:gamma=1.15,"
            "colorbalance=rs=0.22:gs=0.10:bs=-0.15:rm=0.15:gm=0.05:bm=-0.12,"
            "curves=vintage,"
            "vignette=PI/3,"
            "noise=c0s=12:c0f=t,"
            "drawbox=x=iw*random(1):y=0:w=1:h=ih:color=white@0.05:t=fill,"
            "drawbox=x=iw*random(2):y=0:w=1:h=ih:color=white@0.03:t=fill,"
            "drawbox=x=iw*random(3):y=0:w=2:h=ih:color=white@0.04:t=fill,"
            "drawbox=x=iw*random(4):y=0:w=1:h=ih:color=black@0.03:t=fill"
        )
    else:
        levels = {"light": 3, "medium": 8, "heavy": 15}
        s = levels.get(intensity, 8)
        sat = {"light": 0.9, "medium": 0.85, "heavy": 0.75}
        vf = f"noise=alls={s}:allf=t,eq=saturation={sat.get(intensity, 0.85)},vignette=PI/5"
    _run([
        FFMPEG, "-y",
        "-i", input_path,
        "-vf", vf,
        "-c:a", "copy",
        output_path,
    ])


BUBBLE_FONT_PATH = "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"
BUBBLE_FONT_FALLBACK = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def detect_head_position(image_path: str, video_w: int = None, video_h: int = None):
    """Detect the person's head position in an image.
    Uses Haar cascade (picks face closest to center), skin color detection,
    and edge contour fallback. Works on photos, paintings, and sketches.
    Returns (x, y) of head center-top in video coordinates."""
    try:
        import cv2
        import numpy as np
        img = cv2.imread(image_path)
        if img is None:
            return None
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        img_h, img_w = img.shape[:2]
        vw = video_w or img_w
        vh = video_h or img_h
        center_x, center_y = img_w // 2, img_h // 3

        def _to_video(x, y):
            return (int(x * vw / img_w), int(y * vh / img_h))

        def _dist_to_center(fx, fy, fw, fh):
            face_cx = fx + fw // 2
            face_cy = fy + fh // 2
            return ((face_cx - center_x) ** 2 + (face_cy - center_y) ** 2) ** 0.5

        # 1. Haar cascade — pick the face closest to upper-center (main character)
        all_faces = []
        for cascade_name in [
            "haarcascade_frontalface_default.xml",
            "haarcascade_frontalface_alt2.xml",
            "haarcascade_profileface.xml",
        ]:
            cascade = cv2.CascadeClassifier(cv2.data.haarcascades + cascade_name)
            faces = cascade.detectMultiScale(
                gray, scaleFactor=1.05, minNeighbors=4, minSize=(25, 25)
            )
            for f in faces:
                all_faces.append(f)

        if all_faces:
            # Filter: must be at least 3% of image width (not tiny false positives)
            min_size = img_w * 0.03
            real_faces = [f for f in all_faces if f[2] >= min_size]
            if real_faces:
                best = min(real_faces, key=lambda f: _dist_to_center(*f))
                fx, fy, fw, fh = best
                return _to_video(fx + fw // 2, fy)

        # 2. Skin color detection (for colorful/painted images)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        lower1 = np.array([0, 20, 70])
        upper1 = np.array([20, 255, 255])
        lower2 = np.array([170, 20, 70])
        upper2 = np.array([180, 255, 255])
        skin = cv2.inRange(hsv, lower1, upper1) | cv2.inRange(hsv, lower2, upper2)
        upper_skin = skin[:int(img_h * 0.5), :]
        skin_contours, _ = cv2.findContours(upper_skin, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if skin_contours:
            large_skin = [c for c in skin_contours if cv2.contourArea(c) > img_w * img_h * 0.003]
            if large_skin:
                best_skin = min(large_skin, key=lambda c: abs(cv2.boundingRect(c)[0] + cv2.boundingRect(c)[2] // 2 - center_x))
                x, y, w, h = cv2.boundingRect(best_skin)
                return _to_video(x + w // 2, max(y, 10))

        # 3. Edge/contour fallback (for sketches/drawings)
        edges = cv2.Canny(gray, 50, 150)
        upper_edges = edges[:int(img_h * 0.6), :]
        contours, _ = cv2.findContours(upper_edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            large = [c for c in contours if cv2.contourArea(c) > img_w * img_h * 0.005]
            if large:
                best_c = min(large, key=lambda c: abs(cv2.boundingRect(c)[0] + cv2.boundingRect(c)[2] // 2 - center_x))
                x, y, w, h = cv2.boundingRect(best_c)
                return _to_video(x + w // 2, max(y, int(img_h * 0.1)))

        # 4. Dark stroke fallback (for b&w sketches)
        upper = gray[:int(img_h * 0.6), :]
        _, binary = cv2.threshold(upper, 128, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            large = [c for c in contours if cv2.contourArea(c) > img_w * img_h * 0.005]
            if large:
                best_c = min(large, key=lambda c: abs(cv2.boundingRect(c)[0] + cv2.boundingRect(c)[2] // 2 - center_x))
                x, y, w, h = cv2.boundingRect(best_c)
                return _to_video(x + w // 2, max(y, int(img_h * 0.1)))

        # 5. Last fallback: center, upper third
        return (vw // 2, int(vh * 0.25))

    except Exception:
        return None


def _ease_out_back(x: float, c: float = 2.5) -> float:
    c1 = c + 1
    return 1 + c1 * (x - 1) ** 3 + c * (x - 1) ** 2


def _generate_cloud_points(cx: float, cy: float, rx: float, ry: float,
                           num_points: int = 360, num_bumps: int = 8,
                           amplitude: float = 0.12) -> list:
    import math
    points = []
    for i in range(num_points):
        angle = 2 * math.pi * i / num_points
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        r_base = (rx * ry) / math.sqrt((ry * cos_a) ** 2 + (rx * sin_a) ** 2)
        wave = 1 + amplitude * math.cos(num_bumps * angle)
        r = r_base * wave
        points.append((cx + r * cos_a, cy + r * sin_a))
    return points


def _compute_dot_positions(tail_anchor: tuple, cloud_center: tuple,
                           radii: list = None, gap: int = 6,
                           side: str = "left") -> list:
    """Place trail dots along a curved path from tail_anchor toward cloud.
    The path angles left or right so dots are not in a straight vertical line."""
    import math
    if radii is None:
        radii = [5, 9, 14]
    ax, ay = tail_anchor
    ccx, ccy = cloud_center
    dx = ccx - ax
    dy = ccy - ay
    dist = math.sqrt(dx * dx + dy * dy)
    if dist < 1:
        dist = 1
    ux, uy = dx / dist, dy / dist

    cross_sign = 1.0 if side == "right" else -1.0
    px, py = -uy * cross_sign, ux * cross_sign

    positions = []
    cursor_x = ax + ux * (radii[0] + gap)
    cursor_y = ay + uy * (radii[0] + gap)
    positions.append((cursor_x, cursor_y))
    for i in range(1, len(radii)):
        step = radii[i - 1] + gap + radii[i]
        drift = step * 0.35
        cursor_x += ux * step + px * drift
        cursor_y += uy * step + py * drift
        positions.append((cursor_x, cursor_y))
    return positions


def _draw_dot(img: Image.Image, center: tuple, radius: float, alpha: int) -> None:
    if radius <= 0 or alpha <= 0:
        return
    cx, cy = center
    r = radius
    sw = 2.5
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse([cx - r - sw, cy - r - sw, cx + r + sw, cy + r + sw],
              fill=(17, 17, 17, alpha))
    d.ellipse([cx - r, cy - r, cx + r, cy + r],
              fill=(255, 255, 255, alpha))
    img.alpha_composite(layer)


def _draw_cloud(img: Image.Image, base_points: list, scale: float,
                alpha: int, center: tuple, bob_y: float) -> None:
    if scale <= 0 or alpha <= 0:
        return
    cx, cy = center
    scaled = [(cx + (px - cx) * scale, cy + (py - cy) * scale + bob_y)
              for px, py in base_points]
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    fill = (255, 255, 255, alpha)
    d.polygon(scaled, fill=fill)
    stroke = (17, 17, 17, alpha)
    for i in range(len(scaled)):
        p1 = scaled[i]
        p2 = scaled[(i + 1) % len(scaled)]
        d.line([p1, p2], fill=stroke, width=3)
    img.alpha_composite(layer)


def _wrap_bubble_text(text: str, max_chars: int = 20) -> str:
    capitalized = text[:1].upper() + text[1:] if text else text
    words = capitalized.split()
    lines = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 > max_chars:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        lines.append(current)
    return "\n".join(lines)


def _draw_bubble_text(img: Image.Image, text: str, center: tuple,
                      font, alpha: int, bob_y: float) -> None:
    if alpha <= 0:
        return
    wrapped = _wrap_bubble_text(text)
    cx, cy = center
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    bbox = d.multiline_textbbox((0, 0), wrapped, font=font, align="center")
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = cx - tw / 2 - bbox[0]
    ty = cy - th / 2 - bbox[1] + bob_y
    d.multiline_text((tx, ty), wrapped, font=font, fill=(30, 30, 30, alpha), align="center")
    img.alpha_composite(layer)


def _load_bubble_font(caption_font: str = ""):
    font_path = BUBBLE_FONT_PATH
    font_fallback = BUBBLE_FONT_FALLBACK
    if caption_font:
        from .captions import CAPTION_FONTS
        if caption_font in CAPTION_FONTS:
            font_path = CAPTION_FONTS[caption_font]["file"]
            font_fallback = CAPTION_FONTS[caption_font]["fallback"]
    try:
        return ImageFont.truetype(font_path, size=36)
    except (OSError, IOError):
        try:
            return ImageFont.truetype(font_fallback, size=36)
        except (OSError, IOError):
            return ImageFont.load_default()


def _compute_bubble_geometry(text: str, canvas_w: int, canvas_h: int,
                             head_pos: tuple, font,
                             side: str = "left") -> dict:
    import math
    wrapped = _wrap_bubble_text(text)
    dummy = Image.new("RGBA", (1, 1))
    dd = ImageDraw.Draw(dummy)
    bbox = dd.multiline_textbbox((0, 0), wrapped, font=font, align="center")
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    pad_x, pad_y = 45, 30
    bubble_w = max(tw + pad_x * 2, 200)
    bubble_h = max(th + pad_y * 2, 120)

    ref_rx, ref_ry = 108, 65
    scale_x = (bubble_w + 60) / (ref_rx * 2)
    scale_y = (bubble_h + 50) / (ref_ry * 2)
    sc = max(scale_x, scale_y)
    rx = ref_rx * sc
    ry = ref_ry * sc

    margin = 60

    if head_pos:
        hx, hy = head_pos
        bx = hx - bubble_w // 2
        by = hy - bubble_h - 120
        bx = max(margin, min(bx, canvas_w - bubble_w - margin))
        by = max(margin, min(by, canvas_h // 3))
    else:
        bx = (canvas_w - bubble_w) // 2
        by = max(margin, 100)

    cloud_cx = bx + bubble_w // 2
    cloud_cy = by + bubble_h // 2

    cloud_cx = max(margin + int(rx), min(cloud_cx, canvas_w - margin - int(rx)))
    cloud_cy = max(margin + int(ry), min(cloud_cy, canvas_h - margin - int(ry)))

    cloud_points = _generate_cloud_points(cloud_cx, cloud_cy, rx, ry)

    dot_radii_base = [5, 9, 14]
    dot_radii = [r * sc for r in dot_radii_base]
    gap = int(6 * sc)
    total_dot_span = sum(dot_radii) * 2 + gap * len(dot_radii) + 30
    if head_pos:
        hx, hy = head_pos
        min_tail_y = cloud_cy + int(ry) + total_dot_span
        tail_y = max(hy - 30, min_tail_y)
        tail_anchor = (hx, tail_y)
    else:
        tail_anchor = (cloud_cx, cloud_cy + int(ry) + total_dot_span)

    dot_positions = _compute_dot_positions(
        tail_anchor, (cloud_cx, cloud_cy),
        radii=dot_radii, gap=gap, side=side)

    dot_positions = [
        (max(margin + r, min(x, canvas_w - margin - r)),
         max(margin + r, min(y, canvas_h - margin - r)))
        for (x, y), r in zip(dot_positions, dot_radii)
    ]

    return {
        "cloud_points": cloud_points,
        "cloud_center": (cloud_cx, cloud_cy),
        "dot_positions": dot_positions,
        "dot_radii": dot_radii,
    }


def _render_bubble_frame(t: float, geom: dict, text: str, font,
                         canvas_w: int, canvas_h: int,
                         reveal_scale: float = 1.0) -> Image.Image:
    import math

    cloud_points = geom["cloud_points"]
    cloud_center = geom["cloud_center"]
    dot_positions = geom["dot_positions"]
    dot_radii = geom["dot_radii"]

    dot_timings = [
        (0.00 * reveal_scale, 0.30 * reveal_scale),
        (0.35 * reveal_scale, 0.30 * reveal_scale),
        (0.70 * reveal_scale, 0.30 * reveal_scale),
    ]
    cloud_start = 1.05 * reveal_scale
    cloud_dur = 0.50 * reveal_scale
    idle_start = 1.65 * reveal_scale

    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

    bob_y = 0.0
    if t > idle_start:
        bob_y = 7.0 * math.sin(1.5 * (t - idle_start))

    for i, (pop_start, dur) in enumerate(dot_timings):
        if t < pop_start:
            continue
        progress = min((t - pop_start) / max(dur, 0.01), 1.0)
        sc = _ease_out_back(progress)
        alpha = int(255 * min(progress * 3, 1.0))
        dot_bob = 0.0
        if t > idle_start:
            dot_bob = bob_y * (0.1 + 0.3 * i)
        cx, cy = dot_positions[i]
        _draw_dot(img, (cx, cy + dot_bob), dot_radii[i] * sc, alpha)

    if t >= cloud_start:
        progress = min((t - cloud_start) / max(cloud_dur, 0.01), 1.0)
        sc = _ease_out_back(progress)
        alpha = int(255 * min(progress * 3, 1.0))
        _draw_cloud(img, cloud_points, sc, alpha, cloud_center, bob_y)
        if alpha > 100:
            _draw_bubble_text(img, text, cloud_center, font, alpha, bob_y)

    return img


def render_animated_bubble_mov(group, output_path: str,
                               canvas_w: int, canvas_h: int,
                               caption_font: str = "") -> None:
    fps = 25
    duration = group.group_end - group.group_start
    if duration <= 0:
        return

    font = _load_bubble_font(caption_font)

    final_text = group.chunks[-1][0] if group.chunks else ""
    geom = _compute_bubble_geometry(final_text, canvas_w, canvas_h,
                                    group.head_pos, font,
                                    side=group.side)

    reveal_scale = 1.0
    if duration < 1.65:
        reveal_scale = (duration * 0.7) / 1.65

    total_frames = max(int(duration * fps), 1)

    proc = subprocess.Popen([
        FFMPEG, "-y",
        "-f", "rawvideo",
        "-pix_fmt", "rgba",
        "-s", f"{canvas_w}x{canvas_h}",
        "-r", str(fps),
        "-i", "pipe:0",
        "-c:v", "qtrle",
        output_path,
    ], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    for frame_idx in range(total_frames):
        t_local = frame_idx / fps
        t_global = group.group_start + t_local

        active_text = group.chunks[0][0]
        for chunk_text, chunk_start, chunk_end in group.chunks:
            if chunk_start <= t_global <= chunk_end:
                active_text = chunk_text
                break
            if t_global > chunk_end:
                active_text = chunk_text

        frame = _render_bubble_frame(t_local, geom, active_text, font,
                                     canvas_w, canvas_h, reveal_scale)
        proc.stdin.write(frame.tobytes())

    proc.stdin.close()
    proc.wait()


def burn_thought_bubbles(
    input_path: str,
    output_path: str,
    bubble_groups: list,
    tmp_dir: str = None,
    caption_font: str = "",
) -> None:
    """Overlay animated thought bubble WebM clips onto video.
    bubble_groups: list of BubbleGroup dataclass instances."""
    import tempfile
    if tmp_dir is None:
        tmp_dir = tempfile.mkdtemp()

    if not bubble_groups:
        import shutil
        shutil.copy2(input_path, output_path)
        return

    from .config import settings
    vw = settings.vertical_width
    vh = settings.vertical_height

    mov_info = []
    for group in bubble_groups:
        mov_path = os.path.join(tmp_dir, f"bubble_{group.group_idx:04d}.mov")
        print(f"      Rendering bubble group {group.group_idx} ({group.group_end - group.group_start:.1f}s)...")
        render_animated_bubble_mov(group, mov_path, canvas_w=vw, canvas_h=vh,
                                   caption_font=caption_font)
        if os.path.exists(mov_path) and os.path.getsize(mov_path) > 0:
            mov_info.append((mov_path, group.group_start, group.group_end))

    if not mov_info:
        import shutil
        shutil.copy2(input_path, output_path)
        return

    inputs = ["-i", input_path]
    for mov_path, start, _ in mov_info:
        inputs += ["-itsoffset", f"{start:.3f}", "-i", mov_path]

    filters = []
    prev = "0:v"
    for i, (_, start, end) in enumerate(mov_info):
        inp = f"{i + 1}:v"
        out = f"[v{i}]" if i < len(mov_info) - 1 else "[vout]"
        filters.append(
            f"[{prev}][{inp}]overlay=0:0:format=auto:"
            f"enable='between(t,{start:.3f},{end:.3f})'"
            f"{out}"
        )
        prev = f"v{i}"

    fc = ";".join(filters)
    cmd = [
        FFMPEG, "-y",
    ] + inputs + [
        "-filter_complex", fc,
        "-map", "[vout]", "-map", "0:a",
        "-c:a", "copy",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        import shutil
        shutil.copy2(input_path, output_path)

    for mov_path, _, _ in mov_info:
        if os.path.exists(mov_path):
            os.unlink(mov_path)


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
